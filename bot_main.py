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
    print("Ошибка: Библиотека 'google-generativeai' не установлена.")
    exit()

# --- КОНФИГУРАЦИЯ ---
# Базовый ключ (администратора/владельца)
DEFAULT_GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') 

if not TELEGRAM_TOKEN:
    logging.error("⛔ ОШИБКА: TELEGRAM_TOKEN не найден.")
    exit(1)

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ (ХРАНИЛИЩЕ В ПАМЯТИ) ---
# ВНИМАНИЕ: При перезагрузке Render эти данные сотрутся!
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_model_keyboard():
    keyboard = [
        [InlineKeyboardButton("🪐 Gemini 3 Pro (Smart)", callback_data='set_gemini-3-pro')],
        [InlineKeyboardButton("🍌 Nano Banana Pro (Vision)", callback_data='set_nano-banana')],
        [InlineKeyboardButton("⚡ Gemini 2.5 Flash (Fast)", callback_data='set_gemini-flash')],
    ]
    return InlineKeyboardMarkup(keyboard)

def configure_genai_for_user(user_id):
    """Настраивает Gemini на ключ конкретного пользователя или дефолтный."""
    # Берем личный ключ, если есть, иначе общий
    api_key = user_api_keys.get(user_id, DEFAULT_GEMINI_KEY)
    
    if not api_key:
        raise ValueError("API Key не найден. Используйте /setkey или настройте переменные окружения.")
        
    genai.configure(api_key=api_key)
    return api_key

def get_chat_session(user_id, model_name):
    # Если сессии нет или модель сменилась — создаем новую
    if user_id not in chats or chats[user_id].model != model_name:
        configure_genai_for_user(user_id) # Важно настроить ключ перед созданием модели
        model = genai.GenerativeModel(model_name)
        chats[user_id] = model.start_chat(history=[])
    return chats[user_id]

# --- КОМАНДЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_models:
        user_models[user_id] = "gemini-2.5-flash"
    
    msg = (
        f"👋 **Привет! Я бот на базе Gemini 3.**\n\n"
        f"🤖 Текущая модель: `{user_models.get(user_id)}`\n"
        f"🔑 Твой API ключ: {'✅ Установлен' if user_id in user_api_keys else '❌ Используется общий'}\n\n"
        "**Команды:**\n"
        "🧹 /clear — **Очистить контекст** (начать новый диалог)\n"
        "🧠 /model — **Сменить модель** (Flash, Pro, Image)\n"
        "🔑 /setkey `ваш_ключ` — Установить свой API ключ\n"
        "🗑 /delkey — Удалить свой API ключ\n"
        "ℹ️ /start — Показать это меню\n\n"
        "👇 Просто отправь текст, фото или файл."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats:
        del chats[user_id]
        await update.message.reply_text("🧹 **Память очищена!** Я забыл всё, о чем мы говорили ранее. Начинаем с чистого листа.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("🧹 Память и так пуста.")

async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        # Получаем текст после команды /setkey
        key = context.args[0] if context.args else None
        if not key:
            await update.message.reply_text("⚠️ Использование: `/setkey AIzaSy...`", parse_mode=ParseMode.MARKDOWN)
            return

        user_api_keys[user_id] = key
        # Сбрасываем текущий чат, чтобы он пересоздался с новым ключом
        if user_id in chats:
            del chats[user_id]
            
        await update.message.reply_text("✅ **API ключ сохранен!** Теперь запросы идут через него.\n\n⚠️ _Примечание: При перезагрузке бота ключ сбросится._", parse_mode=ParseMode.MARKDOWN)
        
        # В целях безопасности можно попробовать удалить сообщение пользователя с ключом
        try:
            await update.message.delete()
        except:
            pass # Если нет прав на удаление
            
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def del_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_api_keys:
        del user_api_keys[user_id]
        if user_id in chats:
            del chats[user_id]
        await update.message.reply_text("🗑 **Ваш API ключ удален.** Возвращаюсь на общий ключ бота.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("У вас и так не установлен личный ключ.")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 Выберите модель Gemini:", reply_markup=get_model_keyboard())

# --- ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, model_alias = query.data.split('_', 1)
    
    if action == 'set':
        user_id = query.from_user.id
        real_model_name = AVAILABLE_MODELS.get(model_alias, "gemini-2.5-flash")
        user_models[user_id] = real_model_name
        
        # Сбрасываем чат при смене модели
        if user_id in chats:
            del chats[user_id]
            
        await query.edit_message_text(
            text=f"✅ Готово! Переключился на **{model_alias.upper()}**\nID: `{real_model_name}`\nКонтекст сброшен.", 
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # 1. Настраиваем ключ (важно делать это перед каждым запросом в такой архитектуре)
        configure_genai_for_user(user_id)
        
        # 2. Получаем сессию
        chat = get_chat_session(user_id, current_model_name)
        
        # 3. Отправляем запрос
        response = chat.send_message(user_text)
        
        # 4. Отправляем ответ (с разбивкой на длинные сообщения)
        response_text = response.text
        if len(response_text) > 4000:
            for x in range(0, len(response_text), 4000):
                await update.message.reply_text(response_text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Ошибка ({user_id}): {e}")
        
        if "API key" in error_msg or "403" in error_msg:
             await update.message.reply_text("⛔ **Ошибка доступа.** Проверьте ваш API ключ (/setkey) или лимиты.", parse_mode=ParseMode.MARKDOWN)
        elif "429" in error_msg:
             await update.message.reply_text("⏳ **Слишком много запросов.** Google просит подождать.", parse_mode=ParseMode.MARKDOWN)
        elif "404" in error_msg:
             await update.message.reply_text(f"⚠️ Модель {current_model_name} недоступна (возможно, нужен платный аккаунт). Попробуй Flash.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"Ошибка: {e}")

async def handle_multimodal_content(update: Update, context: ContextTypes.DEFAULT_TYPE, is_photo: bool):
    user_id = update.effective_user.id
    current_model_name = user_models.get(user_id, "gemini-2.5-flash")
    
    if is_photo:
        file_handle = update.message.photo[-1]
        action = ChatAction.UPLOAD_PHOTO
        file_ext = ".jpg"
        prompt_default = "Опиши, что на изображении."
    else: 
        file_handle = update.message.document
        action = ChatAction.UPLOAD_DOCUMENT
        file_ext = os.path.splitext(file_handle.file_name)[1]
        prompt_default = "Проанализируй этот файл."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

    telegram_file = await file_handle.get_file()
    file_path = f"temp_{user_id}_{telegram_file.file_unique_id}{file_ext}"
    await telegram_file.download_to_drive(file_path)

    uploaded_file = None
    try:
        configure_genai_for_user(user_id) # Настраиваем ключ
        
        uploaded_file = genai.upload_file(path=file_path)
        
        # Ожидание обработки
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            raise ValueError("Google File API error.")

        prompt = update.message.caption if update.message.caption else prompt_default
        
        # Для vision запросов используем generate_content, а не чат-сессию (обычно проще)
        model = genai.GenerativeModel(current_model_name)
        response = model.generate_content([prompt, uploaded_file])
        
        await update.message.reply_text(response.text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logging.error(f"Media Error: {e}")
        await update.message.reply_text(f"Ошибка обработки медиа: {e}")
    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except:
                pass
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_multimodal_content(update, context, is_photo=False)


# --- ЗАПУСК ---
if __name__ == '__main__':
    logging.info("Инициализация бота...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('model', model_command))
    application.add_handler(CommandHandler('setkey', set_key)) # Новое
    application.add_handler(CommandHandler('delkey', del_key)) # Новое
    application.add_handler(CommandHandler('clear', clear_context)) # Новое
    application.add_handler(CommandHandler('reset', clear_context)) # Алиас
    
    # Кнопки
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Сообщения
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logging.info(f"Бот запущен.")
    application.run_polling(poll_interval=1.0)
