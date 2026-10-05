from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import navigation
from app.utils.i18n import t


def admin_menu(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(language, "inventory"), callback_data="admin:inventory"), InlineKeyboardButton("Thêm sản phẩm" if language == "vi" else "Add Product", callback_data="admin:add")],
        [InlineKeyboardButton(t(language, "admin_orders"), callback_data="admin:orders"), InlineKeyboardButton("Thống kê" if language == "vi" else "Statistics", callback_data="admin:inventory")],
        navigation(language),
    ])


def admin_orders_menu(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Tìm theo mã đơn hàng" if language == "vi" else "Find by order ID", callback_data="admin:find_order")],
        [InlineKeyboardButton("Bảng quản trị" if language == "vi" else "Admin Panel", callback_data="admin")],
        navigation(language),
    ])
