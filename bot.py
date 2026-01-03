import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from flask import Flask, render_template_string
import threading
import logging

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")

LOGO_PATH = "logo.png"
BASE_IMAGE_PATH = "base.png"
FONT_PATH = "font.ttf"

MODE_NONE = None
MODE_LOGO = "logo"
MODE_TEXT = "text"

# ================== FLASK ==================
app = Flask(__name__)

# ================== LOGGING ==================
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

log_records = []

class ListHandler(logging.Handler):
    def emit(self, record):
        log_records.append(self.format(record))
        if len(log_records) > 100:
            log_records.pop(0)

handler = ListHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

# ================== IMAGE FUNCTIONS ==================
def add_logo(image_bytes: bytes) -> BytesIO:
    base = Image.open(BytesIO(image_bytes)).convert("RGBA")
    logo = Image.open(LOGO_PATH).convert("RGBA")

    logo = logo.resize(base.size, Image.Resampling.LANCZOS)
    combined = Image.alpha_composite(base, logo)

    out = BytesIO()
    out.name = "result.png"
    combined.save(out, format="PNG")
    out.seek(0)
    return out

def add_text(text: str) -> BytesIO:
    img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_size = int(img.height * 0.08)
    font = ImageFont.truetype(FONT_PATH, font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (img.width - text_w) / 2
    y = (img.height - text_h) / 2

    draw.text((x, y), text, font=font, fill="white")

    out = BytesIO()
    out.name = "text.png"
    img.save(out, format="PNG")
    out.seek(0)
    return out

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ إضافة شعار إلى صورة"],
        ["📝 إضافة نص إلى صورة"],
    ]
    await update.message.reply_text(
        "اختر العملية:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )
    context.user_data["mode"] = MODE_NONE

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "شعار" in text:
        context.user_data["mode"] = MODE_LOGO
        await update.message.reply_text(
            "📸 أرسل الصورة الآن",
            reply_markup=ReplyKeyboardRemove(),
        )

    elif "نص" in text:
        context.user_data["mode"] = MODE_TEXT
        await update.message.reply_text(
            "✏️ أرسل النص الذي تريد طباعته",
            reply_markup=ReplyKeyboardRemove(),
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != MODE_LOGO:
        return

    logger.info("Received image for logo mode")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    result = add_logo(image_bytes)
    await update.message.reply_photo(photo=result)

    context.user_data["mode"] = MODE_NONE

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != MODE_TEXT:
        return

    text = update.message.text
    logger.info(f"Received text: {text}")

    result = add_text(text)
    await update.message.reply_photo(photo=result)

    context.user_data["mode"] = MODE_NONE

# ================== WEB UI ==================
@app.route("/")
def home():
    return render_template_string(
        """
        <html>
        <head><title>Bot Logs</title></head>
        <body style="background:#111;color:#eee;font-family:monospace">
        <h2>Logs</h2>
        <pre>{{ logs }}</pre>
        </body>
        </html>
        """,
        logs="\n".join(log_records),
    )

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run("0.0.0.0", port=port)

# ================== MAIN ==================
def main():
    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Bot started")
    app_bot.run_polling()


if __name__ == "__main__":
    main()