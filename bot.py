import os
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from flask import Flask, render_template_string
import threading
import logging

TOKEN = os.getenv("TOKEN")
WATERMARK_PATH = "watermark.png"

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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"Received photo from user_id={update.message.from_user.id}")

        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        user_image = Image.open(BytesIO(photo_bytes)).convert("RGBA")
        watermark = Image.open(WATERMARK_PATH).convert("RGBA")

        watermark_resized = watermark.resize(user_image.size, Image.ANTIALIAS)
        combined = Image.alpha_composite(user_image, watermark_resized)

        output = BytesIO()
        output.name = "image.png"
        combined.save(output, format="PNG")
        output.seek(0)

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
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # تشغيل Flask في Thread منفصل
    threading.Thread(target=run_flask, daemon=True).start()

    # تشغيل البوت (Polling)
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
