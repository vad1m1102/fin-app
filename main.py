import asyncio
import html
import logging
import os
import socket
import sys
import uuid
import time
from typing import Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile
)
from datetime import datetime

import database
from config import BOT_TOKEN
from excel_exporter import export_transactions_to_excel
from keyboards import (
    get_main_menu,
    get_type_selection_keyboard,
    get_category_keyboard,
    get_categories_management_keyboard,
    get_delete_transaction_keyboard,
    get_stats_keyboard,
    DEFAULT_EXPENSE_CATEGORIES,
    DEFAULT_INCOME_CATEGORIES
)
from parser import parse_amount_and_description

# Логування
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Тимчасове сховище для чернеток перед вибором категорії: {draft_id: {...}}
pending_drafts: Dict[str, Dict[str, Any]] = {}

# Очікування введення назви нової категорії: {user_id: {"draft_id": Optional[str], "type": str}}
waiting_custom_category: Dict[int, Dict[str, Any]] = {}


def cleanup_old_drafts():
    """Видаляє чернетки, створені понад 30 хвилин тому."""
    now = time.time()
    expired = [k for k, v in pending_drafts.items() if now - v.get("created_at", now) > 1800]
    for k in expired:
        pending_drafts.pop(k, None)


def format_stats_message(stats: dict) -> str:
    period_title = stats["period_title"]
    income = stats["income"]
    expense = stats["expense"]
    balance = stats["balance"]
    expense_cats = stats["expense_categories"]
    income_cats = stats["income_categories"]

    lines = [
        f"📊 <b>Статистика: {period_title}</b>\n",
        f"🟢 <b>Доходи:</b> <code>{income:,.2f} грн</code>".replace(",", " "),
        f"🔴 <b>Витрати:</b> <code>{expense:,.2f} грн</code>".replace(",", " "),
        f"💵 <b>Баланс:</b> <code>{'+' if balance > 0 else ''}{balance:,.2f} грн</code>\n".replace(",", " ")
    ]

    if not expense_cats and not income_cats:
        lines.append("<i>ℹ️ За цей період операцій ще не було.</i>")
        return "\n".join(lines)

    if expense_cats:
        lines.append("📉 <b>Витрати за категоріями:</b>")
        for cat, total in expense_cats:
            pct = (total / expense * 100) if expense > 0 else 0
            formatted_total = f"{total:,.2f} грн".replace(",", " ")
            lines.append(f"• {cat}: <b>{formatted_total}</b> (<code>{pct:.1f}%</code>)")
        lines.append("")

    if income_cats:
        lines.append("📈 <b>Доходи за категоріями:</b>")
        for cat, total in income_cats:
            pct = (total / income * 100) if income > 0 else 0
            formatted_total = f"{total:,.2f} грн".replace(",", " ")
            lines.append(f"• {cat}: <b>{formatted_total}</b> (<code>{pct:.1f}%</code>)")

    return "\n".join(lines)


def format_recent_transactions(transactions: list) -> str:
    if not transactions:
        return "ℹ️ У вас ще немає збережених операцій."

    lines = ["🕒 <b>Останні операції:</b>\n"]
    for tx in transactions:
        sign = "-" if tx["type"] == "expense" else "+"
        icon = "🔴" if tx["type"] == "expense" else "🟢"
        desc_text = html.escape(tx["description"]) if tx.get("description") else ""
        desc = f" ({desc_text})" if desc_text else ""
        date_time = tx["created_at"]
        formatted_amount = f"{tx['amount']:,.2f} грн".replace(",", " ")
        lines.append(
            f"{icon} <b>{sign}{formatted_amount}</b> — {html.escape(tx['category'])}{desc}\n"
            f"   <i>📅 {date_time}</i>\n"
        )
    return "\n".join(lines)


dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: Message):
    welcome_text = (
        "👋 <b>Привіт! Я твій помічник для обліку фінансів.</b>\n\n"
        "💡 <b>Як додати запис?</b>\n"
        "Просто напиши мені суму та опис у будь-якому форматі:\n"
        "• <code>150 кава</code>\n"
        "• <code>таксі 230</code>\n"
        "• <code>15000 зарплата</code>\n"
        "• <code>250.50 Сільпо</code>\n\n"
        "Після цього обери кнопкою категорію витрати або доходу.\n\n"
        "📊 Скористайся кнопками меню нижче для перегляду статистики!"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu())


@dp.message(F.text == "ℹ️ Допомога")
@dp.message(Command("help"))
async def handle_help(message: Message):
    help_text = (
        "ℹ️ <b>Як користуватися ботом:</b>\n\n"
        "1️⃣ <b>Додавання операції:</b>\n"
        "Напишіть повідомлення з сумою та назвою:\n"
        "• <code>150 кава</code>\n"
        "• <code>Сільпо 450.50</code>\n"
        "• <code>8000 фріланс</code>\n\n"
        "2️⃣ <b>Вибір категорії:</b>\n"
        "Оберіть категорію зі списку або натисніть <b>➕ Своя категорія</b>, щоб створити власну!\n\n"
        "3️⃣ <b>Керування категоріями:</b>\n"
        "Натисніть <b>🏷️ Мої категорії</b>, щоб переглянути або видалити створені власні категорії.\n\n"
        "4️⃣ <b>Статистика та експорт:</b>\n"
        "• <b>📊 Статистика</b> — звіт за день, тиждень, місяць або рік.\n"
        "• <b>📥 Експорт в Excel</b> — завантажити таблицю витрат і доходів у форматі .xlsx."
    )
    await message.answer(help_text, reply_markup=get_main_menu())


@dp.message(F.text == "📊 Статистика")
@dp.message(Command("stats"))
async def handle_stats(message: Message):
    stats = database.get_stats(message.from_user.id, "month")
    text = format_stats_message(stats)
    await message.answer(text, reply_markup=get_stats_keyboard())


@dp.message(F.text == "🕒 Останні операції")
@dp.message(Command("recent"))
async def handle_recent(message: Message):
    recent = database.get_recent_transactions(message.from_user.id, limit=5)
    text = format_recent_transactions(recent)
    
    keyboard = None
    if recent:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑️ Видалити останню операцію", callback_data="del_last")]
            ]
        )
    await message.answer(text, reply_markup=keyboard)


@dp.message(F.text == "📥 Експорт в Excel")
@dp.message(Command("export"))
async def handle_export(message: Message):
    transactions = database.get_all_transactions(message.from_user.id)
    if not transactions:
        await message.answer("ℹ️ У вас ще немає збережених операцій для експорту.")
        return

    await message.answer("⏳ Формую файл Excel...")
    excel_stream = export_transactions_to_excel(transactions)
    filename = f"finance_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    file_bytes = excel_stream.getvalue()

    document = BufferedInputFile(file_bytes, filename=filename)
    await message.answer_document(
        document=document,
        caption=f"📁 <b>Ваша фінансова таблиця</b>\n"
                f"Усього операцій: <b>{len(transactions)}</b>"
    )


# Обробка вибору періоду статистики
@dp.callback_query(F.data.startswith("stats:"))
async def handle_stats_callback(callback: CallbackQuery):
    period = callback.data.split(":")[1]
    stats = database.get_stats(callback.from_user.id, period)
    text = format_stats_message(stats)

    try:
        await callback.message.edit_text(text, reply_markup=get_stats_keyboard())
    except Exception:
        pass
    await callback.answer()


# Обробка вибору типу (Витрата / Дохід)
@dp.callback_query(F.data.startswith("type:"))
async def handle_type_callback(callback: CallbackQuery):
    cleanup_old_drafts()
    _, draft_id, tx_type = callback.data.split(":")
    
    draft = pending_drafts.get(draft_id)
    if not draft:
        await callback.answer("⏳ Час вибору минув, введіть суму знову.", show_alert=True)
        return

    draft["type"] = tx_type
    type_name = "🔴 Витрата" if tx_type == "expense" else "🟢 Дохід"
    safe_desc = html.escape(draft['description']) if draft['description'] else ""
    desc_str = f" ({safe_desc})" if safe_desc else ""

    text = (
        f"<b>{type_name}:</b> {draft['amount']:,.2f} грн{desc_str}\n\n"
        f"Оберіть категорію:"
    ).replace(",", " ")

    categories = database.get_user_categories(callback.from_user.id, tx_type)
    await callback.message.edit_text(text, reply_markup=get_category_keyboard(draft_id, tx_type, categories))
    await callback.answer()


# Обробка кнопки "Назад" до вибору типу
@dp.callback_query(F.data.startswith("back:"))
async def handle_back_callback(callback: CallbackQuery):
    draft_id = callback.data.split(":")[1]
    draft = pending_drafts.get(draft_id)
    if not draft:
        await callback.answer("⏳ Час вибору минув, введіть суму знову.", show_alert=True)
        return

    safe_desc = html.escape(draft['description']) if draft['description'] else ""
    desc_str = f"<b>Опис:</b> {safe_desc}\n" if safe_desc else ""
    text = (
        f"💰 <b>Сума:</b> {draft['amount']:,.2f} грн\n"
        f"{desc_str}\n"
        f"Оберіть тип операції:"
    ).replace(",", " ")

    await callback.message.edit_text(text, reply_markup=get_type_selection_keyboard(draft_id))
    await callback.answer()


# Обробка збереження категорії
@dp.callback_query(F.data.startswith("cat:"))
async def handle_category_callback(callback: CallbackQuery):
    cleanup_old_drafts()
    _, draft_id, cat_idx_str = callback.data.split(":")
    cat_idx = int(cat_idx_str)

    draft = pending_drafts.pop(draft_id, None)
    if not draft:
        await callback.answer("⏳ Час вибору минув, введіть суму знову.", show_alert=True)
        return

    tx_type = draft["type"]
    categories = database.get_user_categories(callback.from_user.id, tx_type)
    if 0 <= cat_idx < len(categories):
        category = categories[cat_idx]
    else:
        category = "Інше"

    tx_id = database.add_transaction(
        user_id=callback.from_user.id,
        amount=draft["amount"],
        tx_type=tx_type,
        category=category,
        description=draft["description"]
    )

    type_title = "🔴 Витрату" if tx_type == "expense" else "🟢 Дохід"
    safe_desc = html.escape(draft['description']) if draft['description'] else ""
    desc_line = f"📝 <b>Опис:</b> {safe_desc}\n" if safe_desc else ""
    
    text = (
        f"✅ <b>{type_title} успішно збережено!</b>\n\n"
        f"💰 <b>Сума:</b> {draft['amount']:,.2f} грн\n"
        f"📁 <b>Категорія:</b> {html.escape(category)}\n"
        f"{desc_line}"
    ).replace(",", " ")

    await callback.message.edit_text(text, reply_markup=get_delete_transaction_keyboard(tx_id))
    await callback.answer("Збережено!")


# Скасування додавання операції
@dp.callback_query(F.data.startswith("cancel:"))
async def handle_cancel_callback(callback: CallbackQuery):
    draft_id = callback.data.split(":")[1]
    pending_drafts.pop(draft_id, None)
    waiting_custom_category.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Додавання операції скасовано.")
    await callback.answer()


# Натискання "➕ Своя категорія" під час створення операції
@dp.callback_query(F.data.startswith("newcat:"))
async def handle_new_cat_callback(callback: CallbackQuery):
    _, draft_id, tx_type = callback.data.split(":")
    waiting_custom_category[callback.from_user.id] = {
        "draft_id": draft_id,
        "type": tx_type
    }
    type_name = "витрат" if tx_type == "expense" else "доходів"
    
    text = (
        f"✍️ <b>Введіть назву вашої категорії для {type_name}:</b>\n\n"
        f"<i>Наприклад: Книги, Сім'я, Косметика...</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"back:{draft_id}")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# Меню перегляду та керування категоріями
@dp.message(F.text == "🏷️ Мої категорії")
@dp.message(Command("categories"))
async def handle_categories_menu(message: Message):
    custom_categories = database.get_custom_categories(message.from_user.id)
    
    lines = [
        "🏷️ <b>Керування категоріями</b>\n",
        "Бот уже має великий набір стандартних категорій.",
        "Тут ви можете створювати власні унікальні категорії або видаляти їх.\n"
    ]

    if custom_categories:
        lines.append("✨ <b>Ваші додані категорії:</b>")
        for cat in custom_categories:
            icon = "🔴" if cat["type"] == "expense" else "🟢"
            type_str = "Витрата" if cat["type"] == "expense" else "Дохід"
            lines.append(f"• {icon} <b>{html.escape(cat['name'])}</b> ({type_str})")
        lines.append("\n<i>Натисніть кнопку нижче, щоб видалити або додати:</i>")
    else:
        lines.append("<i>У вас поки немає власних доданих категорій (використовуються стандартні).</i>")

    await message.answer(
        "\n".join(lines),
        reply_markup=get_categories_management_keyboard(custom_categories)
    )


# Додавання категорії з меню категорій
@dp.callback_query(F.data.startswith("addcat:"))
async def handle_add_cat_menu_callback(callback: CallbackQuery):
    tx_type = callback.data.split(":")[1]
    waiting_custom_category[callback.from_user.id] = {
        "draft_id": None,
        "type": tx_type
    }
    type_name = "витрат" if tx_type == "expense" else "доходів"
    await callback.message.answer(
        f"✍️ <b>Введіть назву нової категорії для {type_name}:</b>\n\n"
        f"<i>(Надішліть текстом у чат)</i>"
    )
    await callback.answer()


# Видалення власної категорії
@dp.callback_query(F.data.startswith("delcat:"))
async def handle_del_cat_callback(callback: CallbackQuery):
    cat_id = int(callback.data.split(":")[1])
    database.delete_custom_category(callback.from_user.id, cat_id)
    
    # Оновлюємо перелік
    custom_categories = database.get_custom_categories(callback.from_user.id)
    lines = [
        "🏷️ <b>Керування категоріями</b>\n",
        "Категорію видалено!\n"
    ]
    if custom_categories:
        lines.append("✨ <b>Ваші додані категорії:</b>")
        for cat in custom_categories:
            icon = "🔴" if cat["type"] == "expense" else "🟢"
            type_str = "Витрата" if cat["type"] == "expense" else "Дохід"
            lines.append(f"• {icon} <b>{html.escape(cat['name'])}</b> ({type_str})")
    else:
        lines.append("<i>У вас немає власних категорій.</i>")

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=get_categories_management_keyboard(custom_categories)
        )
    except Exception:
        pass
    await callback.answer("Категорію видалено")


# Видалення конкретного запису
@dp.callback_query(F.data.startswith("del:"))
async def handle_delete_callback(callback: CallbackQuery):
    tx_id = int(callback.data.split(":")[1])
    success = database.delete_transaction(callback.from_user.id, tx_id)
    if success:
        await callback.message.edit_text("🗑️ Запис видалено.")
        await callback.answer("Видалено!")
    else:
        await callback.answer("Запис не знайдено або вже видалено.", show_alert=True)


# Видалення останньої операції зі списку
@dp.callback_query(F.data == "del_last")
async def handle_delete_last_callback(callback: CallbackQuery):
    deleted = database.delete_last_transaction(callback.from_user.id)
    if deleted:
        safe_desc = html.escape(deleted['description']) if deleted['description'] else ""
        desc = f" ({safe_desc})" if safe_desc else ""
        safe_cat = html.escape(deleted['category'])
        await callback.message.edit_text(
            f"🗑️ Видалено останню операцію:\n"
            f"<b>{deleted['amount']:,.2f} грн</b> — {safe_cat}{desc}".replace(",", " ")
        )
        await callback.answer("Видалено!")
    else:
        await callback.answer("Немає записів для видалення.", show_alert=True)


# Обробка текстових повідомлень користувача
@dp.message(F.text)
async def handle_text_message(message: Message):
    # 1. Перевірка: чи очікується введення назви нової категорії
    if message.from_user.id in waiting_custom_category:
        wait_info = waiting_custom_category.pop(message.from_user.id)
        raw_name = message.text.strip()

        if len(raw_name) > 35:
            waiting_custom_category[message.from_user.id] = wait_info
            await message.answer("⚠️ Назва занадто довга (максимум 30 символів). Спробуйте коротшу:")
            return

        tx_type = wait_info["type"]
        new_category = raw_name
        database.add_custom_category(message.from_user.id, tx_type, new_category)

        draft_id = wait_info.get("draft_id")
        draft = pending_drafts.pop(draft_id, None) if draft_id else None

        if draft:
            # Якщо категорія додавалася прямо під час запису операції — зберігаємо операцію
            tx_id = database.add_transaction(
                user_id=message.from_user.id,
                amount=draft["amount"],
                tx_type=tx_type,
                category=new_category,
                description=draft["description"]
            )
            type_title = "🔴 Витрату" if tx_type == "expense" else "🟢 Дохід"
            safe_desc = html.escape(draft['description']) if draft['description'] else ""
            desc_line = f"📝 <b>Опис:</b> {safe_desc}\n" if safe_desc else ""
            
            text = (
                f"✨ Створено нову категорію: <b>{html.escape(new_category)}</b>\n\n"
                f"✅ <b>{type_title} успішно збережено!</b>\n\n"
                f"💰 <b>Сума:</b> {draft['amount']:,.2f} грн\n"
                f"📁 <b>Категорія:</b> {html.escape(new_category)}\n"
                f"{desc_line}"
            ).replace(",", " ")
            await message.answer(text, reply_markup=get_delete_transaction_keyboard(tx_id))
        else:
            type_name = "витрат" if tx_type == "expense" else "доходів"
            await message.answer(
                f"✅ Категорію <b>{html.escape(new_category)}</b> успішно додано до вашого списку {type_name}!\n"
                f"Тепер вона буде відображатися кнопкою при внесенні коштів.",
                reply_markup=get_main_menu()
            )
        return

    # 2. Якщо це звичайне повідомлення — розпізнаємо суму та опис
    parsed = parse_amount_and_description(message.text)
    if not parsed:
        await message.answer(
            "🤔 Не вдалося розпізнати суму.\n\n"
            "Введіть суму та назву, наприклад:\n"
            "• <code>150 кава</code>\n"
            "• <code>350 таксі</code>\n"
            "• <code>15000 зарплата</code>"
        )
        return

    amount, description = parsed
    draft_id = uuid.uuid4().hex[:8]

    pending_drafts[draft_id] = {
        "user_id": message.from_user.id,
        "amount": amount,
        "description": description,
        "created_at": time.time()
    }

    safe_desc = html.escape(description) if description else ""
    desc_str = f"📝 <b>Опис:</b> {safe_desc}\n" if safe_desc else ""
    text = (
        f"💰 <b>Сума:</b> {amount:,.2f} грн\n"
        f"{desc_str}\n"
        f"Оберіть тип операції:"
    ).replace(",", " ")

    await message.answer(text, reply_markup=get_type_selection_keyboard(draft_id))


def detect_proxy() -> Optional[str]:
    """Визначає, чи потрібно використовувати проксі (наприклад, для PythonAnywhere)."""
    # 1. Пряма вказівка в .env або змінних оточення
    env_proxy = os.getenv("PROXY_URL")
    if env_proxy:
        return env_proxy

    # 2. Перевірка наявності proxy.server (специфічно для безкоштовного тарифу PythonAnywhere)
    try:
        socket.gethostbyname("proxy.server")
        return "http://proxy.server:3128"
    except Exception:
        pass

    # 3. Перевірка змінних оточення проксі
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        val = os.getenv(key)
        if val:
            return val

    # 4. Перевірка шляхів PythonAnywhere
    if os.path.exists("/etc/pythonanywhere") or "pythonanywhere" in os.environ.get("HOSTNAME", "").lower():
        return "http://proxy.server:3128"

    return None


async def main():
    database.init_db()

    if not BOT_TOKEN:
        print("\n" + "=" * 60)
        print("❌ ПОМИЛКА: Не вказано токен бота!")
        print("Будь ласка, створіть файл .env та додайте свій токен:")
        print("BOT_TOKEN=ваш_токен_від_BotFather")
        print("=" * 60 + "\n")
        return

    proxy = detect_proxy()
    session = None
    if proxy:
        print(f"🌐 Знайдено проксі: {proxy}")
        try:
            session = AiohttpSession(proxy=proxy)
        except Exception as e:
            print(f"\n❌ Помилка ініціалізації проксі: {e}")
            print("👉 Обов'язково виконайте в консолі: pip install --user aiohttp-socks\n")
            return
    else:
        print("🌐 Пряме підключення (без проксі)")

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    print("🚀 Бот запущений та готовий до роботи!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот зупинений.")
