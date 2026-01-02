import os
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from flask import Flask, render_template_string
import threading
import logging

TOKEN = os.getenv("TOKEN")
WATERMARK_PATH = "logo.png"

app = Flask(__name__)

# إعداد اللوجر
logger = logging.getLogger("bot_logger")
logger.setLevel(logging.INFO)

# قائمة لحفظ آخر 100 سجل (لتعرضها في الويب)
log_records = []

class ListHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_records.append(log_entry)
        if len(log_records) > 100:
            log_records.pop(0)

list_handler = ListHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
list_handler.setFormatter(formatter)
logger.addHandler(list_handler)

async def process_image(image_bytes: bytes) -> BytesIO:
    user_image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    watermark = Image.open(WATERMARK_PATH).convert("RGBA")
    
    # Resize watermark to match user image size
    watermark_resized = watermark.resize(user_image.size, Image.Resampling.LANCZOS)
    
    combined = Image.alpha_composite(user_image, watermark_resized)

    output = BytesIO()
    output.name = "image.png"
    combined.save(output, format="PNG")
    output.seek(0)
    return output

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id if update.message.from_user else "unknown"
        logger.info(f"Received message from user_id={user_id}")

        photo_bytes = None

        # حالة الصورة العادية (photo)
        if update.message.photo:
            photo = update.message.photo[-1]
            photo_file = await photo.get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            logger.info("Photo received as Telegram photo.")

        # حالة الصورة كملف document (تحقق من نوع الملف)
        elif update.message.document:
            doc = update.message.document
            if doc.mime_type.startswith("image/"):
                doc_file = await doc.get_file()
                photo_bytes = await doc_file.download_as_bytearray()
                logger.info("Photo received as Telegram document.")
            else:
                logger.info(f"Received document but not an image (mime_type={doc.mime_type}). Ignored.")
                return

        else:
            logger.info("Message does not contain photo or image document. Ignored.")
            return

        # معالجة الصورة وإضافة العلامة المائية
        output = await process_image(photo_bytes)
        await update.message.reply_photo(photo=output)
        logger.info("Replied with watermarked photo successfully.")

    except Exception as e:
        logger.error(f"Error processing photo: {e}")

# صفحة الويب لعرض السجلات
@app.route("/")
def home():
    html = """
    <html lang="ar">
    <head>
        <meta charset="UTF-8" />
        <title>سجلات البوت</title>
        <style>
            body {font-family: Arial, sans-serif; direction: rtl; background: #f9f9f9; padding: 20px;}
            h1 {color: #333;}
            pre {
                background: #222;
                color: #eee;
                padding: 15px;
                border-radius: 8px;
                height: 500px;
                overflow-y: scroll;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
        </style>
    </head>
    <body>
        <h1>سجلات البوت</h1>
        <pre>{{ logs }}</pre>
    </body>
    </html>
    """
    return render_template_string(html, logs="\n".join(log_records))

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    # دعم الصور كـ photo أو كملف document (صور فقط)
    application.add_handler(MessageHandler(filters.PHOTO | (filters.Document.IMAGE), handle_photo))

    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
