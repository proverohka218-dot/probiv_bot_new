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
from mega_osint import MegaOSINT

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

def generate_html_report(query: str, db_results: list, osint_result: dict) -> str:
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчёт по запросу: {query}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 30px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: #1a1a1a;
            padding: 30px;
            border-radius: 16px;
            border: 1px solid #333;
            box-shadow: 0 8px 24px rgba(0,0,0,0.8);
        }}
        h1 {{
            color: #00ff88;
            border-bottom: 3px solid #00ff88;
            padding-bottom: 15px;
            font-size: 28px;
            margin-bottom: 20px;
        }}
        .query-box {{
            background: #2a2a2a;
            padding: 15px;
            border-radius: 10px;
            font-family: monospace;
            font-size: 18px;
            margin: 20px 0;
            border-left: 4px solid #00ff88;
        }}
        .timestamp {{
            color: #888;
            font-size: 14px;
            margin-bottom: 25px;
        }}
        .section {{
            margin: 25px 0;
            padding: 20px;
            background: #222;
            border-radius: 12px;
            border-left: 5px solid #00ff88;
        }}
        .section h2 {{
            margin-top: 0;
            color: #00ff88;
            font-size: 20px;
            margin-bottom: 15px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}
        th {{
            background: #2a2a2a;
            color: #00ff88;
            font-weight: bold;
        }}
        td {{
            color: #ccc;
        }}
        .empty {{
            color: #888;
            font-style: italic;
        }}
        .vk-link {{
            display: inline-block;
            margin-top: 10px;
            padding: 8px 16px;
            background: #2a6b8f;
            color: #fff;
            border-radius: 8px;
            text-decoration: none;
            font-weight: bold;
            transition: 0.3s;
        }}
        .vk-link:hover {{
            background: #1e4f6b;
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #333;
            font-size: 12px;
            color: #555;
            text-align: center;
        }}
        .footer span {{
            color: #00ff88;
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>🔍 ОТЧЁТ ПО ЗАПРОСУ</h1>
    <div class="query-box">📌 {query}</div>
    <div class="timestamp">🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>

    <div class="section">
        <h2>📊 БАЗА ДАННЫХ</h2>
        <table>
            <tr><th>#</th><th>ФИО</th><th>Телефон</th><th>Email</th><th>Адрес</th><th>VK</th></tr>
"""

    if db_results:
        for i, row in enumerate(db_results[:20], 1):
            vk_link = ""
            if row.get('social_vk'):
                vk_link = f'<a href="https://vk.com/{row["social_vk"]}" target="_blank" style="color:#00ff88;">{row["social_vk"]}</a>'
            elif row.get('domain'):
                vk_link = f'<a href="https://vk.com/{row["domain"]}" target="_blank" style="color:#00ff88;">{row["domain"]}</a>'
            else:
                vk_link = "—"

            html += f"""
            <tr>
                <td>{i}</td>
                <td>{row.get('full_name', '—')}</td>
                <td>{row.get('phone', '—')}</td>
                <td>{row.get('email', '—')}</td>
                <td>{row.get('address', '—')}</td>
                <td>{vk_link}</td>
            </tr>
            """
    else:
        html += '<tr><td colspan="6" class="empty">❌ Ничего не найдено</td></tr>'

    html += """
        </table>
    </div>
    """

    osint_data = osint_result.get('result', {}) if isinstance(osint_result, dict) else {}
    if osint_data:
        html += '<div class="section"><h2>📡 OSINT (MegaOSINT)</h2>'
        if 'telegram' in osint_data and osint_data['telegram'].get('exists'):
            html += f'<div class="osint-item">📱 Telegram: ✅ <b>@{osint_data["telegram"].get("username", "—")}</b></div>'
        if 'truecaller' in osint_data and osint_data['truecaller'].get('name', '—') != '—':
            html += f'<div class="osint-item">📞 Truecaller: <b>{osint_data["truecaller"]["name"]}</b> ({osint_data["truecaller"].get("country", "—")})</div>'
        if 'sherlock' in osint_data and osint_data['sherlock'] and osint_data['sherlock'] != ['Не найдено']:
            html += '<div class="osint-item">🔎 Sherlock: <b>' + ', '.join(osint_data['sherlock'][:5]) + '</b></div>'
        if 'numverify' in osint_data and osint_data['numverify'].get('valid'):
            html += f'<div class="osint-item">📞 Numverify: {osint_data["numverify"].get("country", "—")}, {osint_data["numverify"].get("location", "—")}</div>'
        html += '</div>'
    else:
        html += '<div class="section"><h2>📡 OSINT</h2><p class="empty">❌ Данные не найдены</p></div>'

    if db_results:
        for row in db_results[:1]:
            if row.get('social_vk'):
                html += f'<div style="text-align:center;margin:20px 0;"><a href="https://vk.com/{row["social_vk"]}" target="_blank" class="vk-link">🔗 Открыть профиль VK</a></div>'
            elif row.get('domain'):
                html += f'<div style="text-align:center;margin:20px 0;"><a href="https://vk.com/{row["domain"]}" target="_blank" class="vk-link">🔗 Открыть профиль VK</a></div>'

    html += """
    <div class="footer">
        📌 Отчёт сгенерирован <span>PROBIV+OSINT v7.0 (TORIK)</span>
    </div>
</div>
</body>
</html>
"""
    return html

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
    cached = await get_cached_result(cache_key)
    if cached and isinstance(cached, dict) and 'result' in cached:
        return cached

    result = {'type': qtype, 'query': query, 'result': {}}
    try:
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
        result['result'] = extra if isinstance(extra, dict) else {}
    except Exception as e:
        result['result'] = {'error': str(e)}

    await save_to_cache(cache_key, qtype, query, result)
    return result

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        f"🔍 **PROBIV+OSINT v7.0 (TORIK)**\n\n"
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

    osint_data = osint_result.get('result', {}) if isinstance(osint_result, dict) else {}
    if osint_data:
        response_text += "\n📡 OSINT:\n"
        if 'telegram' in osint_data and osint_data['telegram'].get('exists'):
            response_text += f"   • Telegram: ✅ @{osint_data['telegram'].get('username', '—')}\n"
        if 'truecaller' in osint_data and osint_data['truecaller'].get('name', '—') != '—':
            response_text += f"   • Truecaller: {osint_data['truecaller']['name']} ({osint_data['truecaller'].get('country', '—')})\n"
        if 'sherlock' in osint_data and osint_data['sherlock'] and osint_data['sherlock'] != ['Не найдено']:
            response_text += f"   • Sherlock: {', '.join(osint_data['sherlock'][:5])}\n"

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
    print("✅ Бот PROBIV+OSINT v7.0 (TORIK) запущен!")
    print(f"💰 Цена подписки: {PRICE_STARS} Stars за 30 дней")
    print("🎁 У каждого пользователя 2 бесплатных запроса")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())