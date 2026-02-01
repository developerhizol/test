import logging
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, 
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в .env файле!")

SUPPORT_CHAT_ID = -1003890154139
FEEDBACK_CHAT_ID = -1003387685111
PUBLIC_CHANNEL = "@bothostru"
WELCOME_IMAGE_URL = "https://radika1.link/2026/01/26/IMG_20260126_172056_104cd0714ee93e44168.jpg"
ADMIN_IDS = [7752488661]

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== СОСТОЯНИЯ FSM ==========
class TicketStates(StatesGroup):
    SELECT_CATEGORY = State()
    SELECT_PRIORITY = State()
    WAITING_FOR_ISSUE = State()
    WAITING_FOR_ADMIN_ID = State()
    WAITING_FOR_FEEDBACK = State()

class AdminStates(StatesGroup):
    WAITING_BROADCAST_MESSAGE = State()

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            category TEXT,
            priority TEXT,
            issue TEXT,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP,
            admin_response TEXT,
            response_time TIMESTAMP,
            message_id INTEGER,
            assigned_to INTEGER,
            in_work_by INTEGER,
            feedback_rating INTEGER,
            feedback_comment TEXT,
            feedback_provided BOOLEAN DEFAULT FALSE,
            admin_chat_id INTEGER,
            can_user_close BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_staff (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            added_by INTEGER,
            added_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            admin_id INTEGER,
            response_text TEXT,
            created_at TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🎫 Создать тикет"), KeyboardButton(text="📋 Мои заявки")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="❓ Частые вопросы"), KeyboardButton(text="📌 Контакты")]
    ]
    
    if is_admin(user_id) or is_support_staff(user_id):
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📊 Общая статистика")],
        [KeyboardButton(text="✅ Решенные заявки"), KeyboardButton(text="❌ Нерешенные заявки")],
        [KeyboardButton(text="👥 Назначить поддержкой")],
        [KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="« Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_categories_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="❌ Ошибка")],
        [KeyboardButton(text="🆕 Новая функция")],
        [KeyboardButton(text="❓ Вопрос")],
        [KeyboardButton(text="📂 Другое")],
        [KeyboardButton(text="« Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_priority_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🟢 Низкий"), KeyboardButton(text="🟡 Средний")],
        [KeyboardButton(text="🔴 Высокий"), KeyboardButton(text="🚨 Критический")],
        [KeyboardButton(text="« Назад к категориям")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(text="❌ Отменить создание")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_ticket_work_keyboard(is_admin: bool = True) -> ReplyKeyboardMarkup:
    """Клавиатура для работы с заявкой"""
    if is_admin:
        keyboard = [[KeyboardButton(text="❌ Закрыть заявку")]]
    else:
        keyboard = [[KeyboardButton(text="❌ Завершить обращение")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_support_staff(user_id: int) -> bool:
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM support_staff WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def can_access_admin(user_id: int) -> bool:
    return is_admin(user_id) or is_support_staff(user_id)

def get_feedback_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для оценки от 1 до 10"""
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"rate_{ticket_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Не оставлять отзыв", callback_data=f"skip_feedback_{ticket_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_feedback_comment_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для комментария к отзыву (без кнопки пропуска)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"skip_feedback_{ticket_id}")]
    ])

async def send_feedback_to_channel(ticket_number: str, rating: int, comment: str, user_info: dict):
    """Отправляет отзыв в канал для отзывов"""
    try:
        stars = "⭐" * rating + "☆" * (10 - rating)
        
        message_text = f"""📝 <b>НОВЫЙ ОТЗЫВ ОТ КЛИЕНТА</b>

🎫 <b>Номер заявки:</b> #{ticket_number}
👤 <b>Клиент:</b> {user_info.get('first_name', 'N/A')} (@{user_info.get('username', 'без username')})
🆔 <b>ID клиента:</b> <code>{user_info.get('user_id', 'N/A')}</code>

⭐ <b>Оценка:</b> {rating}/10
{stars}

📝 <b>Комментарий:</b>
{comment}

──────────────────────────
<i>Спасибо за обратную связь! 💖</i>"""
        
        await bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=message_text
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке отзыва в канал: {e}")
        return False

def format_message_header(ticket_number: str, from_support: bool = True) -> str:
    """Форматирует заголовок сообщения"""
    sender = "поддержки" if from_support else "пользователя"
    return f"""📨 <b>Ответ по заявке #{ticket_number}</b>
──────────────────────────
<b>Сообщение от {sender}:</b>
"""

def format_message_footer() -> str:
    """Форматирует подвал сообщения"""
    return """──────────────────────────
<i>Просто отправьте сообщение в этот чат - оно будет переслано.</i>"""

async def forward_media_to_user(message: Message, user_id: int, ticket_number: str, from_admin: bool = True):
    """Пересылает медиафайлы пользователю или админу"""
    
    try:
        header = format_message_header(ticket_number, from_admin)
        footer = format_message_footer()
        
        if message.text:
            message_text = f"{header}{message.text}\n{footer}"
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Сообщение отправлено."
        
        elif message.photo:
            caption = f"{header}{message.caption or ''}\n{footer}"
            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Фото отправлено."
        
        elif message.video:
            caption = f"{header}{message.caption or ''}\n{footer}"
            await bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=caption,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Видео отправлено."
        
        elif message.video_note:
            await bot.send_video_note(
                chat_id=user_id,
                video_note=message.video_note.file_id
            )
            await bot.send_message(
                chat_id=user_id,
                text=f"{header}Видеосообщение\n{footer}",
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Видеосообщение отправлено."
        
        elif message.voice:
            caption = f"{header}Голосовое сообщение\n{footer}"
            await bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                caption=caption,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Голосовое сообщение отправлено."
        
        elif message.document:
            caption = f"{header}{message.caption or ''}\n{footer}"
            await bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=caption,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Документ отправлен."
        
        elif message.sticker:
            await bot.send_sticker(
                chat_id=user_id,
                sticker=message.sticker.file_id
            )
            await bot.send_message(
                chat_id=user_id,
                text=f"{header}Стикер\n{footer}",
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ Стикер отправлен."
        
        elif message.animation:
            caption = f"{header}{message.caption or ''}\n{footer}"
            await bot.send_animation(
                chat_id=user_id,
                animation=message.animation.file_id,
                caption=caption,
                reply_markup=get_ticket_work_keyboard(not from_admin)
            )
            return True, "✅ GIF отправлен."
        
        else:
            return False, "❌ Этот тип сообщения не поддерживается."
            
    except Exception as e:
        logger.error(f"Ошибка при отправке медиа пользователю {user_id}: {e}")
        return False, f"❌ Не удалось отправить сообщение: {e}"

async def close_ticket_for_user(ticket_id: int, user_id: int, ticket_number: str, closer_name: str, is_user_closing: bool = False):
    """Закрывает заявку и отправляет уведомления"""
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    # Обновляем статус заявки
    cursor.execute('UPDATE tickets SET status = "closed", response_time = ?, can_user_close = FALSE WHERE id = ?', 
                   (datetime.now(), ticket_id))
    conn.commit()
    
    if is_user_closing:
        cursor.execute('SELECT in_work_by FROM tickets WHERE id = ?', (ticket_id,))
        admin_id_result = cursor.fetchone()
        admin_id = admin_id_result[0] if admin_id_result else None
        
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"""📭 <b>Пользователь завершил обращение</b>
──────────────────────────
🎫 <b>Номер заявки:</b> #{ticket_number}
👤 <b>Пользователь:</b> {closer_name}

<i>Заявка закрыта по инициативе пользователя.</i>""",
                    reply_markup=get_main_keyboard(admin_id)
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления админу: {e}")
    
    # Обновляем сообщение в канале поддержки
    cursor.execute('SELECT message_id FROM tickets WHERE id = ?', (ticket_id,))
    message_id_result = cursor.fetchone()
    if message_id_result:
        message_id = message_id_result[0]
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Закрыта", callback_data="ticket_closed")]
            ])
            await bot.edit_message_reply_markup(
                chat_id=SUPPORT_CHAT_ID,
                message_id=message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения в канале: {e}")
    
    conn.close()
    
    # Отправляем пользователю запрос на отзыв С КНОПКАМИ В САМОМ СООБЩЕНИИ
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"""🎉 <b>Ваша заявка #{ticket_number} завершена!</b>
──────────────────────────
🌟 <b>Оцените качество работы:</b>
1 — очень плохо
10 — очень хорошо

Также напишите маленький комментарий к вашей оценке. 
Спасибо что выбрали BotHost! 😊""",
            reply_markup=get_feedback_keyboard(ticket_id)
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса на отзыв: {e}")
        return False

# ========== ОСНОВНЫЕ ХЕНДЛЕРЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    welcome_text = f"""<b>✨ Техническая поддержка BotHost ✨</b>
──────────────────────────
Уважаемый клиент!

Мы ценим ваше время и обеспечиваем:
🚀 <b>Приоритетное обслуживание</b>
⏱️ <b>Гарантированное время ответа:</b> 15 минут
👨‍💼 <b>Персонального менеджера</b>
📊 <b>Подробные отчёты</b>

<b>Для начала работы:</b>
1. Нажмите «🎫 Создать тикет»
2. Опишите ситуацию
3. Выберите приоритет
4. Получите номер заявки
──────────────────────────
<em>Ответим на вашу заявку в кратчайшие сроки 😊</em>"""
    
    if WELCOME_IMAGE_URL and WELCOME_IMAGE_URL.startswith("http"):
        try:
            await message.answer_photo(
                photo=WELCOME_IMAGE_URL,
                caption=welcome_text,
                reply_markup=get_main_keyboard(message.from_user.id)
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось загрузить изображение: {e}")
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "« Назад в меню")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await cmd_start(message)

@dp.message(F.text == "🎫 Создать тикет")
async def create_ticket(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        """<b>📝 Создание заявки</b>
──────────────────────────
<b>Выберите категорию вашего обращения:</b>

❌ <b>Ошибка</b>
<em>Критические ошибки, сбои в работе</em>

🆕 <b>Новая функция</b>
<em>Предложения по улучшению</em>

❓ <b>Вопрос</b>
<em>Консультации и вопросы</em>

📂 <b>Другое</b>
<em>Прочие вопросы</em>""",
        reply_markup=get_categories_keyboard()
    )
    await state.set_state(TicketStates.SELECT_CATEGORY)

@dp.message(TicketStates.SELECT_CATEGORY)
async def process_category(message: Message, state: FSMContext):
    if message.text == "« Назад в меню":
        await state.clear()
        await cmd_start(message)
        return
    
    category_map = {
        "❌ Ошибка": "ERROR",
        "🆕 Новая функция": "FEATURE", 
        "❓ Вопрос": "QUESTION",
        "📂 Другое": "OTHER"
    }
    
    if message.text not in category_map:
        await message.answer("❌ <b>Пожалуйста, выберите категорию из предложенных.</b>")
        return
    
    await state.update_data(category=category_map[message.text])
    await message.answer(
        """<b>⚡ Выбор приоритета</b>
──────────────────────────
<b>Выберите срочность обращения:</b>

🟢 <b>Низкий приоритет</b>
<em>Не критично, ответ в течение 24 часов</em>

🟡 <b>Средний приоритет</b>
<em>Стандартный, ответ в течение 6 часов</em>

🔴 <b>Высокий приоритет</b>
<em>Срочно, ответ в течение 1 часа</em>

🚨 <b>Критический приоритет</b>
<em>Система не работает, ответ в течение 10 минут</em>""",
        reply_markup=get_priority_keyboard()
    )
    await state.set_state(TicketStates.SELECT_PRIORITY)

@dp.message(TicketStates.SELECT_PRIORITY)
async def process_priority(message: Message, state: FSMContext):
    if message.text == "« Назад к категориям":
        await message.answer(
            """<b>📝 Создание заявки</b>
──────────────────────────
<b>Выберите категорию вашего обращения:</b>

❌ <b>Ошибка</b>
<em>Критические ошибки, сбои в работе</em>

🆕 <b>Новая функция</b>
<em>Предложения по улучшению</em>

❓ <b>Вопрос</b>
<em>Консультации и вопросы</em>

📂 <b>Другое</b>
<em>Прочие вопросы</em>""",
            reply_markup=get_categories_keyboard()
        )
        await state.set_state(TicketStates.SELECT_CATEGORY)
        return
    
    priority_map = {
        "🟢 Низкий": "LOW",
        "🟡 Средний": "MEDIUM",
        "🔴 Высокий": "HIGH",
        "🚨 Критический": "CRITICAL"
    }
    
    if message.text not in priority_map:
        await message.answer("❌ <b>Пожалуйста, выберите приоритет из предложенных.</b>")
        return
    
    await state.update_data(priority=priority_map[message.text])
    await message.answer(
        """<b>📝 Описание проблемы</b>
──────────────────────────
<b>Опишите вашу проблему максимально подробно:</b>
• Что произошло?
• Какой результат ожидали?
• Какие шаги предпринимали?

<em>Чем подробнее описание, тем быстрее мы поможем!</em>""",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TicketStates.WAITING_FOR_ISSUE)

@dp.message(TicketStates.WAITING_FOR_ISSUE)
async def process_issue(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await message.answer(
            "❌ <b>Создание заявки отменено.</b>",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    user_data = await state.get_data()
    category = user_data.get('category')
    priority = user_data.get('priority')
    
    if not category or not priority:
        await message.answer("❌ <b>Ошибка:</b> данные не найдены. Начните заново.")
        await state.clear()
        return
    
    # Генерируем номер заявки
    now = datetime.now()
    date_part = now.strftime("%Y%m%d")
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE DATE(created_at) = DATE(?)', (now,))
    count = cursor.fetchone()[0] + 1
    ticket_number = f"BH-{date_part}-{count:04d}"
    
    # Сохраняем заявку
    cursor.execute('''
        INSERT INTO tickets (ticket_number, user_id, username, first_name, category, priority, issue, created_at, can_user_close)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticket_number, message.from_user.id, message.from_user.username, 
          message.from_user.first_name, category, priority, message.text, now, True))
    
    ticket_id = cursor.lastrowid
    conn.commit()
    
    # Отправляем в канал поддержки
    category_display = {
        'ERROR': '❌ Ошибка',
        'FEATURE': '🆕 Новая функция',
        'QUESTION': '❓ Вопрос',
        'OTHER': '📂 Другое'
    }.get(category, category)
    
    priority_display = {
        'LOW': '🟢 Низкий',
        'MEDIUM': '🟡 Средний',
        'HIGH': '🔴 Высокий',
        'CRITICAL': '🚨 Критический'
    }.get(priority, priority)
    
    response_time = {
        'CRITICAL': '10 минут',
        'HIGH': '1 час',
        'MEDIUM': '6 часов',
        'LOW': '24 часа'
    }.get(priority, '24 часа')
    
    message_text = f"""🚨 <b>НОВАЯ ЗАЯВКА #{ticket_number}</b> 🚨
──────────────────────────
📂 <b>Категория:</b> {category_display}
⚡ <b>Приоритет:</b> {priority_display}
👤 <b>Клиент:</b> {message.from_user.first_name} (@{message.from_user.username or 'без username'})
🆔 <b>ID:</b> <code>{message.from_user.id}</code>
⏱️ <b>Ожидаемое время ответа:</b> {response_time}

📝 <b>Описание:</b>
{message.text[:500]}{'...' if len(message.text) > 500 else ''}
──────────────────────────"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"respond_{ticket_id}")]
    ])
    
    try:
        msg = await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=message_text,
            reply_markup=keyboard
        )
        cursor.execute('UPDATE tickets SET message_id = ? WHERE id = ?', (msg.message_id, ticket_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при отправке в канал поддержки: {e}")
    
    conn.close()
    
    # Отправляем подтверждение пользователю
    category_display = {
        'ERROR': '❌ Ошибка',
        'FEATURE': '🆕 Новая функция', 
        'QUESTION': '❓ Вопрос',
        'OTHER': '📂 Другое'
    }.get(category, category)
    
    priority_display = {
        'LOW': '🟢 Низкий',
        'MEDIUM': '🟡 Средний',
        'HIGH': '🔴 Высокий',
        'CRITICAL': '🚨 Критический'
    }.get(priority, priority)
    
    response_time = {
        'CRITICAL': '10 минут ⏱️',
        'HIGH': '1 час ⏱️',
        'MEDIUM': '6 часов ⏱️',
        'LOW': '24 часа ⏱️'
    }.get(priority, '24 часа ⏱️')
    
    await message.answer(
        f"""✅ <b>Заявка создана успешно!</b>
──────────────────────────
🎫 <b>Номер заявки:</b> <code>{ticket_number}</code>
📂 <b>Категория:</b> {category_display}
⚡ <b>Приоритет:</b> {priority_display}
⏱️ <b>Ожидаемое время ответа:</b> {response_time}

📋 <b>Статус заявки можно отслеживать в разделе «Мои заявки»</b>

😊 <b>Спасибо за обращение в BotHost!</b>""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    
    await state.clear()

# ========== INLINE КНОПКИ ==========
@dp.callback_query(F.data.startswith("respond_"))
async def handle_respond_button(callback: CallbackQuery):
    if not can_access_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав для этого действия.", show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[1])
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, ticket_number, issue, in_work_by FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    
    if not ticket:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        conn.close()
        return
    
    user_id, ticket_number, issue, in_work_by = ticket
    
    if in_work_by and in_work_by != callback.from_user.id:
        await callback.answer("❌ Эту заявку уже взял другой сотрудник.", show_alert=True)
        conn.close()
        return
    
    cursor.execute('UPDATE tickets SET in_work_by = ?, status = "in_progress", admin_chat_id = ?, can_user_close = TRUE WHERE id = ?', 
                   (callback.from_user.id, callback.from_user.id, ticket_id))
    conn.commit()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ В работе", callback_data="in_work")]
    ])
    
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
        await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=f"""🔄 <b>Заявка #{ticket_number} взята в работу</b>
──────────────────────────
👤 <b>Отвечает:</b> {callback.from_user.first_name} (@{callback.from_user.username or 'нет'})"""
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")
    
    try:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=f"""💬 <b>Вы взяли в работу заявку #{ticket_number}</b>
──────────────────────────
👤 <b>Клиент:</b> ID {user_id}
🎫 <b>Номер заявки:</b> {ticket_number}

📝 <b>Описание проблемы:</b>
{issue[:500]}{'...' if len(issue) > 500 else ''}
──────────────────────────
<b>Теперь вы можете общаться с пользователем напрямую через этого бота.</b>
<b>Просто отправляйте сообщения в этот чат - они будут пересылаться пользователю.</b>

<b>Поддерживаются:</b> текст, фото, видео, видеосообщения, голосовые, документы, стикеры, GIF

<b>Для завершения диалога нажмите кнопку «❌ Закрыть заявку» ниже.</b>

<i>Отправьте ваше первое сообщение пользователю (просто напишите или отправьте файл):</i>""",
            reply_markup=get_ticket_work_keyboard(is_admin=True)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения админу: {e}")
    
    await callback.answer()

@dp.callback_query(F.data == "in_work")
async def handle_in_work_button(callback: CallbackQuery):
    await callback.answer("✅ Эта заявка уже взята в работу", show_alert=True)

@dp.callback_query(F.data == "ticket_closed")
async def handle_ticket_closed_button(callback: CallbackQuery):
    await callback.answer("❌ Эта заявка уже закрыта", show_alert=True)

@dp.callback_query(F.data.startswith("rate_"))
async def handle_rate_callback(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    if len(data_parts) != 3:
        await callback.answer("❌ Ошибка обработки оценки")
        return
    
    ticket_id = int(data_parts[1])
    rating = int(data_parts[2])
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET feedback_rating = ? WHERE id = ?', (rating, ticket_id))
    conn.commit()
    
    cursor.execute('SELECT ticket_number, user_id, username, first_name FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    ticket_number = ticket[0] if ticket else "N/A"
    user_id = ticket[1] if ticket else None
    username = ticket[2] if ticket else None
    first_name = ticket[3] if ticket else None
    
    conn.close()
    
    await state.update_data(
        waiting_for_feedback=True,
        feedback_ticket_id=ticket_id,
        feedback_rating=rating,
        feedback_user_info={
            'user_id': user_id,
            'username': username,
            'first_name': first_name
        }
    )
    
    await callback.message.edit_text(
        f"""✅ <b>Спасибо за оценку {rating}/10!</b>
──────────────────────────
<b>Теперь напишите небольшой комментарий к вашей оценке.</b>

<i>Для отмены нажмите «❌ Отменить»</i>""",
        reply_markup=get_feedback_comment_keyboard(ticket_id)
    )
    
    await state.set_state(TicketStates.WAITING_FOR_FEEDBACK)
    await callback.answer()

@dp.callback_query(F.data.startswith("skip_feedback_"))
async def handle_skip_feedback(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET feedback_provided = TRUE WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        """❤️ <b>Спасибо за ваш отзыв.</b>
──────────────────────────
<b>Хорошего дня! 😊</b>""",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await state.clear()
    await callback.answer()

# ========== ОБРАБОТЧИК ДЛЯ КОММЕНТАРИЯ К ОТЗЫВУ ==========
@dp.message(TicketStates.WAITING_FOR_FEEDBACK)
async def handle_feedback_comment(message: Message, state: FSMContext):
    user_data = await state.get_data()
    ticket_id = user_data.get('feedback_ticket_id')
    rating = user_data.get('feedback_rating')
    user_info = user_data.get('feedback_user_info', {})
    
    if not ticket_id or not rating:
        await message.answer("❌ <b>Ошибка:</b> не найдена информация об отзыве.")
        await state.clear()
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET feedback_comment = ?, feedback_provided = TRUE WHERE id = ?', 
                   (message.text, ticket_id))
    conn.commit()
    
    cursor.execute('SELECT ticket_number FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    ticket_number = ticket[0] if ticket else "N/A"
    
    conn.close()
    
    feedback_sent = await send_feedback_to_channel(
        ticket_number=ticket_number,
        rating=rating,
        comment=message.text,
        user_info=user_info
    )
    
    if feedback_sent:
        logger.info(f"Отзыв по заявке #{ticket_number} отправлен в канал отзывов")
    else:
        logger.warning(f"Не удалось отправить отзыв по заявке #{ticket_number} в канал")
    
    await message.answer(
        """❤️ <b>Спасибо за ваш отзыв.</b>
──────────────────────────
<b>Хорошего дня! 😊</b>""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    
    await state.clear()

# ========== ОБРАБОТЧИКИ КНОПОК ==========
@dp.message(F.text == "📋 Мои заявки")
async def my_tickets(message: Message):
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ticket_number, category, priority, issue, status, created_at 
        FROM tickets 
        WHERE user_id = ? 
        ORDER BY created_at DESC
        LIMIT 5
    ''', (message.from_user.id,))
    
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer(
            """📭 <b>У вас нет активных заявок.</b>
──────────────────────────
<b>Нажмите «🎫 Создать тикет» для обращения в поддержку.</b>""",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    response = "📋 <b>Ваши последние заявки:</b>\n\n"
    
    for ticket in tickets:
        ticket_number, category, priority, issue, status, created_at = ticket
        
        status_emoji = {
            'open': '🟢',
            'in_progress': '🟡',
            'closed': '✅',
            'rejected': '❌'
        }.get(status, '⚪')
        
        category_emoji = {
            'ERROR': '❌',
            'FEATURE': '🆕',
            'QUESTION': '❓',
            'OTHER': '📂'
        }.get(category, '📄')
        
        priority_emoji = {
            'LOW': '🟢',
            'MEDIUM': '🟡',
            'HIGH': '🔴',
            'CRITICAL': '🚨'
        }.get(priority, '⚪')
        
        created_date = created_at.split(' ')[0] if ' ' in created_at else created_at
        
        response += f"""──────────────────────────
🎫 <b>{ticket_number}</b>
{status_emoji} <b>Статус:</b> {status}
{category_emoji} <b>Категория:</b> {category}
{priority_emoji} <b>Приоритет:</b> {priority}
📅 <b>Создана:</b> {created_date}

📝 <b>Описание:</b>
{issue[:100]}{'...' if len(issue) > 100 else ''}

"""
    
    response += "──────────────────────────"
    
    await message.answer(response, reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE user_id = ?', (message.from_user.id,))
    user_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE user_id = ? AND status = "closed"', (message.from_user.id,))
    closed_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT AVG(feedback_rating) FROM tickets WHERE user_id = ? AND feedback_rating IS NOT NULL', (message.from_user.id,))
    avg_rating = cursor.fetchone()[0] or 0
    
    conn.close()
    
    await message.answer(
        f"""📊 <b>Ваша статистика</b>
──────────────────────────
🎫 <b>Всего заявок:</b> {user_tickets}
✅ <b>Решено:</b> {closed_tickets}
❌ <b>В работе:</b> {user_tickets - closed_tickets}
⭐ <b>Ваша средняя оценка:</b> {avg_rating:.1f}/10

<b>Эффективность поддержки для вас:</b> {int((closed_tickets/user_tickets*100) if user_tickets > 0 else 0)}%""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "❓ Частые вопросы")
async def show_faq(message: Message):
    faq_text = """❓ <b>Часто задаваемые вопросы</b>
──────────────────────────
<b>1. Как долго ждать ответа?</b>
• 🚨 Критические: 10 минут
• 🔴 Высокий: 1 час
• 🟡 Средний: 6 часов
• 🟢 Низкий: 24 часа

<b>2. Как отследить статус заявки?</b>
Используйте раздел «📋 Мои заявки»

<b>3. Что делать, если проблема срочная?</b>
Выбирайте приоритет «🚨 Критический»

<b>4. Как связаться с персональным менеджером?</b>
Укажите в заявке «Требуется менеджер»

<b>5. Рабочее время поддержки?</b>
Круглосуточно 24/7 🕒"""
    
    await message.answer(faq_text, reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "📌 Контакты")
async def show_contacts(message: Message):
    contacts_text = f"""📌 <b>Контакты BotHost</b>
──────────────────────────
✉️ <b>Email:</b>
support@bothost.ru

🌐 <b>Сайт:</b>
www.bothost.ru

📱 <b>Наш канал:</b>
{PUBLIC_CHANNEL}

🕒 <b>Поддержка 24/7:</b>
В этом боте — круглосуточно!"""
    
    await message.answer(contacts_text, reply_markup=get_main_keyboard(message.from_user.id))

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: Message):
    if not can_access_admin(message.from_user.id):
        await message.answer(
            "⛔ <b>У вас нет доступа к админ-панели.</b>",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    admin_status = "👑 Владелец" if is_admin(message.from_user.id) else "🛠️ Поддержка"
    
    await message.answer(
        f"""<b>{admin_status} | Панель управления</b>
──────────────────────────
<b>Выберите действие:</b>""",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📊 Общая статистика")
async def show_admin_stats(message: Message):
    if not can_access_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM tickets')
    total_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status = "closed"')
    closed_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status != "closed"')
    open_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM tickets')
    unique_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM support_staff')
    support_count = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT AVG((julianday(response_time) - julianday(created_at)) * 24 * 60)
        FROM tickets WHERE response_time IS NOT NULL
    ''')
    avg_response = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE feedback_rating IS NOT NULL')
    feedback_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT AVG(feedback_rating) FROM tickets WHERE feedback_rating IS NOT NULL')
    avg_rating = cursor.fetchone()[0] or 0
    
    conn.close()
    
    await message.answer(
        f"""📊 <b>Общая статистика BotHost</b>
──────────────────────────
🎫 <b>Всего заявок:</b> {total_tickets}
✅ <b>Решено:</b> {closed_tickets}
❌ <b>В работе:</b> {open_tickets}
👥 <b>Уникальных пользователей:</b> {unique_users}
🛠️ <b>Сотрудников поддержки:</b> {support_count}
⏱️ <b>Среднее время ответа:</b> {int(avg_response or 0)} мин.
⭐ <b>Средняя оценка:</b> {avg_rating:.1f}/10 ({feedback_count} отзывов)

<b>Эффективность:</b> {int((closed_tickets/total_tickets*100) if total_tickets > 0 else 0)}%""",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "✅ Решенные заявки")
async def show_solved_tickets(message: Message):
    if not can_access_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ticket_number, username, category, priority, created_at, feedback_rating 
        FROM tickets WHERE status = "closed" 
        ORDER BY created_at DESC LIMIT 10
    ''')
    
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer("✅ <b>Нет решенных заявок.</b>", reply_markup=get_admin_keyboard())
        return
    
    response = "✅ <b>Последние решенные заявки:</b>\n\n"
    for ticket in tickets:
        ticket_num, username, category, priority, created_at, rating = ticket
        rating_display = f"⭐ {rating}/10" if rating else "📭 Без отзыва"
        created_date = created_at.split(' ')[0] if ' ' in created_at else created_at
        response += f"""🎫 <b>{ticket_num}</b>
👤 @{username or 'без username'}
📂 {category}
⭐ {rating_display}
📅 {created_date}
──────────────────────────
"""
    
    await message.answer(response, reply_markup=get_admin_keyboard())

@dp.message(F.text == "❌ Нерешенные заявки")
async def show_unsolved_tickets(message: Message):
    if not can_access_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, ticket_number, username, category, priority, created_at 
        FROM tickets WHERE status != "closed" 
        ORDER BY 
            CASE priority 
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 5
            END,
            created_at ASC
        LIMIT 10
    ''')
    
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer("✅ <b>Все заявки решены!</b>", reply_markup=get_admin_keyboard())
        return
    
    response = "❌ <b>Заявки в работе:</b>\n\n"
    for ticket in tickets:
        ticket_id, ticket_num, username, category, priority, created_at = ticket
        priority_emoji = {'CRITICAL': '🚨', 'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(priority, '⚪')
        created_date = created_at.split(' ')[0] if ' ' in created_at else created_at
        response += f"""{priority_emoji} <b>{ticket_num}</b> (ID: {ticket_id})
👤 @{username or 'без username'}
📂 {category}
📅 {created_date}
──────────────────────────
"""
    
    await message.answer(response, reply_markup=get_admin_keyboard())

@dp.message(F.text == "👥 Назначить поддержкой")
async def assign_support(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ <b>Только владельцы могут назначать поддержку.</b>")
        return
    
    await message.answer(
        """👥 <b>Назначение сотрудника поддержки</b>
──────────────────────────
<b>Отправьте Telegram ID пользователя, которого хотите добавить в поддержку.</b>
<em>ID можно получить с помощью бота @userinfobot</em>

<i>Для отмены нажмите «« Назад в меню»</i>""",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="« Назад в меню")]], resize_keyboard=True)
    )
    await state.set_state(TicketStates.WAITING_FOR_ADMIN_ID)

@dp.message(TicketStates.WAITING_FOR_ADMIN_ID)
async def process_admin_id(message: Message, state: FSMContext):
    if message.text == "« Назад в меню":
        await state.clear()
        await admin_panel(message)
        return
    
    try:
        new_admin_id = int(message.text)
    except ValueError:
        await message.answer("❌ <b>Неверный формат ID.</b> Отправьте числовой ID.")
        return
    
    if new_admin_id in ADMIN_IDS:
        await message.answer("⚠️ <b>Этот пользователь уже является владельцем.</b>")
        await state.clear()
        await admin_panel(message)
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    try:
        user_info = await bot.get_chat(new_admin_id)
        username = user_info.username or ""
        first_name = user_info.first_name or ""
    except:
        username = ""
        first_name = ""
    
    cursor.execute('''
        INSERT OR REPLACE INTO support_staff (user_id, username, first_name, added_by, added_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (new_admin_id, username, first_name, message.from_user.id, datetime.now()))
    
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(
            chat_id=new_admin_id,
            text=f"""🛠️ <b>Вас назначили сотрудником поддержки BotHost!</b>
──────────────────────────
<b>Теперь вам доступна админ-панель в боте.</b>

<b>Ваши возможности:</b>
• Просмотр заявок
• Ответ пользователям
• Закрытие заявок

<b>Начните работу:</b> @{(await bot.me()).username}"""
        )
    except:
        pass
    
    await message.answer(
        f"""✅ <b>Пользователь {new_admin_id} добавлен в поддержку!</b>
──────────────────────────
👤 <b>Имя:</b> {first_name}
📱 <b>Username:</b> @{username or 'нет'}""",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

@dp.message(F.text == "📢 Рассылка")
async def start_broadcast(message: Message, state: FSMContext):
    if not can_access_admin(message.from_user.id):
        return
    
    await message.answer(
        """📢 <b>Отправьте сообщение для рассылки</b>
──────────────────────────
<b>Можно отправить текст, фото с подписью или документ.</b>

<i>Для отмены нажмите «« Назад в меню»</i>""",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="« Назад в меню")]], resize_keyboard=True)
    )
    await state.set_state(AdminStates.WAITING_BROADCAST_MESSAGE)

@dp.message(AdminStates.WAITING_BROADCAST_MESSAGE)
async def process_broadcast(message: Message, state: FSMContext):
    if message.text == "« Назад в меню":
        await state.clear()
        await admin_panel(message)
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM tickets')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        await message.answer("❌ <b>Нет пользователей для рассылки.</b>", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    
    success = 0
    failed = 0
    
    await message.answer(f"📢 <b>Начинаю рассылку для {len(users)} пользователей...</b>")
    
    for user_row in users:
        user_id = user_row[0]
        try:
            if message.text:
                await bot.send_message(user_id, message.text)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.document:
                await bot.send_document(user_id, message.document.file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption)
            success += 1
            import asyncio
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Ошибка при отправке пользователю {user_id}: {e}")
            failed += 1
    
    await message.answer(
        f"""📢 <b>Рассылка завершена!</b>
──────────────────────────
✅ <b>Успешно отправлено:</b> {success}
❌ <b>Не отправлено:</b> {failed}
👥 <b>Всего пользователей:</b> {len(users)}""",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

# ========== ЗАКРЫТИЕ ЗАЯВОК ==========
@dp.message(F.text == "❌ Закрыть заявку")
async def handle_admin_close_ticket(message: Message):
    if not can_access_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, ticket_number, in_work_by 
        FROM tickets 
        WHERE in_work_by = ? AND status = 'in_progress'
        ORDER BY created_at DESC LIMIT 1
    ''', (message.from_user.id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        await message.answer("❌ <b>Не найдена активная заявка.</b>")
        conn.close()
        return
    
    ticket_id, user_id, ticket_number, in_work_by = ticket
    
    if in_work_by != message.from_user.id:
        await message.answer("❌ <b>Не вы взяли заявку, не вам и закрывать.</b>")
        conn.close()
        return
    
    conn.close()
    
    closer_name = f"{message.from_user.first_name} (@{message.from_user.username or 'нет'})"
    await close_ticket_for_user(ticket_id, user_id, ticket_number, closer_name, is_user_closing=False)
    
    await message.answer(
        f"""✅ <b>Заявка #{ticket_number} закрыта.</b>
──────────────────────────
👤 <b>Пользователю отправлен запрос на отзыв.</b>""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "❌ Завершить обращение")
async def handle_user_close_ticket(message: Message):
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, ticket_number, can_user_close
        FROM tickets 
        WHERE user_id = ? AND status = 'in_progress'
        ORDER BY created_at DESC LIMIT 1
    ''', (message.from_user.id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        await message.answer("❌ <b>Не найдена активная заявка.</b>")
        conn.close()
        return
    
    ticket_id, ticket_number, can_user_close = ticket
    
    if not can_user_close:
        await message.answer("❌ <b>Вы не можете завершить это обращение.</b>")
        conn.close()
        return
    
    conn.close()
    
    closer_name = f"{message.from_user.first_name} (@{message.from_user.username or 'нет'})"
    await close_ticket_for_user(ticket_id, message.from_user.id, ticket_number, closer_name, is_user_closing=True)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
@dp.message(lambda message: can_access_admin(message.from_user.id))
async def handle_admin_message(message: Message):
    # Проверяем, не команда ли это админ-панели
    if message.text in ["👑 Админ-панель", "📊 Общая статистика", "✅ Решенные заявки", 
                       "❌ Нерешенные заявки", "👥 Назначить поддержкой", "📢 Рассылка", 
                       "« Назад в меню"]:
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, ticket_number, in_work_by 
        FROM tickets 
        WHERE in_work_by = ? AND status = 'in_progress'
        ORDER BY created_at DESC LIMIT 1
    ''', (message.from_user.id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        conn.close()
        return
    
    ticket_id, user_id, ticket_number, in_work_by = ticket
    
    if in_work_by != message.from_user.id:
        await message.answer("❌ <b>Эта заявка взята другим сотрудником.</b>")
        conn.close()
        return
    
    response_text = message.text or message.caption or "[медиафайл]"
    
    cursor.execute('''
        INSERT INTO responses (ticket_id, admin_id, response_text, created_at)
        VALUES (?, ?, ?, ?)
    ''', (ticket_id, message.from_user.id, response_text, datetime.now()))
    conn.commit()
    
    success, result_message = await forward_media_to_user(message, user_id, ticket_number, from_admin=True)
    
    if success:
        await message.answer(result_message, reply_markup=get_ticket_work_keyboard(is_admin=True))
    else:
        await message.answer(result_message, reply_markup=get_ticket_work_keyboard(is_admin=True))
    
    conn.close()

@dp.message()
async def handle_user_message(message: Message):
    if message.text in ["/start", "🎫 Создать тикет", "📋 Мои заявки", "📊 Статистика", 
                       "❓ Частые вопросы", "📌 Контакты", "« Назад в меню", 
                       "❌ Отменить создание", "« Назад к категориям"]:
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    # Проверяем, есть ли у пользователя активная заявка
    cursor.execute('''
        SELECT id, ticket_number, in_work_by, can_user_close
        FROM tickets 
        WHERE user_id = ? AND status = 'in_progress'
        ORDER BY created_at DESC LIMIT 1
    ''', (message.from_user.id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        conn.close()
        return
    
    ticket_id, ticket_number, admin_id, can_user_close = ticket
    
    if not admin_id:
        await message.answer("❌ <b>Ваша заявка еще не взята в работу.</b>")
        conn.close()
        return
    
    response_text = message.text or message.caption or "[медиафайл]"
    
    cursor.execute('''
        INSERT INTO responses (ticket_id, admin_id, response_text, created_at)
        VALUES (?, ?, ?, ?)
    ''', (ticket_id, message.from_user.id, response_text, datetime.now()))
    conn.commit()
    
    success, result_message = await forward_media_to_user(message, admin_id, ticket_number, from_admin=False)
    
    if success:
        await message.answer("✅ <b>Ваше сообщение отправлено поддержке.</b>", reply_markup=get_ticket_work_keyboard(is_admin=False))
    else:
        await message.answer(result_message, reply_markup=get_ticket_work_keyboard(is_admin=False))
    
    conn.close()

# ========== ЗАПУСК БОТА ==========
async def main():
    init_db()
    
    print("✨" * 40)
    print("🤖 Бот техподдержки BotHost запущен (aiogram 3)!")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print(f"📢 Канал для заявок: {SUPPORT_CHAT_ID}")
    print(f"⭐ Канал для отзывов: {FEEDBACK_CHAT_ID}")
    print(f"📱 Публичный канал: {PUBLIC_CHANNEL}")
    print("✅ Система отзывов включена")
    print("✅ Поддержка медиафайлов включена")
    print("✅ Пользователь может закрывать заявки")
    print("✨" * 40)
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())