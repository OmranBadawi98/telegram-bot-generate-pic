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
    logger.info(f"بدء إضافة النص: {text}")
    img = Image.open(BASE_IMAGE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    width_margin = int(img.width * 0.08)
    left_x = width_margin
    right_x = img.width - width_margin
    max_width = right_x - left_x

    top_margin = int(img.height * 0.35)
    bottom_margin = int(img.height * 0.08)
    max_height = img.height - top_margin - bottom_margin

    logger.info(f"المساحة الأفقية للنص: {max_width}px")
    logger.info(f"المساحة الرأسية للنص: {max_height}px (من {top_margin}px إلى {img.height - bottom_margin}px)")

    font_size = int(img.height * 0.08)
    logger.info(f"حجم الخط الابتدائي: {font_size}")

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

    def justify_line(line, draw, font, max_width):
        words = line.split()
        if len(words) == 1:
            return line  # لا تمديد في كلمة واحدة

        # حساب العرض الكلي للكلمات بدون مسافات
        total_words_width = sum(draw.textbbox((0,0), w, font=font)[2] - draw.textbbox((0,0), w, font=font)[0] for w in words)

        # حساب المساحة الفارغة التي نحتاج نملأها بالتمديد
        space_to_fill = max_width - total_words_width
        if space_to_fill <= 0:
            return line  # لا تمديد لو النص أطول من المساحة

        # عدد الحروف التي يمكننا وضع التمديد بينها (بين الحروف وليس بين الكلمات)
        extend_positions = sum(len(w) - 1 for w in words if len(w) > 1)
        if extend_positions == 0:
            return line  # لا تمديد لو ما في حروف كافية

        # كم عدد حروف التمديد لكل موقع تقريباً
        extend_per_pos = space_to_fill / extend_positions

        # نحدد عدد حروف التمديد لكل موقع (على شكل عدد صحيح)
        extend_chars_per_pos = max(1, int(extend_per_pos / (draw.textbbox((0,0), "ـ", font=font)[2] - draw.textbbox((0,0), "ـ", font=font)[0])))

        # نبدأ نبني السطر مع التمديد
        justified_line = ""
        for w in words:
            if len(w) == 1:
                justified_line += w
            else:
                for i, ch in enumerate(w):
                    justified_line += ch
                    if i < len(w) - 1:
                        justified_line += "ـ" * extend_chars_per_pos
            justified_line += " "  # مسافة بين الكلمات

        return justified_line.strip()

    while font_size > 10:
        font = ImageFont.truetype(FONT_PATH, font_size)
        lines = wrap_text(text, font, max_width)
        total_height = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            total_height += line_height + 5
        total_height -= 5

        logger.info(f"حجم الخط الحالي: {font_size}، عدد الأسطر: {len(lines)}، ارتفاع النص الكلي: {total_height}، المساحة المتاحة: {max_height}")

        if total_height <= max_height:
            break
        font_size -= 1

    y_start = top_margin + (max_height - total_height) // 2

    logger.info(f"بدء رسم النص عند النقطة y={y_start}")

    for line in lines:
        justified_line = justify_line(line, draw, font, max_width)
        bbox = draw.textbbox((0, 0), justified_line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x_start = left_x + (max_width - line_width) / 2
        draw.text((x_start, y_start), justified_line, font=font, fill="white")
        y_start += line_height + 5

    out = BytesIO()
    out.name = "text.png"
    img.save(out, format="PNG")
    out.seek(0)
    logger.info("تم حفظ الصورة النهائية مع النص")
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
