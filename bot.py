import asyncio
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, BufferedInputFile

from config import BOT_TOKEN, PRICE_STARS
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
    get_free_queries,
    decrement_free_queries,
)
from rate_limiter import rate_limiter
from osint_agent import run_osint

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_last_query = {}

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

def generate_html_report(query: str, db_results: list, osint_result: str) -> str:
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

    if osint_result:
        html += '<div class="section"><h2>📡 OSINT (OpenOSINT)</h2>'
        html += f'<pre>{osint_result}</pre>'
        html += '</div>'

    html += '<div class="footer">📌 Отчёт сгенерирован PROBIV+OSINT v7.0 (ROCKET)</div></div></body></html>'
    return html

async def osint_search(query: str) -> str:
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
    cached = await get_cached_result(cache_key)
    if cached:
        return cached if isinstance(cached, str) else cached.get('result', '')

    raw_result = await run_osint(query)
    result = {'type': qtype, 'query': query, 'result': raw_result}
    await save_to_cache(cache_key, qtype, query, result)
    return raw_result

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        f"🔍 **PROBIV+OSINT v7.0 (OpenOSINT)**\n\n"
        "Я ищу информацию по:\n"
        "• 📞 Номеру телефона\n"
        "• ✉️ Email\n"
        "• 👤 ФИО\n"
        "• 🔗 Никнейм\n"
        "• 🌐 IP-адрес\n\n"
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
        await add_promo_code(code, days, message.from_user.id)
        await message.answer(f"✅ **Промокод создан!**\n\n🎟️ Код: `{code}`\n📅 Дней: {days}", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Введите число дней.")

@dp.message()
async def handle_text(message: types.Message):
    if not message.text or message.text.startswith('/'):
        return
    text = message.text.strip().upper()
    if len(text) == 8 and text.isalnum():
        duration = await get_promo_duration(text)
        if duration > 0:
            await activate_subscription(message.from_user.id, days=duration, promo_code=text)
            await message.answer(f"✅ **Промокод активирован!**\n\nПодписка на {duration} дней оформлена.", parse_mode="Markdown", reply_markup=main_menu())
            return
    if not await is_subscription_active(message.from_user.id):
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

    if not await is_subscription_active(callback.from_user.id):
        free_q = await get_free_queries(callback.from_user.id)
        if free_q <= 0:
            await callback.message.answer(
                f"🔒 **У вас нет подписки и закончились бесплатные запросы**\n\n"
                f"Купите подписку за {PRICE_STARS} Stars или активируйте промокод.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            return
        await decrement_free_queries(callback.from_user.id)
        await callback.message.answer(f"🎁 **Бесплатный запрос #{2 - await get_free_queries(callback.from_user.id)} из 2**")

    query = user_last_query.get(callback.from_user.id)
    if not query:
        await callback.message.answer("❌ Сначала отправь данные.")
        return
    msg = await callback.message.answer("⏳ Ищу в базе и открытых источниках...")
    db_results = await search_db(query)
    osint_result = await osint_search(query)
    await log_search(callback.from_user.id, query, len(db_results))

    response_text = f"🔍 **Результаты по запросу:** `{query}`\n\n"
    if db_results:
        response_text += f"📊 Найдено в БД: {len(db_results)} записей\n"
        for row in db_results[:3]:
            response_text += f"👤 {row.get('full_name', '—')} | 📞 {row.get('phone', '—')} | ✉️ {row.get('email', '—')}\n"
    else:
        response_text += "❌ В базе ничего не найдено.\n"

    if osint_result:
        response_text += f"\n📡 OSINT:\n{osint_result}"

    html_content = generate_html_report(query, db_results, osint_result)
    await callback.message.answer(response_text, parse_mode="Markdown")
    await callback.message.answer_document(BufferedInputFile(html_content.encode(), filename=f"report_{query[:20]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"), caption="📄 Полный отчёт в HTML")
    await msg.delete()

@dp.callback_query(lambda c: c.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    await callback.answer("⏳ Загрузка статистики...")
    try:
        import asyncpg
        from config import DATABASE_URL
        conn = await asyncpg.connect(DATABASE_URL)
        count = await conn.fetchval('SELECT COUNT(*) FROM people')
        history_count = await conn.fetchval('SELECT COUNT(*) FROM search_history')
        await conn.close()
        await callback.message.answer(
            f"📊 **Статистика**\n\n"
            f"👤 Записей в БД: {count}\n"
            f"🔍 Всего запросов: {history_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(lambda c: c.data == "my_subscription")
async def my_subscription(callback: types.CallbackQuery):
    await callback.answer("⏳ Проверяю подписку...")
    try:
        info = await get_subscription_info(callback.from_user.id)
        free_q = await get_free_queries(callback.from_user.id)
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
    await activate_subscription(message.from_user.id, days=30)
    await message.answer("✅ **Подписка активирована!**", parse_mode="Markdown", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "promo")
async def promo_prompt(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("🎟️ **Введите промокод** (8 символов)", parse_mode="Markdown")

async def main():
    await init_db()
    print("✅ Бот PROBIV+OSINT v7.0 (OpenOSINT) запущен!")
    print(f"💰 Цена подписки: {PRICE_STARS} Stars за 30 дней")
    print("🎁 У каждого пользователя 2 бесплатных запроса")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())