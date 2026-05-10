import ssl
import aiohttp
import json
import os

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================================================
# ENV
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()

_raw_alert = os.getenv("ALERT_CHAT_ID", "").strip()
ALERT_CHAT_ID = int(_raw_alert) if _raw_alert else None

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

def _parse_int(env_name: str):

    raw = os.getenv(env_name, "").strip()

    if not raw:
        return None

    return int(raw)


LIMIT_CHECK_INTERVAL_SEC = _parse_int("LIMIT_CHECK_INTERVAL_SEC") or 300
LIMIT_CHECK_FIRST_SEC = _parse_int("LIMIT_CHECK_FIRST_SEC") or 10

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

# NOT: USERS / LIMITS her işlemde disktan okunur; limits.json
# güncellendiğinde botu yeniden başlatmaya gerek kalmaz.

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

    users_data = load_json(USERS_FILE)

    info = users_data[username]

    panel = info["panel"]
    uuid = info["uuid"]

    panel_conf = PANELS.get(panel) or {}

    if not panel_conf.get("url"):
        raise RuntimeError(
            f"Panel '{panel}' için PANEL*_URL eksik "
            f"veya .env yanlış (hesap {username})."
        )

    deposit_total, withdraw_total, delivery_total = await fetch_user_amount(
        panel_conf,
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

        users_data = load_json(USERS_FILE)

        if username not in users_data:

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


        users_data = load_json(USERS_FILE)
        limits_data = load_json(LIMITS_FILE)

        for username in limits_data.keys():

            if username not in users_data:
                print(
                    f"OTO KASA: {username} limits.json içinde ama "
                    f"users.json'da yok, atlanıyor."
                )
                continue

            limit = float(limits_data[username])

            try:
                data = await calculate_kasa(username)
            except Exception as e:
                print(f"OTO KASA {username}: kasa hesap hatası: {e}")
                continue

            total = data["total"]

            already_alerted = bool(
                alerts.get(username, False)
            )

            # LIMIT GEÇİLDİ
            if total >= limit and not already_alerted:

                try:
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
                except Exception as e:
                    print(
                        f"OTO KASA {username}: Telegram mesaj gönderilemedi "
                        f"(chat_id doğru mu, bot yazabiliyor mu?): {e}"
                    )
                    continue

                alerts[username] = True

                save_json(ALERTS_FILE, alerts)

            # LIMIT ALTINA DÜŞERSE RESET (sadece state değişince kaydet)
            elif total < limit and already_alerted:

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

if ALERT_CHAT_ID is None:
    raise RuntimeError(
        "ALERT_CHAT_ID bulunamadı veya boş — limit uyarılarının "
        "gideceği sohbet/kanal ID\'sini .env içinde tam sayı olarak ver."
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()

if app.job_queue is None:
    raise RuntimeError(
        "JobQueue yok. Kurulum: pip install 'python-telegram-bot[job-queue]'"
    )

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

# Varsayılan 5 dk; LIMIT_CHECK_INTERVAL_SEC ile değiştirilebilir
app.job_queue.run_repeating(
    auto_kasa_check,
    interval=LIMIT_CHECK_INTERVAL_SEC,
    first=LIMIT_CHECK_FIRST_SEC
)

print("BOT AKTİF")

app.run_polling()
