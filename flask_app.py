import asyncio
import os
import sys
from flask import Flask, request, jsonify

# Забезпечуємо знаходження модулів проєкту в sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import database
from config import BOT_TOKEN
from main import create_bot, process_update

app = Flask(__name__)

# Ініціалізація бази даних при старті веб-сервера
database.init_db()


@app.route("/")
def index():
    return (
        "<!DOCTYPE html>"
        "<html lang='uk'><head><meta charset='utf-8'><title>Fin Tracker Bot</title>"
        "<style>body{font-family:sans-serif;padding:40px;background:#f5f7fa;color:#333;text-align:center;}"
        ".card{background:white;padding:30px;border-radius:12px;max-width:500px;margin:auto;box-shadow:0 4px 12px rgba(0,0,0,0.1);}"
        "a{display:inline-block;margin:10px;padding:10px 20px;background:#0088cc;color:white;text-decoration:none;border-radius:6px;font-weight:bold;}"
        "a.danger{background:#d9534f;}"
        "</style></head><body>"
        "<div class='card'>"
        "<h2>🚀 Fin Tracker Webhook Bot</h2>"
        "<p>Статус: <b>Веб-сервер активний і працює 24/7</b></p>"
        "<hr/>"
        "<p>Керування вебхуком Telegram:</p>"
        "<a href='/set_webhook'>✅ Встановити Webhook</a><br/>"
        "<a href='/webhook_info'>ℹ️ Перевірити статус Webhook</a><br/>"
        "<a href='/delete_webhook' class='danger'>🗑️ Видалити Webhook</a>"
        "</div></body></html>"
    ), 200


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    """Приймає та обробляє оновлення від Telegram."""
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_json()
        if json_data:
            asyncio.run(process_update(json_data))
        return "OK", 200
    return "Forbidden", 403


@app.route("/set_webhook", methods=["GET"])
def set_webhook_route():
    """Встановлює Webhook у Telegram за 1 клік у браузері."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    # Визначаємо хост PythonAnywhere або поточний домен
    host = request.headers.get("X-Forwarded-Host", request.host)
    webhook_url = f"https://{host}/webhook/{BOT_TOKEN}"

    async def _set():
        bot = create_bot()
        try:
            res = await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            info = await bot.get_webhook_info()
            return res, info
        finally:
            await bot.session.close()

    try:
        res, info = asyncio.run(_set())
        return (
            f"<h2>✅ Webhook успішно встановлено!</h2>"
            f"<p><b>URL:</b> {webhook_url}</p>"
            f"<p><b>Telegram відповідь:</b> {res}</p>"
            f"<p><b>Статус у Telegram:</b> {info.url}</p>"
            f"<br/><a href='/'>⬅️ Назад</a>"
        ), 200
    except Exception as e:
        return (
            f"<h2>❌ Помилка встановлення Webhook:</h2>"
            f"<p>{e}</p>"
            f"<br/><a href='/'>⬅️ Назад</a>"
        ), 500


@app.route("/webhook_info", methods=["GET"])
def webhook_info_route():
    """Показує поточний статус вебхука в Telegram."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    async def _info():
        bot = create_bot()
        try:
            return await bot.get_webhook_info()
        finally:
            await bot.session.close()

    try:
        info = asyncio.run(_info())
        return (
            f"<h2>ℹ️ Інформація про Webhook</h2>"
            f"<p><b>Поточний URL:</b> {info.url or 'Не встановлено'}</p>"
            f"<p><b>Очікує обробки оновлень:</b> {info.pending_update_count}</p>"
            f"<p><b>Остання помилка (якщо є):</b> {info.last_error_message or 'Немає'}</p>"
            f"<br/><a href='/'>⬅️ Назад</a>"
        ), 200
    except Exception as e:
        return f"<h2>❌ Помилка: {e}</h2><br/><a href='/'>⬅️ Назад</a>", 500


@app.route("/delete_webhook", methods=["GET"])
def delete_webhook_route():
    """Видаляє Webhook (якщо потрібно повернутися до polling)."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    async def _delete():
        bot = create_bot()
        try:
            return await bot.delete_webhook()
        finally:
            await bot.session.close()

    try:
        res = asyncio.run(_delete())
        return (
            f"<h2>🗑️ Webhook видалено!</h2>"
            f"<p>Telegram відповідь: {res}</p>"
            f"<br/><a href='/'>⬅️ Назад</a>"
        ), 200
    except Exception as e:
        return f"<h2>❌ Помилка: {e}</h2><br/><a href='/'>⬅️ Назад</a>", 500


if __name__ == "__main__":
    # Локальний запуск сервера розробки
    app.run(port=5000, debug=True)

