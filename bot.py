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
    ]
    # أزرار تظهر بشكل دائم
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
    logger.info("User started the bot")
    await update.message.reply_text(
        "اختر العملية:",
        reply_markup=get_main_keyboard(),
    )
    return MODE_SELECTION

async def mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"Mode selection received: {text}")

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
        await update.message.reply_text("الرجاء اختيار أحد الخيارات من لوحة المفاتيح.")
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

async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # قد لا يكون update موجود في بعض حالات timeout
    # فقط نرسل رسالة عامة
    if update and update.message:
        await update.message.reply_text(
            "انتهى وقت الانتظار. الرجاء اختيار العملية مجدداً:",
            reply_markup=get_main_keyboard(),
        )
    return MODE_SELECTION

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
        conversation_timeout=180,  # 3 دقائق مهلة
        allow_reentry=True,
        # إضافة استدعاء عند انتهاء المهلة (في مكتبات حديثة فقط)
        on_timeout=conversation_timeout,
    )

    app_bot.add_handler(conv_handler)

    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Bot started")
    app_bot.run_polling()

if __name__ == "__main__":
    main()
