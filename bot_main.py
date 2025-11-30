import os
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)

# --- БИБЛИОТЕКА GOOGLE GEMINI ---
try:
    import google.generativeai as genai
except ImportError:
    print("Ошибка: Библиотека 'google-generativeai' не установлена.")
    exit()

# --- НАСТРОЙКИ ---

# ТВОЙ ID (Доступ разрешен только этому числу)
ADMIN_ID = 1348287195

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') 
# Базовый ключ (можно задать в Render или через /setkey)
DEFAULT_GEMINI_KEY = os.environ.get('GEMINI_API_KEY')

if not TELEGRAM_TOKEN:
    logging.error("⛔ ОШИБКА: TELEGRAM_TOKEN не найден.")
    exit(1)

# --- ЗАГЛУШКА ДЛЯ RENDER (WEB SERVER) ---
# Это нужно, чтобы Render думал, что у нас веб-сайт, и не выключал бота
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def start_web_server():
    # Render передает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logging.info(f"🌍 Web server for Render started on port {port}")
    server.serve_forever()

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
user_models = {}      # {user_id: "model_name"}
user_api_keys = {}    # {user_id: "sk-..."}
chats = {}            # {user_id: chat_session_object}

AVAILABLE_MODELS = {
    "gemini-3-pro": "gemini-3-pro-preview",
    "nano-banana": "gemini-3-pro-image",
    "gemini-flash": "gemini-2.5-flash"
}

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ПРОВЕРКА ДОСТУПА ---
def is_admin(user_id):
    return user_id == ADMIN_ID

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_model_keyboard():
    keyboard = [
        [InlineKeyboardButton("🪐 Gemini 3 Pro (Smart)", callback_data='set_gemini-3-pro')],
        [InlineKeyboardButton("🍌 Nano Banana Pro (Vision)", callback_data='set_nano-banana')],
        [InlineKeyboardButton("⚡ Gemini 2.5 Flash (Fast)", callback_data='set_gemini-flash')],
    ]
    return InlineKeyboardMarkup(keyboard)

def configure_genai_for_user(user_id):
    api_key = user_api_keys.get(user_id, DEFAULT_GEMINI_KEY)
    if not api_key:
        raise ValueError("API Key не найден. Используйте /setkey.")
    genai.configure(api_key=api_key)
    return api_key

def get_chat_session(user_id, model_name):
    if user_id not in chats or chats[user_id].model != model_name:
        configure_genai_for_user(user_id)
        model = genai.GenerativeModel(model_name)
        chats[user_id] = model.start_chat(history=[])
    return chats[user_id]

# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # ПРОВЕРКА НА ЧУЖАКА
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещен. Бот приватный.")
        return

    if user_id not in user_models:
        user_models[user_id] = "gemini-2.5-flash"
    
    msg = (
        f"👋 **Привет, Хозяин! (ID: {user_id})**\n"
        f"Все системы в норме. Gemini 3 готов.\n\n"
        f"🤖 Модель: `{user_models.get(user_id)}`\n"
        f"🔑 Ключ: {'✅ Личный' if user_id in user_api_keys else 'ℹ️ Общий'}\n\n"
        "**Команды:**\n"
        "🧹 /clear — Новый диалог (забыть контекст)\n"
        "🧠 /model — Смена модели\n"
        "🔑 /setkey `ключ` — Свой API ключ\n"
        "🗑 /delkey — Удалить свой ключ\n"
        "ℹ️ /start — Меню"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id): return

    if user_id in chats:
        del chats[user_id]
        await update.message.reply_text("🧹 **Память очищена!**", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("🧹 Память и так пуста.")

async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id): return

    try:
        key = context.args[0] if context.args else None
        if not key:
            await update.message.reply_text("⚠️ Использование: `/setkey AIzaSy...`", parse_mode=ParseMode.MARKDOWN)
            return
        user_api_keys[user_id] = key
        if user_id in chats: del chats[user_id]
        await update.message.reply_text("✅ API ключ сохранен!", parse_mode=ParseMode.MARKDOWN)
        try: await update.message.delete()
        except: pass
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def del_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id): return

    if user_id in user_api_keys:
        del user_api_keys[user_id]
        if user_id in chats: del chats[user_id]
        await update.message.reply_text("🗑 Ваш API ключ удален.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Ключ не был установлен.")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("🧠 Выберите модель:", reply_markup=get_model_keyboard())

# --- ХЕНДЛЕРЫ ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id): return
    
    await query.answer()
    action, model_alias = query.data.split('_', 1)
    
    if action == 'set':
        real_model_name = AVAILABLE_MODELS.get(model_alias, "gemini-2.5-flash")
        user_models[user_id] = real_model_name
        if user_id in chats: del chats[user_id]
        await query.edit_message_text(text=f"✅ Модель: **{model_alias.upper()}**\nКонтекст сброшен.", parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # ПРОВЕРКА
    if not is_admin(user_id):
        return # Просто игнорируем чужаков, чтобы не спамили

    user_text = update.message.text
    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        configure_genai_for_user(user_id)
        chat = get_chat_session(user_id, current_model_name)
        response = chat.send_message(user_text)
        
        response_text = response.text
        if len(response_text) > 4000:
            for x in range(0, len(response_text), 4000):
                await update.message.reply_text(response_text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error: {e}")
        if "API key" in error_msg or "403" in error_msg:
             await update.message.reply_text("⛔ Ошибка ключа. Проверь /setkey.", parse_mode=ParseMode.MARKDOWN)
        elif "429" in error_msg:
             await update.message.reply_text("⏳ Лимит запросов. Подожди.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"Ошибка: {e}")

async def handle_multimodal_content(update: Update, context: ContextTypes.DEFAULT_TYPE, is_photo: bool):
    user_id = update.effective_user.id
    if not is_admin(user_id): return

    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    if is_photo:
        file_handle = update.message.photo[-1]
        action = ChatAction.UPLOAD_PHOTO
        file_ext = ".jpg"
        prompt_default = "Опиши изображение."
    else: 
        file_handle = update.message.document
        action = ChatAction.UPLOAD_DOCUMENT
        file_ext = os.path.splitext(file_handle.file_name)[1]
        prompt_default = "Проанализируй файл."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)
    telegram_file = await file_handle.get_file()
    file_path = f"temp_{user_id}_{telegram_file.file_unique_id}{file_ext}"
    await telegram_file.download_to_drive(file_path)

    uploaded_file = None
    try:
        configure_genai_for_user(user_id)
        uploaded_file = genai.upload_file(path=file_path)
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED": raise ValueError("File failed.")

        prompt = update.message.caption if update.message.caption else prompt_default
        model = genai.GenerativeModel(current_model_name)
        response = model.generate_content([prompt, uploaded_file])
        await update.message.reply_text(response.text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка файла: {e}")
    finally:
        if uploaded_file:
            try: genai.delete_file(uploaded_file.name)
            except: pass
        if os.path.exists(file_path): os.remove(file_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=False)

# --- ЗАПУСК ---
if __name__ == '__main__':
    logging.info("Запуск бота...")
    
    # 1. ЗАПУСКАЕМ "ФЕЙКОВЫЙ" ВЕБ-СЕРВЕР ДЛЯ RENDER
    # Он работает в отдельном потоке (Thread)
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    # 2. ЗАПУСКАЕМ БОТА
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('model', model_command))
    application.add_handler(CommandHandler('setkey', set_key))
    application.add_handler(CommandHandler('delkey', del_key))
    application.add_handler(CommandHandler('clear', clear_context))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logging.info(f"Бот слушает ID: {ADMIN_ID}")
    application.run_polling(poll_interval=1.0)
