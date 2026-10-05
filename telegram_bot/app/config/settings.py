from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


def _admin_ids(value: str) -> frozenset[int]:
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///shop_bot.db")
    admin_ids: frozenset[int] = _admin_ids(os.getenv("ADMIN_IDS", ""))
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "manual")
    currency: str = os.getenv("CURRENCY", "VND")
    sepay_api_key: str = os.getenv("SEPAY_API_KEY", "")
    sepay_bank_account_number: str = os.getenv("SEPAY_BANK_ACCOUNT_NUMBER", "")
    sepay_bank_code: str = os.getenv("SEPAY_BANK_CODE", "")
    sepay_template: str = os.getenv("SEPAY_TEMPLATE", "img")
    sepay_base_url: str = os.getenv("SEPAY_BASE_URL", "https://qr.sepay.vn")
    sepay_webhook_secret: str = os.getenv("SEPAY_WEBHOOK_SECRET", "")


settings = Settings()
