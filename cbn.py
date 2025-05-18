import os
import sqlite3
import logging
from datetime import datetime
import requests
import shutil
from twilio.rest import Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import subprocess
import asyncio
import nest_asyncio
from logging.handlers import RotatingFileHandler
import platform

# ================= CONFIG ================= #
TELEGRAM_BOT_TOKEN = "7040937454:AAGqcr1aF8HB6DaDIgUSURMgKKjG6rAF95U"
TWILIO_SID = "ACe0a87e110a84b18cd0cb6dd8f7137fbc"
TWILIO_AUTH_TOKEN = "5270cbe9f7d290070967881ecb1e1921"
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"  # Twilio sandbox number
YOUR_WHATSAPP_TO = "whatsapp:+254112969052"

DB_FILE = "chat_logs.db"
MEDIA_DIR = "media"
LOG_DIR = "logs"
# ========================================== #

# Initialize folders
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ================= LOGGER ================= #
log_file = os.path.join(LOG_DIR, "bot.log")
handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[handler, logging.StreamHandler()]
)
logger = logging.getLogger("LoggerBot")
# ========================================== #

# =============== DATABASE ================= #
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, username TEXT,
            first_name TEXT, last_name TEXT,
            message TEXT, latitude REAL,
            longitude REAL, datetime TEXT,
            media_type TEXT, media_file TEXT
        )""")
        conn.commit()
# ========================================== #

# ============ IP LOCATION FALLBACK ========= #
def get_ip_location():
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5).json()
        return r.get("lat"), r.get("lon")
    except Exception as e:
        logger.warning(f"IP lookup failed: {e}")
        return None, None
# =========================================== #

# ============== ONIONSHARE ================= #
def share_with_onionshare(filepath):
    if not filepath or not os.path.isfile(filepath):
        return None

    onionshare_cmd = "onionshare"
    shell_flag = False

    if platform.system() == "Windows":
        onionshare_cmd = "onionshare.exe"
        shell_flag = True

    if not shutil.which(onionshare_cmd):
        return "OnionShare not installed or not in PATH"

    try:
        result = subprocess.run(
            [onionshare_cmd, "--no-autostart", "--text", filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=shell_flag
        )
        for line in result.stdout.splitlines():
            if "onion address is:" in line.lower():
                return line.split("onion address is:")[-1].strip()
        return "No onion URL found"
    except Exception as e:
        logger.error(f"OnionShare error: {e}")
        return "OnionShare failed"
# =========================================== #

# ============= WHATSAPP SENDER ============= #
def send_to_whatsapp(message):
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_FROM,
            to=YOUR_WHATSAPP_TO
        )
    except Exception as e:
        logger.error(f"Twilio WhatsApp error: {e}")
# =========================================== #

# ============== MEDIA HANDLER ============== #
async def save_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file, media_type, ext = None, None, ""

    if msg.photo:
        file = await context.bot.get_file(msg.photo[-1].file_id)
        media_type, ext = "photo", ".jpg"
    elif msg.video:
        file = await context.bot.get_file(msg.video.file_id)
        media_type, ext = "video", ".mp4"
    elif msg.document:
        file = await context.bot.get_file(msg.document.file_id)
        media_type = "document"
        ext = os.path.splitext(msg.document.file_name or "")[1]
    elif msg.voice:
        file = await context.bot.get_file(msg.voice.file_id)
        media_type, ext = "voice", ".ogg"
    elif msg.audio:
        file = await context.bot.get_file(msg.audio.file_id)
        media_type, ext = "audio", ".mp3"
    elif msg.video_note:
        file = await context.bot.get_file(msg.video_note.file_id)
        media_type, ext = "video_note", ".mp4"

    if not file:
        return None, None

    folder = os.path.join(MEDIA_DIR, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(folder, exist_ok=True)
    filename = f"{update.effective_user.id}_{datetime.now().strftime('%H%M%S')}{ext}"
    filepath = os.path.join(folder, filename)

    try:
        await file.download_to_drive(filepath)
        return media_type, filepath
    except Exception as e:
        logger.error(f"Media download failed: {e}")
        return None, None
# =========================================== #

# ================ HANDLERS ================= #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Logger Bot is active. Send any message, media or location.")

async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    text = msg.text or ""
    location = msg.location
    lat, lon = (location.latitude, location.longitude) if location else get_ip_location()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    media_type, media_file = await save_media(update, context)
    onion_url = share_with_onionshare(media_file) if media_file else None

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
        INSERT INTO logs (chat_id, username, first_name, last_name, message, latitude, longitude, datetime, media_type, media_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            user.id, user.username, user.first_name, user.last_name,
            text, lat, lon, timestamp, media_type, media_file
        ))
        conn.commit()

    summary = f"""
👤 @{user.username or user.id}
📛 Name: {user.first_name or ''} {user.last_name or ''}
💬 Msg: {text or 'None'}
📍 Loc: {lat}, {lon}
📂 Media: {media_type or 'None'}
📅 Time: {timestamp}
🌐 Onion URL: {onion_url or 'N/A'}
""".strip()

    logger.info(summary)
    send_to_whatsapp(summary)
# =========================================== #

# ================ MAIN ===================== #
async def main():
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.LOCATION | filters.PHOTO |
        filters.VIDEO | filters.Document.ALL |
        filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE,
        log_message
    ))

    logger.info("✅ Telegram Logger Bot started.")
    await app.run_polling()
# =========================================== #

# ============= ENTRYPOINT ================== #
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
