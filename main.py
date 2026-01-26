import logging
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv
from enum import Enum

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
    WAITING_FOR_RESPONSE_TO_USER = State()

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
            assigned_to INTEGER
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

# ========== ОСНОВНЫЕ ХЕНДЛЕРЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = f"""<b>🏢 Техническая служба поддержки BotHost</b>
─────────────────────────────
Уважаемый клиент!

Мы ценим ваше время и обеспечиваем:
• 🚀 Приоритетное обслуживание
• ⏱️ Гарантированное время ответа: <b>10 минут</b>
• 👨‍💼 Персонального менеджера
• 📊 Подробные отчёты

Для начала работы:
1. Нажмите «Создать тикет»
2. Опишите ситуацию
3. Выберите приоритет
4. Получите номер заявки
─────────────────────────────
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

@dp.message(F.text == "🎫 Создать тикет")
async def create_ticket(message: Message, state: FSMContext):
    await message.answer(
        "<b>📝 Создание заявки</b>\n"
        "─────────────────────────────\n"
        "Выберите категорию вашего обращения:\n\n"
        "<b>❌ Ошибка</b>\n"
        "<i>Критические ошибки, сбои в работе</i>\n\n"
        "<b>🆕 Новая функция</b>\n"
        "<i>Предложения по улучшению</i>\n\n"
        "<b>❓ Вопрос</b>\n"
        "<i>Консультации и вопросы</i>\n\n"
        "<b>📂 Другое</b>\n"
        "<i>Прочие вопросы</i>",
        reply_markup=get_categories_keyboard()
    )
    await state.set_state(TicketStates.SELECT_CATEGORY)

@dp.message(TicketStates.SELECT_CATEGORY, F.text.in_(["❌ Ошибка", "🆕 Новая функция", "❓ Вопрос", "📂 Другое"]))
async def process_category(message: Message, state: FSMContext):
    category_map = {
        "❌ Ошибка": "ERROR",
        "🆕 Новая функция": "FEATURE", 
        "❓ Вопрос": "QUESTION",
        "📂 Другое": "OTHER"
    }
    
    await state.update_data(category=category_map[message.text])
    await message.answer(
        "<b>⚡ Выбор приоритета</b>\n"
        "─────────────────────────────\n"
        "Выберите срочность обращения:\n\n"
        "<b>🟢 Низкий приоритет</b>\n"
        "<i>Не критично, ответ в течение 24 часов</i>\n\n"
        "<b>🟡 Средний приоритет</b>\n"
        "<i>Стандартный, ответ в течение 6 часов</i>\n\n"
        "<b>🔴 Высокий приоритет</b>\n"
        "<i>Срочно, ответ в течение 1 часа</i>\n\n"
        "<b>🚨 Критический приоритет</b>\n"
        "<i>Система не работает, ответ в течение 10 минут</i>",
        reply_markup=get_priority_keyboard()
    )
    await state.set_state(TicketStates.SELECT_PRIORITY)

@dp.message(TicketStates.SELECT_PRIORITY, F.text.in_(["🟢 Низкий", "🟡 Средний", "🔴 Высокий", "🚨 Критический"]))
async def process_priority(message: Message, state: FSMContext):
    priority_map = {
        "🟢 Низкий": "LOW",
        "🟡 Средний": "MEDIUM",
        "🔴 Высокий": "HIGH",
        "🚨 Критический": "CRITICAL"
    }
    
    await state.update_data(priority=priority_map[message.text])
    await message.answer(
        "<b>📝 Описание проблемы</b>\n"
        "─────────────────────────────\n"
        "Опишите вашу проблему максимально подробно:\n"
        "• Что произошло?\n"
        "• Какой результат ожидали?\n"
        "• Какие шаги предпринимали?\n\n"
        "<i>Чем подробнее описание, тем быстрее мы поможем!</i>",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TicketStates.WAITING_FOR_ISSUE)

@dp.message(TicketStates.WAITING_FOR_ISSUE, F.text)
async def process_issue(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await message.answer(
            "❌ Создание заявки отменено.\nВозвращаю в главное меню.",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    user_data = await state.get_data()
    category = user_data.get('category')
    priority = user_data.get('priority')
    
    if not category or not priority:
        await message.answer("Ошибка: данные не найдены. Начните заново.")
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
        INSERT INTO tickets (ticket_number, user_id, username, first_name, category, priority, issue, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticket_number, message.from_user.id, message.from_user.username, 
          message.from_user.first_name, category, priority, message.text, now))
    
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Отправляем в канал поддержки
    await send_to_support_channel(ticket_id, ticket_number, message.from_user, category, priority, message.text)
    
    # Отправляем подтверждение пользователю
    await send_ticket_confirmation(message, ticket_number, category, priority)
    
    await state.clear()

async def send_to_support_channel(ticket_id: int, ticket_number: str, user, category: str, priority: str, issue: str):
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
    
    message_text = f"""🚨 <b>НОВАЯ ЗАЯВКА #{ticket_number}</b> 🚨

<b>📂 Категория:</b> {category_display}
<b>⚡ Приоритет:</b> {priority_display}
<b>👤 Клиент:</b> {user.first_name} (@{user.username or 'без username'})
<b>🆔 ID:</b> <code>{user.id}</code>
<b>🕒 Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

<b>📝 Описание:</b>
{issue[:500]}{'...' if len(issue) > 500 else ''}

<b>⏱️ Ожидаемое время ответа:</b> {'10 минут' if priority == 'CRITICAL' else '1 час' if priority == 'HIGH' else '6 часов' if priority == 'MEDIUM' else '24 часа'}"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Ответить", callback_data=f"respond_{ticket_id}"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close_{ticket_id}")
        ]
    ])
    
    try:
        msg = await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=message_text,
            reply_markup=keyboard
        )
        
        conn = sqlite3.connect('bothost_support.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE tickets SET message_id = ? WHERE id = ?', (msg.message_id, ticket_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка при отправке в канал поддержки: {e}")

async def send_ticket_confirmation(message: Message, ticket_number: str, category: str, priority: str):
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
    
    await message.answer(
        f"""✅ <b>Заявка создана успешно!</b>

<b>🎫 Номер заявки:</b> <code>{ticket_number}</code>
<b>📂 Категория:</b> {category_display}
<b>⚡ Приоритет:</b> {priority_display}
<b>🕒 Время создания:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

📋 Статус заявки можно отслеживать в разделе «Мои заявки»

<b>⏱️ Ожидаемое время ответа:</b> {'10 минут ⏱️' if priority == 'CRITICAL' else '1 час ⏱️' if priority == 'HIGH' else '6 часов ⏱️' if priority == 'MEDIUM' else '24 часа ⏱️'}

Спасибо за обращение в BotHost! 🏢""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: Message):
    if not can_access_admin(message.from_user.id):
        await message.answer(
            "⛔ У вас нет доступа к админ-панели.",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    admin_status = "👑 Владелец" if is_admin(message.from_user.id) else "🛠️ Поддержка"
    
    await message.answer(
        f"<b>{admin_status} | Панель управления</b>\n"
        "─────────────────────────────\n"
        "Выберите действие:",
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
    
    conn.close()
    
    await message.answer(
        f"""📊 <b>Общая статистика BotHost</b>

🎫 Всего заявок: <b>{total_tickets}</b>
✅ Решено: <b>{closed_tickets}</b>
❌ В работе: <b>{open_tickets}</b>
👥 Уникальных пользователей: <b>{unique_users}</b>
🛠️ Сотрудников поддержки: <b>{support_count}</b>
⏱️ Среднее время ответа: <b>{int(avg_response or 0)} мин.</b>

<b>Эффективность:</b> {int((closed_tickets/total_tickets*100) if total_tickets > 0 else 0)}%""",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "👥 Назначить поддержкой")
async def assign_support(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только владельцы могут назначать поддержку.")
        return
    
    await message.answer(
        "👥 <b>Назначение сотрудника поддержки</b>\n\n"
        "Отправьте Telegram ID пользователя, которого хотите добавить в поддержку.\n"
        "ID можно получить с помощью бота @userinfobot\n\n"
        "<i>Для отмены нажмите «« Назад в меню»</i>",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="« Назад в меню")]], resize_keyboard=True)
    )
    await state.set_state(TicketStates.WAITING_FOR_ADMIN_ID)

@dp.message(TicketStates.WAITING_FOR_ADMIN_ID, F.text == "« Назад в меню")
async def cancel_admin_assign(message: Message, state: FSMContext):
    await state.clear()
    await admin_panel(message)

@dp.message(TicketStates.WAITING_FOR_ADMIN_ID, F.text)
async def process_admin_id(message: Message, state: FSMContext):
    try:
        new_admin_id = int(message.text)
    except ValueError:
        await message.answer("❌ Неверный формат ID. Отправьте числовой ID.")
        return
    
    if new_admin_id in ADMIN_IDS:
        await message.answer("⚠️ Этот пользователь уже является владельцем.")
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
    
    # Уведомляем нового сотрудника
    try:
        await bot.send_message(
            chat_id=new_admin_id,
            text=f"""🛠️ <b>Вас назначили сотрудником поддержки BotHost!</b>

Теперь вам доступна админ-панель в боте.
Ваши возможности:
• Просмотр заявок
• Ответ пользователям
• Закрытие заявок

Начните работу: @{(await bot.me()).username}"""
        )
    except:
        pass
    
    await message.answer(
        f"✅ Пользователь {new_admin_id} добавлен в поддержку!",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

# ========== INLINE КНОПКИ ==========
@dp.callback_query(F.data.startswith("respond_"))
async def handle_respond_button(callback: CallbackQuery, state: FSMContext):
    if not can_access_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав для этого действия.", show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[1])
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, ticket_number, issue FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    conn.close()
    
    if not ticket:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return
    
    user_id, ticket_number, issue = ticket
    
    await state.update_data(
        responding_to_ticket=ticket_id,
        responding_to_user=user_id,
        ticket_number=ticket_number
    )
    
    await callback.message.answer(
        f"💬 <b>Ответ на заявку #{ticket_number}</b>\n\n"
        f"<b>Вопрос пользователя:</b>\n{issue[:300]}...\n\n"
        f"Отправьте ваш ответ (текст, фото, документ):\n\n"
        f"<i>Для отмены нажмите /cancel</i>"
    )
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=f"🔄 <b>Заявка #{ticket_number} взята в работу</b>\n"
                 f"Отвечает: {callback.from_user.first_name} (@{callback.from_user.username or 'нет'})"
        )
    except:
        pass
    
    await state.set_state(TicketStates.WAITING_FOR_RESPONSE_TO_USER)
    await callback.answer()

@dp.callback_query(F.data.startswith("close_"))
async def handle_close_button(callback: CallbackQuery):
    if not can_access_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав для этого действия.", show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[1])
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, ticket_number FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    
    if not ticket:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return
    
    user_id, ticket_number = ticket
    
    cursor.execute('UPDATE tickets SET status = "closed", response_time = ? WHERE id = ?', (datetime.now(), ticket_id))
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"""🎉 <b>Ваша заявка #{ticket_number} закрыта!</b>

Заявка была закрыта сотрудником поддержки.

🌟 <b>Оцените качество работы:</b>
1 — очень плохо
10 — очень хорошо

Также напишите маленький комментарий к вашей оценке. 
Спасибо что выбрали BotHost 😊"""
        )
    except:
        pass
    
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ <b>ЗАКРЫТО</b> пользователем {callback.from_user.first_name}"
        )
    except:
        pass
    
    await callback.answer(f"✅ Заявка #{ticket_number} закрыта.")

@dp.message(TicketStates.WAITING_FOR_RESPONSE_TO_USER, F.text)
async def send_response_to_user(message: Message, state: FSMContext):
    user_data = await state.get_data()
    ticket_id = user_data.get('responding_to_ticket')
    user_id = user_data.get('responding_to_user')
    ticket_number = user_data.get('ticket_number')
    
    if not all([ticket_id, user_id, ticket_number]):
        await message.answer("❌ Ошибка: данные ответа не найдены.")
        await state.clear()
        return
    
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO responses (ticket_id, admin_id, response_text, created_at)
        VALUES (?, ?, ?, ?)
    ''', (ticket_id, message.from_user.id, message.text, datetime.now()))
    
    cursor.execute('UPDATE tickets SET status = "in_progress" WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"""📨 <b>Ответ по заявке #{ticket_number}</b>

<b>Сообщение от поддержки:</b>
{message.text}

─────────────────────────────
<i>Для продолжения диалога просто ответьте на это сообщение.
Ваш ответ автоматически поступит в поддержку.</i>"""
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение пользователю: {e}")
        await state.clear()
        return
    
    await message.answer(
        f"✅ Ответ отправлен пользователю (заявка #{ticket_number})",
        reply_markup=get_admin_keyboard() if can_access_admin(message.from_user.id) else get_main_keyboard(message.from_user.id)
    )
    await state.clear()

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========
@dp.message(F.text == "📋 Мои заявки")
async def my_tickets(message: Message):
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ticket_number, category, priority, issue, status, created_at, admin_response 
        FROM tickets 
        WHERE user_id = ? 
        ORDER BY created_at DESC
        LIMIT 5
    ''', (message.from_user.id,))
    
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer(
            "📭 У вас нет активных заявок.\n"
            "Нажмите «🎫 Создать тикет» для обращения в поддержку.",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return
    
    response = "📋 <b>Ваши последние заявки:</b>\n\n"
    
    for ticket in tickets:
        ticket_number, category, priority, issue, status, created_at, admin_response = ticket
        
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
        
        response += f"""─────────────────────────────
<b>{ticket_number}</b>
{status_emoji} Статус: <b>{status}</b>
{category_emoji} Категория: <b>{category}</b>
{priority_emoji} Приоритет: <b>{priority}</b>
🕒 Создана: {created_at.split('.')[0] if '.' in created_at else created_at}

<b>Описание:</b>
{issue[:100]}..."""

        if admin_response:
            response += f"\n\n<b>Ответ поддержки:</b>\n{admin_response[:100]}..."
        
        response += "\n"
    
    response += "\n─────────────────────────────"
    
    await message.answer(response, reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    conn = sqlite3.connect('bothost_support.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE user_id = ?', (message.from_user.id,))
    user_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE user_id = ? AND status = "closed"', (message.from_user.id,))
    closed_tickets = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"""📊 <b>Ваша статистика</b>

🎫 Всего заявок: <b>{user_tickets}</b>
✅ Решено: <b>{closed_tickets}</b>
❌ В работе: <b>{user_tickets - closed_tickets}</b>

<b>Эффективность поддержки для вас:</b> {int((closed_tickets/user_tickets*100) if user_tickets > 0 else 0)}%""",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "❓ Частые вопросы")
async def show_faq(message: Message):
    faq_text = """❓ <b>Часто задаваемые вопросы</b>

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

<b>🏢 Офис:</b>
г. Москва, ул. Техническая, д. 1
Пн-Пт: 9:00-18:00

<b>📞 Телефон:</b>
+7 (495) 123-45-67

<b>✉️ Email:</b>
support@bothost.ru

<b>🌐 Сайт:</b>
www.bothost.ru

<b>📱 Наш канал:</b>
{PUBLIC_CHANNEL}

<b>🕒 Поддержка 24/7:</b>
В этом боте — круглосуточно!"""
    
    await message.answer(contacts_text, reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "« Назад в меню")
async def back_to_menu(message: Message):
    await cmd_start(message)

@dp.message(F.text.in_(["« Назад к категориям", "❌ Отменить создание"]))
async def cancel_creation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Создание заявки отменено.\nВозвращаю в главное меню.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Действие отменено.\nВозвращаю в главное меню.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message()
async def handle_other_messages(message: Message):
    await message.answer(
        "🤔 Неизвестная команда.\nИспользуйте кнопки меню ниже.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ========== ЗАПУСК БОТА ==========
async def main():
    # Инициализация базы данных
    init_db()
    
    print("🤖 Бот техподдержки BotHost запущен (aiogram 3)!")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print(f"📢 Канал для заявок: {SUPPORT_CHAT_ID}")
    print(f"📱 Публичный канал: {PUBLIC_CHANNEL}")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())