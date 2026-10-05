import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from telegram import Bot

from app.config.settings import settings
from app.database.connection import create_session_factory
from app.database.models import Order, OrderStatus, Payment, UnmatchedWebhook
from app.services.delivery_service import DeliveryService
from app.services.order_service import OrderService

app = FastAPI(title="Shop Bot Payment Webhook")
logger = logging.getLogger(__name__)
REFERENCE_PATTERN = re.compile(r"ORD[A-Za-z0-9]+")
PAYMENT_LOOKBACK_MINUTES = 30


def _authorize_request(request: Request) -> bool:
    authorization = request.headers.get("authorization") or request.headers.get("Authorization")
    if not authorization:
        return False
    parts = authorization.split()
    if len(parts) != 2:
        return False
    return parts[0].lower() == "apikey" and parts[1] == settings.sepay_api_key


def _payload_value(payload: dict, *keys: str):
    current = payload
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _normalize_amount(value) -> Decimal:
    if value is None:
        raise ValueError("Missing transaction amount")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid transaction amount: {value}") from exc


def _extract_reference_code(content: str | None) -> str | None:
    if not content:
        return None
    match = REFERENCE_PATTERN.search(content)
    return match.group(0) if match else None


def _recent_pending_orders_by_amount(session, amount: Decimal) -> list[Order]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PAYMENT_LOOKBACK_MINUTES)
    return list(
        session.scalars(
            select(Order)
            .where(
                Order.status == OrderStatus.PENDING,
                Order.amount == amount,
                Order.created_at >= cutoff,
            )
        ).all()
    )


async def _notify_admins(message: str) -> None:
    if not settings.bot_token or not settings.admin_ids:
        logger.warning("Skipping SePay admin notification because BOT_TOKEN or ADMIN_IDS is not configured.")
        return

    bot = Bot(token=settings.bot_token)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=message)
        except Exception:
            logger.exception("Failed to notify Telegram admin %s about SePay manual review", admin_id)


async def _deliver_order(order_id: str) -> None:
    if not settings.bot_token:
        logger.warning("Skipping automatic delivery for order %s because BOT_TOKEN is not configured.", order_id)
        return

    session_factory = create_session_factory(settings.database_url)
    session = session_factory()
    bot = Bot(token=settings.bot_token)
    try:
        await DeliveryService().deliver_order(session, bot, order_id)
    except Exception:
        logger.exception("Automatic delivery failed for order %s", order_id)
        try:
            await _notify_admins(
                f"⚠️ Automatic delivery task failed for order #{order_id}; please deliver manually."
            )
        except Exception:
            logger.exception("Failed to notify admin after automatic delivery failure for order %s", order_id)
    finally:
        session.close()


def _save_unmatched_webhook(session, *, reason: str, transaction_id: str | None, reference_code: str | None, amount: Decimal | None, expected_amount: Decimal | None, payload: dict, order_id: str | None = None, message: str | None = None) -> None:
    session.add(
        UnmatchedWebhook(
            reason=reason,
            transaction_id=transaction_id,
            order_id=order_id,
            reference_code=reference_code,
            amount=amount,
            expected_amount=expected_amount,
            payload=payload,
            message=message,
        )
    )
    session.flush()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/payment")
async def payment_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    logger.info("Incoming SePay webhook received: method=%s path=%s headers=%s", request.method, request.url.path, dict(request.headers))
    if not _authorize_request(request):
        logger.warning("Rejected unauthenticated SePay webhook request from %s", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="Unauthorized")
    logger.info("SePay webhook authorization passed for request from %s", request.client.host if request.client else "unknown")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload structure")

    if not settings.sepay_api_key:
        logger.warning("SePay API key is not configured; rejecting request")
        raise HTTPException(status_code=503, detail="Payment provider is not configured")

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid payload structure")

    transaction_id_raw = _payload_value(data, "id") or _payload_value(data, "transaction_id") or _payload_value(data, "transactionId")
    transaction_id = str(transaction_id_raw) if transaction_id_raw is not None else None
    content = _payload_value(data, "content") or _payload_value(data, "des") or _payload_value(data, "reference")
    code = _payload_value(data, "code")
    amount_value = _payload_value(data, "transferAmount") or _payload_value(data, "amount") or _payload_value(data, "transfer_amount")
    reference_code = code if isinstance(code, str) and code.strip() else _extract_reference_code(content)

    logger.info(
        "SePay payload decoded: transaction_id=%s reference_code=%s amount=%s code=%s content=%s",
        transaction_id,
        reference_code,
        amount_value,
        code,
        content,
    )

    if not transaction_id:
        raise HTTPException(status_code=400, detail="Missing transaction id")

    try:
        amount = _normalize_amount(amount_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # SePay treats 200/201 with body {"success": true} as success.
    # Duplicate transactions, amount mismatches, and "manual review" cases are handled
    # intentionally here and do not warrant retries; they are logical outcomes, not transport failures.
    session_factory = create_session_factory(settings.database_url)
    session = session_factory()
    try:
        existing_payment = session.scalar(select(Payment).where(Payment.transaction_id == transaction_id))
        if existing_payment is not None:
            logger.info("Ignoring duplicate SePay webhook for transaction_id=%s (order_id=%s)", transaction_id, existing_payment.order_id)
            return JSONResponse({"success": True}, status_code=200)

        pending_payments = list(session.scalars(select(Payment).where(Payment.status == "pending")).all())
        payment = None
        order = None
        logger.info("Checking %s pending payment records for reference %s", len(pending_payments), reference_code)

        for candidate in pending_payments:
            metadata = candidate.raw_webhook_data or {}
            if metadata.get("reference_code") == reference_code:
                payment = candidate
                order = candidate.order
                logger.info("Found pending payment %s for order %s by reference_code match", candidate.id, order.id)
                break

        if order is None:
            recent_orders = _recent_pending_orders_by_amount(session, amount)
            if len(recent_orders) == 1:
                logger.warning(
                    "SePay webhook received amount-only match for order %s; manual review required. Payload=%s",
                    recent_orders[0].id,
                    payload,
                )
                message = (
                    "⚠️ SePay manual review required\n\n"
                    f"Order #{recent_orders[0].id} has a pending payment that matches the transferred amount, "
                    "but the transfer content did not include a valid order reference.\n\n"
                    f"Payload: {payload}"
                )
                background_tasks.add_task(_notify_admins, message)
                _save_unmatched_webhook(
                    session,
                    reason="no_pending_order_match",
                    transaction_id=transaction_id,
                    reference_code=reference_code,
                    amount=amount,
                    expected_amount=None,
                    payload=payload,
                    order_id=recent_orders[0].id,
                    message=message,
                )
                session.commit()
                return JSONResponse({"success": True}, status_code=200)

            logger.warning("SePay webhook payload did not match any pending order. Payload=%s", payload)
            message = (
                "⚠️ SePay manual review required\n\n"
                "No pending order matched the transferred reference or amount.\n\n"
                f"Payload: {payload}"
            )
            _save_unmatched_webhook(
                session,
                reason="no_pending_order_match",
                transaction_id=transaction_id,
                reference_code=reference_code,
                amount=amount,
                expected_amount=None,
                payload=payload,
                message=message,
            )
            session.commit()
            background_tasks.add_task(_notify_admins, message)
            return JSONResponse({"success": True}, status_code=200)

        if order.amount != amount:
            logger.warning(
                "SePay webhook amount mismatch for order %s. Expected %s, got %s.",
                order.id,
                order.amount,
                amount,
            )
            message = (
                "⚠️ SePay amount mismatch requires review\n\n"
                f"Order #{order.id} expected amount {order.amount}, but the webhook reported {amount}.\n\n"
                f"Payload: {payload}"
            )
            _save_unmatched_webhook(
                session,
                reason="amount_mismatch",
                transaction_id=transaction_id,
                reference_code=reference_code,
                amount=amount,
                expected_amount=order.amount,
                payload=payload,
                order_id=order.id,
                message=message,
            )
            session.commit()
            background_tasks.add_task(_notify_admins, message)
            return JSONResponse({"success": True}, status_code=200)

        payment.status = "paid"
        payment.transaction_id = transaction_id
        payment.raw_webhook_data = payload

        try:
            order_service = OrderService()
            order_service.mark_paid(session, order.id, transaction_id)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to mark order %s as paid after SePay webhook", order.id)
            raise HTTPException(status_code=500, detail="Failed to update order status")

        background_tasks.add_task(_deliver_order, order.id)
        return JSONResponse({"success": True}, status_code=200)
    except Exception:
        session.rollback()
        logger.exception("Error while processing SePay webhook")
        raise HTTPException(status_code=500, detail="Unable to process webhook")
    finally:
        session.close()
