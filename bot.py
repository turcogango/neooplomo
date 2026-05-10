import ssl
import aiohttp
import json
import os
import asyncio
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# =========================================================
# ENV SAFE
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()

ALERT_CHAT_ID = int(os.getenv("ALERT_CHAT_ID", "0"))

HEDEF_GRUPLAR = [
    int(x) for x in os.getenv("TARGET_GROUPS", "").split(",") if x.strip()
]

# =========================================================
# FILES
# =========================================================

USERS = json.load(open("users.json", "r", encoding="utf-8"))
LIMITS = json.load(open("limits.json", "r", encoding="utf-8"))
DEVIR = json.load(open("devir.json", "r", encoding="utf-8"))
ALERTS_FILE = "alerts.json"

def load_alerts():
    try:
        return json.load(open(ALERTS_FILE, "r", encoding="utf-8"))
    except:
        return {}

def save_alerts(data):
    json.dump(data, open(ALERTS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# =========================================================
# FORMAT
# =========================================================

def tr(x):
    try:
        return f"{int(float(x)):,}".replace(",", ".")
    except:
        return "0"

# =========================================================
# PANEL FETCH (FIXED + SAFE)
# =========================================================

async def fetch_user_amount(panel_config, user_uuid):

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    login_url = f"{panel_config['url']}/login"
    reports_url = f"{panel_config['url']}/reports/quickly"

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        timeout=timeout
    ) as session:

        # ---------------- LOGIN ----------------
        async with session.get(login_url) as r:
            html = await r.text()

        token = None
        for line in html.splitlines():
            if 'name="_token"' in line:
                try:
                    token = line.split('value="')[1].split('"')[0]
                except:
                    pass
                break

        if not token:
            print("❌ TOKEN YOK")
            return 0, 0, 0

        async with session.post(
            login_url,
            data={
                "_token": token,
                "email": panel_config["username"],
                "password": panel_config["password"]
            }
        ) as r:

            login_text = await r.text()

            print("LOGIN STATUS:", r.status)

            if r.status != 200:
                print("❌ LOGIN FAIL")
                return 0, 0, 0

        # ---------------- REPORT PAGE ----------------
        async with session.get(reports_url) as r:
            html = await r.text()

        csrf = None
        for line in html.splitlines():
            if 'csrf-token' in line:
                try:
                    csrf = line.split('content="')[1].split('"')[0]
                except:
                    pass
                break

        if not csrf:
            print("❌ CSRF YOK")
            return 0, 0, 0

        today = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")

        # ---------------- REPORT ----------------
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

            try:
                data = await r.json()
            except:
                print("❌ JSON PARSE ERROR")
                return 0, 0, 0

        print("REPORT RAW:", data)

        deposit = float(data.get("deposit", [0])[0] or 0)
        withdraw = float(data.get("withdraw", [0])[0] or 0)
        delivery = float(data.get("delivery", [0, 0])[1] or 0)

        return deposit, withdraw, delivery

# =========================================================
# KASA CALC
# =========================================================

async def calculate_kasa(username):

    info = USERS.get(username)
    if not info:
        return 0

    deposit, withdraw, delivery = await fetch_user_amount(
        {
            "url": info["panel"],
            "username": "",
            "password": ""
        },
        info["uuid"]
    )

    commission = deposit * 0.025
    net = deposit - withdraw - delivery - commission

    devir = float(DEVIR.get(username, 0))

    return net + devir

# =========================================================
# AUTO CHECK (3 MIN)
# =========================================================

async def auto_kasa_check(app):

    alerts = load_alerts()

    for username in USERS.keys():

        if username not in LIMITS:
            continue

        limit = float(LIMITS[username])

        total = await calculate_kasa(username)

        if total >= limit and not alerts.get(username):

            await app.bot.send_message(
                chat_id=ALERT_CHAT_ID,
                text=(
                    f"🚨 KASA LİMİT UYARISI 🚨\n\n"
                    f"Hesap: {username}\n"
                    f"Limit: {tr(limit)} TL\n"
                    f"Güncel: {tr(total)} TL\n"
                    f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
            )

            alerts[username] = True
            save_alerts(alerts)

        elif total < limit:
            alerts[username] = False
            save_alerts(alerts)

# =========================================================
# LOOP
# =========================================================

async def kasa_loop(app):
    while True:
        try:
            await auto_kasa_check(app)
        except Exception as e:
            print("LOOP ERROR:", e)

        await asyncio.sleep(180)

async def post_init(app):
    asyncio.create_task(kasa_loop(app))

# =========================================================
# BOT
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yok")

app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

print("BOT AKTİF")

app.run_polling()
