import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

HEDEF_GRUPLAR = [
    int(x) for x in os.getenv("TARGET_GROUPS").split(",")
]

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Railway verdiğin domain

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message:
        return

    text_control = message.text or message.caption or ""

    if BOT_USERNAME.lower() in text_control.lower():

        grup_adi = message.chat.title or "Bilinmeyen Grup"
        gonderen = message.from_user.first_name or "Anonim"

        ust_metin = f"📢 {grup_adi}\n👤 {gonderen}\n\n"

        for grup in HEDEF_GRUPLAR:
            try:
                if message.text:
                    await context.bot.send_message(
                        chat_id=grup,
                        text=ust_metin + message.text
                    )
                else:
                    await context.bot.copy_message(
                        chat_id=grup,
                        from_chat_id=message.chat_id,
                        message_id=message.message_id,
                        caption=ust_metin + (message.caption or "")
                    )
            except Exception as e:
                print(f"Hata: {e}")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle))

    await app.bot.set_webhook(url=WEBHOOK_URL)
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
