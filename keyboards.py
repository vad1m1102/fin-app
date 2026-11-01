from typing import List, Dict, Any, Optional
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)

DEFAULT_EXPENSE_CATEGORIES = [
    "🛒 Продукти",
    "☕ Кафе / Ресторани",
    "🚕 Транспорт / Таксі",
    "⛽ Пальне / Авто",
    "🏠 Житло / Комуналка",
    "🛍️ Покупки / Одяг",
    "💊 Здоров'я / Аптека",
    "🏋️ Спорт / Фітнес",
    "🎮 Розваги / Відпочинок",
    "📱 Зв'язок / Інтернет",
    "🎬 Підписки / Сервіси",
    "🐾 Тварини / Зоо",
    "📚 Навчання / Книги",
    "🎁 Подарунки",
    "📦 Інше"
]

DEFAULT_INCOME_CATEGORIES = [
    "💼 Зарплата / Аванс",
    "💻 Фріланс / Проєкти",
    "📈 Інвестиції / Дивіденди",
    "🎁 Подарунок",
    "💳 Кешбек / Бонуси",
    "🏢 Оренда / Нерухомість",
    "🔄 Повернення боргу",
    "💰 Інший дохід"
]

# Для зворотної сумісності
EXPENSE_CATEGORIES = DEFAULT_EXPENSE_CATEGORIES
INCOME_CATEGORIES = DEFAULT_INCOME_CATEGORIES


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🕒 Останні операції")],
            [KeyboardButton(text="🏷️ Мої категорії"), KeyboardButton(text="📥 Експорт в Excel")],
            [KeyboardButton(text="ℹ️ Допомога")]
        ],
        resize_keyboard=True
    )


def get_type_selection_keyboard(draft_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔴 Витрата", callback_data=f"type:{draft_id}:expense"),
                InlineKeyboardButton(text="🟢 Дохід", callback_data=f"type:{draft_id}:income")
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel:{draft_id}")
            ]
        ]
    )


def get_category_keyboard(draft_id: str, tx_type: str, categories: List[str]):
    buttons = []
    
    # Розміщуємо по 2 кнопки в ряд
    row = []
    for idx, cat in enumerate(categories):
        row.append(InlineKeyboardButton(text=cat, callback_data=f"cat:{draft_id}:{idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Кнопка додавання своєї категорії
    buttons.append([
        InlineKeyboardButton(text="➕ Своя категорія", callback_data=f"newcat:{draft_id}:{tx_type}")
    ])

    # Кнопки повернення назад або скасування
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{draft_id}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel:{draft_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_categories_management_keyboard(custom_categories: List[Dict[str, Any]]):
    buttons = []
    if custom_categories:
        for cat in custom_categories:
            icon = "🔴" if cat["type"] == "expense" else "🟢"
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗑️ Видалити: {icon} {cat['name']}",
                    callback_data=f"delcat:{cat['id']}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="➕ Додати витрату", callback_data="addcat:expense"),
        InlineKeyboardButton(text="➕ Додати дохід", callback_data="addcat:income")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_transaction_keyboard(tx_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Видалити цей запис", callback_data=f"del:{tx_id}")]
        ]
    )


def get_stats_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сьогодні", callback_data="stats:day"),
                InlineKeyboardButton(text="📆 Цього тижня", callback_data="stats:week")
            ],
            [
                InlineKeyboardButton(text="🗓️ Цього місяця", callback_data="stats:month"),
                InlineKeyboardButton(text="📈 Цього року", callback_data="stats:year")
            ]
        ]
    )
