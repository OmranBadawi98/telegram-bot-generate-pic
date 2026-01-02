import os
from io import BytesIO
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters


TOKEN = os.getenv("TOKEN")
WATERMARK_PATH = "watermark.png"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()

if __name__ == "__main__":
    main()
