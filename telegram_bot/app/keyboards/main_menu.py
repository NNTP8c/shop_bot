from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.i18n import t

def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("English", callback_data="language:en"),
        InlineKeyboardButton("Tiếng Việt", callback_data="language:vi"),
    ]])


def main_menu(is_admin: bool = False, language: str = "en") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(language, "shop"), callback_data="shop")],
        [InlineKeyboardButton(t(language, "orders"), callback_data="orders"), InlineKeyboardButton(t(language, "account"), callback_data="account")],
        [InlineKeyboardButton(t(language, "help"), callback_data="help")],
        [InlineKeyboardButton(t(language, "change_language"), callback_data="change_language")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(t(language, "admin_panel"), callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def navigation(language: str = "en") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(t(language, "back"), callback_data="main"), InlineKeyboardButton(t(language, "main_menu"), callback_data="main")]
