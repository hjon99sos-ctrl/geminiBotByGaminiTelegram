облакасодержащий, [30.11.2025 13:24]
import os
import logging
import asyncio
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
    # Эта ошибка сработает, если забыли добавить библиотеку в requirements.txt
    print("Ошибка: Библиотека 'google-generativeai' не установлена.")
    exit()

# --- КОНФИГУРАЦИЯ И КЛЮЧИ (БЕРУТСЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ RENDER) ---

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') 
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') 

# Проверка, что ключи получены
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logging.error("⛔ ОШИБКА: TELEGRAM_TOKEN или GEMINI_API_KEY не найдены в переменных окружения Render.")
    # Принудительно завершаем скрипт, чтобы Render показал ошибку
    exit(1) 

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)

# --- СПИСОК МОДЕЛЕЙ ---
AVAILABLE_MODELS = {
    "gemini-3-pro": "gemini-3-pro-preview",
    "nano-banana": "gemini-3-pro-image",
    "gemini-flash": "gemini-2.5-flash"
}

# Хранилище настроек пользователей: {user_id: "model_id"}
user_models = {}
# Хранилище истории чатов: {user_id: chat_session_object}
chats = {}

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ФУНКЦИИ КЛАВИАТУРЫ ---

def get_model_keyboard():
    keyboard = [
        [InlineKeyboardButton("🪐 Gemini 3 Pro (Smart)", callback_data='set_gemini-3-pro')],
        [InlineKeyboardButton("🍌 Nano Banana Pro (Vision)", callback_data='set_nano-banana')],
        [InlineKeyboardButton("⚡ Gemini 2.5 Flash (Fast)", callback_data='set_gemini-flash')],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- КОМАНДЫ И ХЕНДЛЕРЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_models:
        user_models[user_id] = "gemini-2.5-flash"
    
    await update.message.reply_text(
        f"👋 Привет! Я обновлен до **Gemini 3**.\n\n"
        f"Текущая модель: {user_models.get(user_id)}\n\n"
        "Нажми /model чтобы переключить мозг.\n"
        "Отправь фото, файл или текст.",
        parse_mode=ParseMode.MARKDOWN
    )

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите модель Gemini:", reply_markup=get_model_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, model_alias = query.data.split('_', 1)
    
    if action == 'set':
        user_id = query.from_user.id
        real_model_name = AVAILABLE_MODELS.get(model_alias, "gemini-2.5-flash")
        user_models[user_id] = real_model_name
        
        if user_id in chats:
            del chats[user_id]
            
        await query.edit_message_text(text=f"✅ Готово! Переключился {model_alias.upper()})}**\nID: {real_model_name}", parse_mode=ParseMode.MARKDOWN)

# --- ЛОГИКА ГЕНЕРАЦИИ (ПОМОЩНИКИ) ---

def get_chat_session(user_id, model_name):
    if user_id not in chats or chats[user_id].model != model_name:
        model = genai.GenerativeModel(model_name)
        chats[user_id] = model.start_chat(history=[])
    return chats[user_id]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

облакасодержащий, [30.11.2025 13:24]
try:
        chat = get_chat_session(user_id, current_model_name)
        response = chat.send_message(user_text)
        
        response_text = response.text
        if len(response_text) > 4000:
             await update.message.reply_text(response_text[:4000], parse_mode=ParseMode.MARKDOWN)
             await update.message.reply_text(response_text[4000:], parse_mode=ParseMode.MARKDOWN)
        else:
             await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Ошибка при обработке сообщения: {e}")
        if "404" in error_msg or "not found" in error_msg:
             await update.message.reply_text(f"⚠️ Модель {current_model_name} недоступна. Попробуй Flash через /model.")
        else:
             await update.message.reply_text(f"Ошибка Gemini: {e}")

async def handle_multimodal_content(update: Update, context: ContextTypes.DEFAULT_TYPE, is_photo: bool):
    user_id = update.effective_user.id
    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    # Определяем тип файла и действие
    if is_photo:
        file_handle = update.message.photo[-1]
        action = ChatAction.UPLOAD_PHOTO
        file_ext = ".jpg"
        prompt_default = "Проанализируй это изображение детально."
    else: # Document
        file_handle = update.message.document
        action = ChatAction.UPLOAD_DOCUMENT
        file_ext = os.path.splitext(file_handle.file_name)[1]
        prompt_default = "Проанализируй этот файл и сделай краткое резюме."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

    telegram_file = await file_handle.get_file()
    # Создаем уникальное имя файла на сервере Render
    file_path = f"temp_{user_id}_{telegram_file.file_unique_id}{file_ext}"
    await telegram_file.download_to_drive(file_path)

    uploaded_file = None
    try:
        # Загружаем файл в Gemini File API
        uploaded_file = genai.upload_file(path=file_path)
        
        while uploaded_file.state.name == "PROCESSING":
             await asyncio.sleep(1)
             uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
             raise ValueError("Google не смог обработать этот файл.")

        prompt = update.message.caption if update.message.caption else prompt_default
        
        # Генерируем контент
        vision_model = genai.GenerativeModel(current_model_name)
        response = vision_model.generate_content([prompt, uploaded_file])
        
        await update.message.reply_text(response.text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logging.error(f"Ошибка мультимодальной обработки: {e}")
        await update.message.reply_text(f"Ошибка обработки файла: {e}")
    finally:
        # 3. Чистим
        if uploaded_file:
             try:
                 genai.delete_file(uploaded_file.name) # Удаляем с серверов Gemini
             except Exception as cleanup_e:
                 logging.warning(f"Не удалось удалить файл Gemini: {cleanup_e}")
        if os.path.exists(file_path):
            os.remove(file_path) # Удаляем с сервера Render

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=False)


# --- ЗАПУСК ---
if name == 'main':
    logging.info("Инициализация бота...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Хендлеры команд и кнопок
    application.add_handler(CommandHandler('start', start))

облакасодержащий, [30.11.2025 13:24]
application.add_handler(CommandHandler('model', model_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Хендлеры контента
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logging.info(f"Бот запущен. Токен: {'***' + TELEGRAM_TOKEN[-4:]}")
    # Run polling - запускает бота в режиме ожидания сообщений
    application.run_polling(poll_interval=1.0)