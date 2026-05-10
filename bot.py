import ssl
import aiohttp
import json
import os
import asyncio

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================================================
# ENV
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()

ALERT_CHAT_ID = int(os.getenv("ALERT_CHAT_ID"))

HEDEF_GRUPLAR = [
    int(x)
    for x in os.getenv("TARGET_GROUPS", "").split(",")
    if x.strip()
]

ADMIN_IDS = [
    int(x)
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
]

# =========================================================
# PANEL CONFIG
# =========================================================

PANELS = {
    "panel1": {
        "url": os.getenv("PANEL1_URL"),
        "username": os.getenv("PANEL1_USER"),
        "password": os.getenv("PANEL1_PASS")
    },
    "panel2": {
        "url": os.getenv("PANEL2_URL"),
        "username": os.getenv("PANEL2_USER"),
        "password": os.getenv("PANEL2_PASS")
    }
}

# =========================================================
# DOSYALAR
# =========================================================

USERS_FILE = "users.json"
LIMITS_FILE = "limits.json"
DEVIR_FILE = "devir.json"
ALERTS_FILE = "alerts.json"

# =========================================================
# JSON
# =========================================================

def load_json(file_name, default=None):
    if default is None:
        default = {}

    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


USERS = load_json(USERS_FILE)
LIMITS = load_json(LIMITS_FILE)

# =========================================================
# FORMAT
# =========================================================

def tr(x):
    try:
        return f"{int(float(x)):,}".replace(",", ".")
    except:
        return "0"

# =========================================================
# PANEL FETCH
# =========================================================

async def fetch_user_amount(panel_config, user_uuid):

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    login_url = f"{panel_config['url']}/login"
    reports_url = f"{panel_config['url']}/reports/quickly"

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx)
    ) as session:

        async with session.get(login_url) as r:
            text = await r.text()

        token = ""
        for line in text.splitlines():
            if 'name="_token"' in line:
                token = line.split('value="')[1].split('"')[0]
                break

        await session.post(
            login_url,
            data={
                "_token": token,
                "email": panel_config["username"],
                "password": panel_config["password"]
            }
        )

        async with session.get(reports_url) as r:
            text = await r.text()

        csrf = ""
        for line in text.splitlines():
            if 'csrf-token' in line:
                csrf = line.split('content="')[1].split('"')[0]
                break

        today = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")

        async with session.post(
            reports_url,
            headers={
                "X-CSRF-TOKEN": csrf,
                "Content-Type": "application/json"
            },
            json={
                "site": "",
                "dateone": today,
                "datetwo": today,
                "bank": "",
                "user": user_uuid
            }
        ) as r:
            data = await r.json()

        deposit_total = float(data.get("deposit", [0])[0] or 0)
        withdraw_total = float(data.get("withdraw", [0])[0] or 0)
        delivery_total = float(data.get("delivery", [0, 0])[1] or 0)

        return deposit_total, withdraw_total, delivery_total

# =========================================================
# KASA HESAP
# =========================================================

async def calculate_kasa(username):

    info = USERS[username]

    panel = info["panel"]
    uuid = info["uuid"]

    deposit, withdraw, delivery = await fetch_user_amount(
        PANELS[panel],
        uuid
    )

    commission = deposit * 0.025

    net = deposit - withdraw - delivery - commission

    devirs = load_json(DEVIR_FILE)
    devir = float(devirs.get(username, 0))

    total = net + devir

    return total

# =========================================================
# AUTO LIMIT CHECK (3 DAKİKA)
# =========================================================

async def auto_kasa_check(app):

    try:

        alerts = load_json(ALERTS_FILE)

        for username in USERS.keys():

            if username not in LIMITS:
                continue

            limit = float(LIMITS[username])

            total = await calculate_kasa(username)

            already = alerts.get(username, False)

            if total >= limit and not already:

                await app.bot.send_message(
                    chat_id=ALERT_CHAT_ID,
                    text=(
                        f"🚨 KASA LİMİT UYARISI 🚨\n\n"
                        f"Hesap: {username}\n"
                        f"Limit: {tr(limit)} TL\n"
                        f"Güncel Kasa: {tr(total)} TL\n"
                        f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )
                )

                alerts[username] = True
                save_json(ALERTS_FILE, alerts)

            elif total < limit:
                alerts[username] = False
                save_json(ALERTS_FILE, alerts)

    except Exception as e:
        print("AUTO KASA HATA:", e)

# =========================================================
# BACKGROUND LOOP (3 DK)
# =========================================================

async def kasa_loop(app):

    while True:

        await auto_kasa_check(app)

        await asyncio.sleep(180)  # 3 dakika

async def post_init(app):
    asyncio.create_task(kasa_loop(app))

# =========================================================
# BOT START
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yok")

app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

print("BOT AKTİF")

app.run_polling()
