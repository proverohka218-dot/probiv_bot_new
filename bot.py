import asyncio
import re
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, BufferedInputFile

from config import BOT_TOKEN, PRICE_STARS, DB_PATH
from database import (
    init_db,
    is_subscription_active,
    activate_subscription,
    get_subscription_info,
    generate_promo_code,
    add_promo_code,
    get_promo_duration,
    search_db,
    log_search,
    get_cache_key,
    get_cached_result,
    save_to_cache,
)
from rate_limiter import rate_limiter
from mega_osint import MegaOSINT

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_last_query = {}

# ===== КЛАВИАТУРА =====
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Пробить", callback_data="search")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🎟️ Активировать промокод", callback_data="promo")],
            [InlineKeyboardButton(text="👤 Моя подписка", callback_data="my_subscription")]
        ]
    )

# ===== ПРОВЕРКА БЕСПЛАТНЫХ ЗАПРОСОВ =====
def get_free_queries(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute('SELECT free_queries FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return 2  # 2 бесплатных запроса по умолчанию

def decrement_free_queries(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT INTO users (user_id, free_queries) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET free_queries = free_queries - 1
    ''', (user_id, 2))
    conn.commit()
    conn.close()

def init_free_queries_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            free_queries INTEGER DEFAULT 2
        )
    ''')
    conn.commit()
    conn.close()

# ===== ГЕНЕРАЦИЯ HTML-ОТЧЁТА =====
def generate_html_report(query: str, db_results: list, osint_result: dict) -> str:
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Отчёт по запросу: {query}</title>
<style>body{{font-family:Arial,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:20px;}}
.container{{max-width:800px;margin:auto;background:#1a1a1a;padding:30px;border-radius:12px;border:1px solid #333;}}
h1{{color:#00ff88;border-bottom:2px solid #00ff88;padding-bottom:10px;}}
.section{{margin:20px 0;padding:15px;background:#222;border-radius:8px;border-left:4px solid #00ff88;}}
table{{width:100%;border-collapse:collapse;}}
th,td{{padding:10px;text-align:left;border-bottom:1px solid #333;}}
th{{background:#2a2a2a;color:#00ff88;}}
.footer{{margin-top:30px;font-size:12px;color:#666;text-align:center;}}
</style></head>
<body>
<div class="container">
<h1>🔍 ОТЧЁТ ПО ЗАПРОСУ</h1>
<div style="font-size:18px;">📌 {query}</div>
<div style="color:#888;">🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
"""
    if db_results:
        html += f'<div class="section"><h2>📊 БАЗА ДАННЫХ (найдено: {len(db_results)})</h2><table><tr><th>#</th><th>ФИО</th><th>Телефон</th><th>Email</th><th>Адрес</th></tr>'
        for i, row in enumerate(db_results[:10], 1):
            html += f'<tr><td>{i}</td><td>{row.get("full_name", "—")}</td><td>{row.get("phone", "—")}</td><td>{row.get("email", "—")}</td><td>{row.get("address", "—")}</td></tr>'
        html += '</table></div>'
    else:
        html += '<div class="section"><p>❌ В базе ничего не найдено</p></div>'

    osint_data = osint_result.get('result', {})
    if osint_data:
        html += '<div class="section"><h2>📡 OSINT</h2>'
        tg = osint_data.get('telegram_phone', {}) or osint_data.get('telegram_username', {})
        if tg.get('exists'):
            html += f'<p>📱 Telegram: ✅ @{tg.get("username", "—")}</p>'
        tc = osint_data.get('truecaller', {})
        if tc.get('name') and tc['name'] != '—':
            html += f'<p>📞 Truecaller: {tc["name"]} ({tc.get("country", "—")})</p>'
        hibp = osint_data.get('hibp', {})
        if hibp.get('count', 0) > 0:
            html += f'<p>✉️ Утечек: {hibp["count"]}</p>'
        sherlock = osint_data.get('sherlock', [])
        if sherlock and sherlock != ['Не найдено']:
            html += f'<p>🔎 Sherlock: {", ".join(sherlock[:5])}</p>'
        html += '</div>'

    html += '<div class="footer">📌 Отчёт сгенерирован PROBIV+OSINT v7.0 (ROCKET)</div></div></body></html>'
    return html

# ===== OSINT-ПОИСК =====
async def osint_search(query: str) -> dict:
    query = query.strip()
    if re.match(r'^\+?\d{10,15}$', query) or re.match(r'^8\d{10}$', query):
        qtype = 'phone'
    elif re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', query):
        qtype = 'email'
    elif re.match(r'^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$', query):
        qtype = 'fio'
    elif query.startswith('@') or len(query) > 3:
        qtype = 'username'
    elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', query):
        qtype = 'ip'
    else:
        qtype = 'unknown'

    cache_key = get_cache_key(query, qtype)
    cached = get_cached_result(cache_key)
    if cached:
        return cached

    result = {'type': qtype, 'query': query, 'result': {}}
    async with MegaOSINT() as osint:
        if qtype == 'phone':
            extra = await osint.full_search(phone=query)
        elif qtype == 'email':
            extra = await osint.full_search(email=query)
        elif qtype == 'fio':
            extra = await osint.full_search(fio=query)
        elif qtype == 'username':
            username = query[1:] if query.startswith('@') else query
            extra = await osint.full_search(username=username)
        elif qtype == 'ip':
            extra = await osint.full_search(ip=query)
        else:
            extra = {}
        result['result'] = extra

    save_to_cache(cache_key, qtype, query, result)
    return result

# ===== ОБРАБОТЧИКИ =====

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        f"🔍 **PROBIV+OSINT v7.0 (ROCKET)**\n\n"
        "Я ищу информацию по:\n"
        "• 📞 Номеру телефона → Truecaller + Numverify + Telegram + Dehashed\n"
        "• ✉️ Email → Hunter + Dehashed + HIBP\n"
        "• 👤 ФИО → VK\n"
        "• 🔗 Ник → Sherlock (300+ платформ) + Telegram\n"
        "• 🌐 IP → IP2Location + AbuseIPDB\n\n"
        f"💰 **Подписка — {PRICE_STARS} Stars за 30 дней**\n"
        "🎟️ Промокоды — введите код для активации\n\n"
        "🎁 **У тебя есть 2 БЕСПЛАТНЫХ запроса** (без подписки)\n\n"
        "📄 Результат придёт в виде текста и HTML-файла",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@dp.message(Command("addpromo"))
async def add_promo_command(message: types.Message):
    if str(message.from_user.id) != "1689645974":
        await message.answer("❌ У вас нет прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: `/addpromo 30`", parse_mode="Markdown")
        return
    try:
        days = int(args[1])
        code = generate_promo_code()
        add_promo_code(code, days, message.from_user.id)
        await message.answer(f"✅ **Промокод создан!**\n\n🎟️ Код: `{code}`\n📅 Дней: {days}", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Введите число дней.")

@dp.message()
async def handle_text(message: types.Message):
    if not message.text or message.text.startswith('/'):
        return
    text = message.text.strip().upper()
    if len(text) == 8 and text.isalnum():
        duration = get_promo_duration(text)
        if duration > 0:
            activate_subscription(message.from_user.id, days=duration, promo_code=text)
            await message.answer(f"✅ **Промокод активирован!**\n\nПодписка на {duration} дней оформлена.", parse_mode="Markdown", reply_markup=main_menu())
            return
    if not is_subscription_active(message.from_user.id):
        await message.answer(
            f"🔒 **Доступ ограничен**\n\n"
            f"Купите подписку за {PRICE_STARS} Stars или активируйте промокод.\n"
            f"🎁 Или используйте **2 бесплатных запроса** — просто нажмите «Пробить»",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        return
    user_last_query[message.from_user.id] = message.text.strip()
    await message.answer(f"✅ Сохранено: `{message.text}`\nНажми **«Пробить»**", parse_mode="Markdown", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "search")
async def search_callback(callback: types.CallbackQuery):
    await callback.answer("⏳ Поиск...")
    if not rate_limiter.is_allowed(callback.from_user.id):
        wait = rate_limiter.get_wait_time(callback.from_user.id)
        await callback.message.answer(f"⏳ **Лимит запросов:** 5 в минуту.\nПодожди **{wait} секунд**.", parse_mode="Markdown")
        return
    
    # Проверка: есть ли подписка ИЛИ остались бесплатные запросы
    if not is_subscription_active(callback.from_user.id):
        free_q = get_free_queries(callback.from_user.id)
        if free_q <= 0:
            await callback.message.answer(
                f"🔒 **У вас нет подписки и закончились бесплатные запросы**\n\n"
                f"Купите подписку за {PRICE_STARS} Stars или активируйте промокод.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            return
        # Списываем бесплатный запрос
        decrement_free_queries(callback.from_user.id)
        await callback.message.answer(f"🎁 **Бесплатный запрос #{2 - get_free_queries(callback.from_user.id)} из 2**")
    
    query = user_last_query.get(callback.from_user.id)
    if not query:
        await callback.message.answer("❌ Сначала отправь данные.")
        return
    msg = await callback.message.answer("⏳ Ищу в базе и открытых источниках...")
    db_results = search_db(query)
    osint_result = await osint_search(query)
    log_search(callback.from_user.id, query, len(db_results))
    response_text = f"🔍 **Результаты по запросу:** `{query}`\n\n"
    if db_results:
        response_text += f"📊 Найдено в БД: {len(db_results)} записей\n"
        for row in db_results[:3]:
            response_text += f"👤 {row.get('full_name', '—')} | 📞 {row.get('phone', '—')} | ✉️ {row.get('email', '—')}\n"
    else:
        response_text += "❌ В базе ничего не найдено.\n"
    osint_data = osint_result.get('result', {})
    if osint_data:
        response_text += "\n📡 OSINT:\n"
        tg = osint_data.get('telegram_phone', {}) or osint_data.get('telegram_username', {})
        if tg.get('exists'):
            response_text += f"   • Telegram: ✅ @{tg.get('username', '—')}\n"
        tc = osint_data.get('truecaller', {})
        if tc.get('name') and tc['name'] != '—':
            response_text += f"   • Truecaller: {tc['name']} ({tc.get('country', '—')})\n"
        hibp = osint_data.get('hibp', {})
        if hibp.get('count', 0) > 0:
            response_text += f"   • Утечек: {hibp['count']}\n"
        sherlock = osint_data.get('sherlock', [])
        if sherlock and sherlock != ['Не найдено']:
            response_text += f"   • Sherlock: {', '.join(sherlock[:5])}\n"
    html_content = generate_html_report(query, db_results, osint_result)
    await callback.message.answer(response_text, parse_mode="Markdown")
    await callback.message.answer_document(BufferedInputFile(html_content.encode(), filename=f"report_{query[:20]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"), caption="📄 Полный отчёт в HTML")
    await msg.delete()

# ===== СТАТИСТИКА =====
@dp.callback_query(lambda c: c.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    await callback.answer("⏳ Загрузка статистики...")
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute('SELECT COUNT(*) FROM people').fetchone()[0]
        history_count = conn.execute('SELECT COUNT(*) FROM search_history').fetchone()[0]
        conn.close()
        await callback.message.answer(
            f"📊 **Статистика**\n\n"
            f"👤 Записей в БД: {count}\n"
            f"🔍 Всего запросов: {history_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

# ===== МОЯ ПОДПИСКА =====
@dp.callback_query(lambda c: c.data == "my_subscription")
async def my_subscription(callback: types.CallbackQuery):
    await callback.answer("⏳ Проверяю подписку...")
    try:
        info = get_subscription_info(callback.from_user.id)
        free_q = get_free_queries(callback.from_user.id)
        if info['active']:
            await callback.message.answer(
                f"👤 **Ваша подписка активна**\n\n"
                f"⏳ Осталось дней: **{info['days_left']}**\n"
                f"🎁 Бесплатных запросов осталось: **{free_q}**",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer(
                f"🔒 **У вас нет активной подписки**\n\n"
                f"🎁 Бесплатных запросов осталось: **{free_q}**\n"
                f"💎 Купите подписку за {PRICE_STARS} Stars",
                parse_mode="Markdown"
            )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

# ===== ПОКУПКА ПОДПИСКИ =====
@dp.callback_query(lambda c: c.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    await callback.answer()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="💎 PROBIV+OSINT Premium",
        description=f"Доступ на 30 дней ({PRICE_STARS} Stars)",
        payload="subscription_30_days",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Подписка на 30 дней", amount=PRICE_STARS)],
        photo_url="https://img.icons8.com/color/96/000000/security-checked--v1.png",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )

@dp.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(lambda message: message.successful_payment)
async def successful_payment(message: types.Message):
    activate_subscription(message.from_user.id, days=30)
    await message.answer("✅ **Подписка активирована!**", parse_mode="Markdown", reply_markup=main_menu())

# ===== ПРОМОКОД =====
@dp.callback_query(lambda c: c.data == "promo")
async def promo_prompt(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("🎟️ **Введите промокод** (8 символов)", parse_mode="Markdown")

# ===== ЗАПУСК =====
async def main():
    init_db()
    init_free_queries_table()
    print("✅ Бот PROBIV+OSINT v7.0 (SQLite) запущен!")
    print(f"💰 Цена подписки: {PRICE_STARS} Stars за 30 дней")
    print("🎁 У каждого пользователя 2 бесплатных запроса")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())