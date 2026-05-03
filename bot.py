from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import os

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

HEDEF_GRUPLAR = [
    int(x) for x in os.getenv("TARGET_GROUPS").split(",")
]

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message:
        return

    text = message.text or message.caption or ""

    # SADECE etiket varsa çalış
    if BOT_USERNAME.lower() not in text.lower():
        return

    grup_adi = message.chat.title or "Bilinmeyen Grup"
    gonderen = message.from_user.first_name or "Anonim"

    ust_bilgi = f"📢 Kaynak Grup: {grup_adi}\n👤 Gönderen: {gonderen}\n\n"

    for hedef in HEDEF_GRUPLAR:
        try:
            if message.text:
                await context.bot.send_message(
                    chat_id=hedef,
                    text=ust_bilgi + message.text
                )
            else:
                await context.bot.copy_message(
                    chat_id=hedef,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                    caption=ust_bilgi + (message.caption or "")
                )
        except Exception as e:
            print(f"Hata: {e}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, handle))

app.run_polling()
