import ssl
import aiohttp
import json
import os

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
# JSON LOAD
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

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

# =========================================================
# LOAD DATA
# =========================================================

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
# PANELDEN KASA ÇEK
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

        # LOGIN SAYFASI
        async with session.get(login_url) as r:
            text = await r.text()

        token = ""

        for line in text.splitlines():

            if 'name="_token"' in line:

                token = (
                    line.split('value="')[1]
                    .split('"')[0]
                )

                break

        # LOGIN
        await session.post(
            login_url,
            data={
                "_token": token,
                "email": panel_config["username"],
                "password": panel_config["password"]
            }
        )

        # REPORT SAYFASI
        async with session.get(reports_url) as r:
            text = await r.text()

        csrf = ""

        for line in text.splitlines():

            if 'csrf-token' in line:

                csrf = (
                    line.split('content="')[1]
                    .split('"')[0]
                )

                break

        today = (
            datetime.utcnow() + timedelta(hours=3)
        ).strftime("%Y-%m-%d")

        # RAPOR İSTEĞİ
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

        deposit_total = float(
            data.get("deposit", [0])[0] or 0
        )

        withdraw_total = float(
            data.get("withdraw", [0])[0] or 0
        )

        delivery_total = float(
            data.get("delivery", [0, 0])[1] or 0
        )

        return (
            deposit_total,
            withdraw_total,
            delivery_total
        )

# =========================================================
# KASA HESAPLA
# =========================================================

async def calculate_kasa(username):

    info = USERS[username]

    panel = info["panel"]
    uuid = info["uuid"]

    deposit_total, withdraw_total, delivery_total = await fetch_user_amount(
        PANELS[panel],
        uuid
    )

    commission = deposit_total * 0.025

    net = (
        deposit_total
        - withdraw_total
        - delivery_total
        - commission
    )

    devirs = load_json(DEVIR_FILE)

    devir = float(
        devirs.get(username, 0)
    )

    total = net + devir

    return {
        "deposit": deposit_total,
        "withdraw": withdraw_total,
        "delivery": delivery_total,
        "commission": commission,
        "net": net,
        "devir": devir,
        "total": total
    }

# =========================================================
# /KASA1
# /KASA2
# =========================================================

async def kasa(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = await update.message.reply_text(
        "Kasa verileri alınıyor..."
    )

    try:

        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:

            await msg.edit_text(
                "Bu komutu sadece adminler kullanabilir."
            )

            return

        command = (
            update.message.text
            .lstrip("/")
            .upper()
        )

        username = command.replace(
            "KASA",
            "SKY"
        )

        if username not in USERS:

            await msg.edit_text(
                "Kullanıcı bulunamadı."
            )

            return

        data = await calculate_kasa(username)

        await msg.edit_text(

            f"🏦 {username} KASA\n\n"

            f"💸 Yatırım: {tr(data['deposit'])} TL\n"
            f"💰 Çekim: {tr(data['withdraw'])} TL\n"
            f"🚚 Teslimat: {tr(data['delivery'])} TL\n"
            f"📉 Komisyon: {tr(data['commission'])} TL\n"
            f"📊 Net: {tr(data['net'])} TL\n"
            f"🔁 Devir: {tr(data['devir'])} TL\n\n"

            f"🏦 TOPLAM: {tr(data['total'])} TL"
        )

    except Exception as e:

        await msg.edit_text(
            f"Hata oluştu:\n{e}"
        )

# =========================================================
# OTOMATİK LIMIT KONTROL
# =========================================================

async def auto_kasa_check(context: ContextTypes.DEFAULT_TYPE):

    try:

        alerts = load_json(ALERTS_FILE)

        for username in USERS.keys():

            if username not in LIMITS:
                continue

            limit = float(LIMITS[username])

            data = await calculate_kasa(username)

            total = data["total"]

            already_alerted = alerts.get(
                username,
                False
            )

            # LIMIT GEÇİLDİ
            if total >= limit and not already_alerted:

                await context.bot.send_message(
                    chat_id=ALERT_CHAT_ID,
                    text=(

                        f"🚨 KASA LİMİT UYARISI 🚨\n\n"

                        f"Hesap: {username}\n"
                        f"Limit: {tr(limit)} TL\n"
                        f"Güncel Kasa: {tr(total)} TL\n\n"

                        f"Tarih: "
                        f"{datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )
                )

                alerts[username] = True

                save_json(ALERTS_FILE, alerts)

            # LIMIT ALTINA DÜŞERSE RESET
            elif total < limit:

                alerts[username] = False

                save_json(ALERTS_FILE, alerts)

    except Exception as e:

        print(f"OTO KASA HATA: {e}")

# =========================================================
# FORWARD SİSTEMİ
# =========================================================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    if not message:
        return

    text = message.text or message.caption or ""

    # ETİKET YOKSA ÇALIŞMA
    if BOT_USERNAME not in text.lower():
        return

    grup_adi = (
        message.chat.title
        or "Bilinmeyen Grup"
    )

    gonderen = (
        message.from_user.first_name
        or "Anonim"
    )

    ust_bilgi = (

        f"📢 Kaynak Grup: {grup_adi}\n"
        f"👤 Gönderen: {gonderen}\n\n"
    )

    for hedef in HEDEF_GRUPLAR:

        try:

            # TEXT
            if message.text:

                await context.bot.send_message(
                    chat_id=hedef,
                    text=ust_bilgi + message.text
                )

            # FOTO / VIDEO / DOSYA
            else:

                await context.bot.copy_message(
                    chat_id=hedef,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                    caption=ust_bilgi + (
                        message.caption or ""
                    )
                )

        except Exception as e:

            print(f"FORWARD HATA: {e}")

# =========================================================
# APP
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN bulunamadı")

app = ApplicationBuilder().token(BOT_TOKEN).build()

# /kasa1 /kasa2
app.add_handler(
    MessageHandler(
        filters.Regex(r"^/kasa\d+$"),
        kasa
    )
)

# forward sistemi
app.add_handler(
    MessageHandler(
        filters.ALL,
        handle
    )
)

# HER 5 DAKİKADA KONTROL
app.job_queue.run_repeating(
    auto_kasa_check,
    interval=300,
    first=10
)

print("BOT AKTİF")

app.run_polling()
