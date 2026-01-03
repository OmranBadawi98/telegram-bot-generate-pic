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
    ConversationHandler,
)
from flask import Flask, render_template_string
import threading
import logging

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")

LOGO_PATH = "logo.png"
BASE_IMAGE_PATH = "base.png"
FONT_PATH = "font.ttf"

# Conversation states
MODE_SELECTION, MODE_LOGO, MODE_TEXT = range(3)

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

# ================== KEYBOARD ==================
def get_main_keyboard():
    keyboard = [
        ["➕ إضافة شعار إلى صورة"],
        ["📝 إضافة نص إلى صورة"],
        ["القائمة الرئيسية 🔄"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

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
    logger.info(f"بدء إضافة نص: {text}")
    
    img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    max_width = img.width * 0.9
    max_height = img.height * 0.9

    font_size = int(img.height * 0.08)


    def wrap_text(text, font, max_width):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    while font_size > 10:
        font = ImageFont.truetype(FONT_PATH, font_size)
        lines = wrap_text(text, font, max_width)

        # حساب ارتفاع النص الكلي مع المسافات بين الأسطر
        total_height = 0
        line_heights = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            h = bbox[3] - bbox[1]
            line_heights.append(h)
            total_height += h
        line_spacing = int(font_size * 0.1)
        total_height += line_spacing * (len(lines) - 1)

        if total_height <= max_height:
            break
        font_size -= 1

    logger.info(f"حجم الخط النهائي: {font_size}, عدد الأسطر: {len(lines)}")

    y_start = (img.height - total_height) / 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = line_heights[i]
        x = (img.width - w) / 2
        draw.text((x, y_start), line, font=font, fill="white")
        y_start += h + line_spacing

    out = BytesIO()
    out.name = "text.png"
    img.save(out, format="PNG")
    out.seek(0)

    logger.info("تمت إضافة النص إلى الصورة بنجاح.")
    return out

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("User started the bot")
    await update.message.reply_text(
        "اختر العملية:",
        reply_markup=get_main_keyboard(),
    )
    return MODE_SELECTION

async def mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"Mode selection received: {text}")

    if text == "القائمة الرئيسية 🔄":
        await update.message.reply_text(
            "اختر العملية:",
            reply_markup=get_main_keyboard(),
        )
        return MODE_SELECTION

    if "شعار" in text:
        await update.message.reply_text(
            "📸 أرسل الصورة الآن",
            reply_markup=ReplyKeyboardRemove(),
        )
        return MODE_LOGO

    elif "نص" in text:
        await update.message.reply_text(
            "✏️ أرسل النص الذي تريد طباعته",
            reply_markup=ReplyKeyboardRemove(),
        )
        return MODE_TEXT

    else:
        await update.message.reply_text(
            "الرجاء اختيار أحد الخيارات من لوحة المفاتيح.",
            reply_markup=get_main_keyboard(),
        )
        return MODE_SELECTION

async def handle_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("الرجاء إرسال صورة صالحة.")
        return MODE_LOGO

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()

    logger.info("Processing logo addition")

    try:
        result = add_logo(image_bytes)
        await update.message.reply_photo(photo=result)
        await update.message.reply_text(
            "تمت إضافة الشعار بنجاح.\nاختر العملية التالية:",
            reply_markup=get_main_keyboard(),
        )
        return MODE_SELECTION
    except Exception as e:
        logger.error(f"Error adding logo: {e}")
        await update.message.reply_text("حدث خطأ أثناء إضافة الشعار. حاول مرة أخرى.")
        return MODE_LOGO

async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"Received text to add: {text}")

    try:
        result = add_text(text)
        await update.message.reply_photo(photo=result)
        await update.message.reply_text(
            "تمت إضافة النص بنجاح.\nاختر العملية التالية:",
            reply_markup=get_main_keyboard(),
        )
        return MODE_SELECTION
    except Exception as e:
        logger.error(f"Error adding text: {e}")
        await update.message.reply_text("حدث خطأ أثناء إضافة النص. حاول مرة أخرى.")
        return MODE_TEXT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "تم إلغاء العملية. لاختيار عملية جديدة اكتب /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

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

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MODE_SELECTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_selection),
            ],
            MODE_LOGO: [
                MessageHandler(filters.PHOTO, handle_logo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, mode_selection),  # نص بدل صورة؟
            ],
            MODE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_mode),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        conversation_timeout=180,
        allow_reentry=True,
    )

    app_bot.add_handler(conv_handler)

    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Bot started")
    app_bot.run_polling()

if __name__ == "__main__":
    main()
