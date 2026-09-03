from __future__ import annotations

from telegram import ReplyKeyboardMarkup


MAIN_MENU = {
    "full": "LENGKAP",
    "config": "📋 CONFIG",
    "report": "📄 REPORT",
    "sto": "📡 STO",
    "orders": "📦 Orderanku",
    "profile": "👤 Profile",
    "settings": "⚙ Settings",
}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [MAIN_MENU["full"]],
            [MAIN_MENU["config"], MAIN_MENU["report"], MAIN_MENU["sto"]],
            [MAIN_MENU["orders"]],
            [MAIN_MENU["profile"], MAIN_MENU["settings"]],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Pilih menu",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
