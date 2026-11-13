import asyncio
import json
import logging
import os
import sys
import threading
import urllib.request
from flask import Flask, request, jsonify

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import database
from config import BOT_TOKEN
from main import process_update

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 1. Ініціалізація бази даних при старті веб-сервера
database.init_db()

# 2. Постійний фоновий цикл подій для Keep-Alive з'єднань із Telegram
_loop = asyncio.new_event_loop()


def _run_bg_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


_bg_thread = threading.Thread(target=_run_bg_loop, args=(_loop,), daemon=True)
_bg_thread.start()


@app.route("/")
def index():
    return (
        "<!DOCTYPE html>"
        "<html lang='uk'><head><meta charset='utf-8'><title>Fin Tracker Bot</title>"
        "<style>body{font-family:sans-serif;padding:40px;background:#f5f7fa;color:#333;text-align:center;}"
        ".card{background:white;padding:30px;border-radius:12px;max-width:520px;margin:auto;box-shadow:0 4px 12px rgba(0,0,0,0.1);}"
        "a{display:inline-block;margin:10px;padding:12px 20px;background:#0088cc;color:white;text-decoration:none;border-radius:6px;font-weight:bold;}"
        "a.danger{background:#d9534f;}"
        ".badge{display:inline-block;background:#28a745;color:white;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:bold;}"
        "</style></head><body>"
        "<div class='card'>"
        "<h2>⚡ Fin Tracker Bot <span class='badge'>Turbo Keep-Alive</span></h2>"
        "<p>Статус: <b>Веб-сервер активний і працює 24/7</b></p>"
        "<p><small>Миттєва відправка кнопок та постійний пул мережевих з'єднань</small></p>"
        "<hr/>"
        "<p>Керування вебхуком Telegram:</p>"
        "<a href='/set_webhook'>✅ Встановити Webhook</a><br/>"
        "<a href='/webhook_info'>ℹ️ Перевірити статус Webhook</a><br/>"
        "<a href='/delete_webhook' class='danger'>🗑️ Видалити Webhook</a>"
        "</div></body></html>"
    ), 200


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    """Приймає та миттєво обробляє оновлення від Telegram."""
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_json(silent=True)
        if json_data:
            future = asyncio.run_coroutine_threadsafe(process_update(json_data), _loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                app.logger.error(f"Помилка або таймаут обробки вебхука: {e}")
        return "OK", 200
    return "Forbidden", 403


@app.route("/set_webhook", methods=["GET"])
def set_webhook_route():
    """Встановлює Webhook у Telegram за 1 клік."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    host = request.headers.get("X-Forwarded-Host", request.host)
    webhook_url = f"https://{host}/webhook/{BOT_TOKEN}"
    telegram_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}&drop_pending_updates=True"

    try:
        req = urllib.request.Request(telegram_api_url)
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("ok"):
                return (
                    f"<h2>✅ Webhook успішно встановлено!</h2>"
                    f"<p><b>Webhook URL:</b> {webhook_url}</p>"
                    f"<p><b>Telegram результат:</b> {res_data.get('description', 'OK')}</p>"
                    f"<p>Бот уже готовий миттєво приймати повідомлення в Telegram!</p>"
                    f"<br/><a href='/'>⬅️ Назад</a>"
                ), 200
    except Exception as err:
        logger_error = str(err)
    else:
        logger_error = "Помилка відповіді"

    return (
        f"<h2>⚙️ Активація Webhook</h2>"
        f"<p>Проксі сервера повернув затримку ({logger_error}).</p>"
        f"<p><b>Натисніть на посилання нижче для активації вебхука прямо з вашого браузера:</b></p>"
        f"<p><a href='{telegram_api_url}' target='_blank' style='background:#28a745;padding:12px 24px;font-size:16px;'>👉 Натисніть тут для активації Webhook</a></p>"
        f"<br/><a href='/'>⬅️ Назад</a>"
    ), 200


@app.route("/webhook_info", methods=["GET"])
def webhook_info_route():
    """Показує поточний статус вебхука в Telegram."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    telegram_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    try:
        req = urllib.request.Request(telegram_api_url)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            result = data.get("result", {})
            return (
                f"<h2>ℹ️ Інформація про Webhook</h2>"
                f"<p><b>Поточний URL:</b> {result.get('url') or 'Не встановлено'}</p>"
                f"<p><b>Очікує обробки оновлень:</b> {result.get('pending_update_count', 0)}</p>"
                f"<p><b>Остання помилка:</b> {result.get('last_error_message') or 'Немає'}</p>"
                f"<br/><a href='/'>⬅️ Назад</a>"
            ), 200
    except Exception as e:
        return f"<h2>❌ Помилка: {e}</h2><br/><a href='/'>⬅️ Назад</a>", 500


@app.route("/delete_webhook", methods=["GET"])
def delete_webhook_route():
    """Видаляє Webhook (якщо потрібно повернутися до polling)."""
    if not BOT_TOKEN:
        return jsonify({"status": "error", "message": "BOT_TOKEN не задано в .env"}), 500

    telegram_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    try:
        req = urllib.request.Request(telegram_api_url)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            return (
                f"<h2>🗑️ Webhook видалено!</h2>"
                f"<p>Результат: {data.get('description', 'OK')}</p>"
                f"<br/><a href='/'>⬅️ Назад</a>"
            ), 200
    except Exception as e:
        return f"<h2>❌ Помилка: {e}</h2><br/><a href='/'>⬅️ Назад</a>", 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)