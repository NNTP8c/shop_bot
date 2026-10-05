from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import navigation
from app.utils.i18n import t


def products(products, language: str = "en") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{product.type} x{product.quantity} - {product.price:,.0f}₫", callback_data=f"product:{product.id}")] for product in products]
    rows.append(navigation(language))
    return InlineKeyboardMarkup(rows)


def confirm_purchase(order_id: str, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ " + ("Tôi đã thanh toán" if language == "vi" else "I have completed payment"), callback_data=f"confirm:{order_id}"),
            InlineKeyboardButton("❌ " + t(language, "cancel_order"), callback_data=f"cancel_order:{order_id}"),
        ],
        navigation(language),
    ])
