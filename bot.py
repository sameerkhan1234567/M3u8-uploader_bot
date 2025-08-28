import os
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")  # koyeb me env variable set karna hoga

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me an m3u8 link with edge-cache-token, I’ll download & send video!")

async def handle_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.endswith(".m3u8") and "edge-cache-token" not in url:
        await update.message.reply_text("⚠️ Please send a valid m3u8 URL with edge-cache-token")
        return
    
    await update.message.reply_text("⏳ Downloading... Please wait!")

    # Output file
    output_file = "video.mp4"

    try:
        subprocess.run([
            "ffmpeg", "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", output_file, "-y"
        ], check=True)

        await update.message.reply_video(video=open(output_file, "rb"))
        os.remove(output_file)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_m3u8))
    app.run_polling()

if __name__ == "__main__":
    main()