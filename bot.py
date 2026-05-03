from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = "BOT_TOKEN"

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    print("GRUP ID:", chat.id)
    print("GRUP ADI:", chat.title)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, get_id))

app.run_polling()
