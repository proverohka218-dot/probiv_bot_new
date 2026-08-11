import asyncio
import re
import os
import subprocess
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
    avatar_url = "https://ui-avatars.com/api/?name=OSINT&background=0D8ABC&color=fff&size=128"
    if osint_result and isinstance(osint_result, dict):
        osint_data = osint_result.get('result', {})
        if osint_data.get('truecaller') and osint_data['truecaller'].get('avatar'):
            avatar_url = osint_data['truecaller']['avatar']
        elif osint_data.get('vk') and osint_data['vk'] and osint_data['vk'][0].get('photo_200'):
            avatar_url = osint_data['vk'][0]['photo_200']

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT Report: {query}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: #0f0f1a;
            color: #e2e8f0;
            padding: 24px;
        }}
        .container {{
            max-width: 820px;
            margin: 0 auto;
            background: #1a1a2e;
            border-radius: 24px;
            padding: 24px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.8);
            border: 1px solid #2d2d44;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #2d2d44;
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        .header-left {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .badge {{
            background: #00ff88;
            color: #0f0f1a;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 20px;
            text-transform: uppercase;
        }}
        .query-title {{
            font-size: 22px;
            font-weight: 600;
            background: #2d2d44;
            padding: 4px 12px;
            border-radius: 8px;
            color: #00ff88;
        }}
        .profile-card {{
            display: flex;
            align-items: center;
            gap: 20px;
            background: #16162b;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #2d2d44;
        }}
        .avatar {{
            width: 72px;
            height: 72px;
            border-radius: 50%;
            background: #2d2d44;
            object-fit: cover;
            border: 2px solid #00ff88;
        }}
        .profile-info h2 {{
            font-size: 24px;
            font-weight: 700;
        }}
        .profile-info .phone {{
            color: #00ff88;
            font-size: 18px;
            font-weight: 500;
        }}
        .profile-info .meta {{
            color: #94a3b8;
            font-size: 14px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #16162b;
            border-radius: 12px;
            padding: 14px;
            text-align: center;
            border: 1px solid #2d2d44;
        }}
        .stat-card .label {{
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-card .value {{
            font-size: 20px;
            font-weight: 700;
            color: #00ff88;
        }}
        .result-list {{
            background: #16162b;
            border-radius: 16px;
            padding: 16px;
            border: 1px solid #2d2d44;
            margin-bottom: 20px;
        }}
        .result-item {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #252540;
        }}
        .result-item:last-child {{ border-bottom: none; }}
        .result-name {{ font-weight: 600; }}
        .result-phone {{ color: #00ff88; }}
        .osint-block {{
            background: #16162b;
            border-radius: 16px;
            padding: 16px;
            border: 1px solid #2d2d44;
            margin-top: 16px;
        }}
        .osint-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px solid #252540;
        }}
        .osint-item:last-child {{ border-bottom: none; }}
        .osint-icon {{
            width: 28px;
            text-align: center;
            font-size: 20px;
        }}
        .osint-label {{ color: #94a3b8; font-size: 14px; }}
        .osint-value {{ font-weight: 600; }}
        .osint-value.found {{ color: #00ff88; }}
        .osint-value.not-found {{ color: #f87171; }}
        .footer {{
            text-align: center;
            color: #4a4a6a;
            font-size: 13px;
            margin-top: 24px;
            border-top: 1px solid #2d2d44;
            padding-top: 16px;
        }}
        @media (max-width: 600px) {{
            .profile-card {{ flex-direction: column; text-align: center; }}
            .stats-grid {{ grid-template-columns: 1fr 1fr; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="header-left">
            <span class="badge">🔍 OSINT</span>
            <span class="query-title">{query}</span>
        </div>
        <span style="font-size:12px;color:#4a4a6a;">{datetime.now().strftime('%H:%M %d.%m.%Y')}</span>
    </div>

    <div class="profile-card">
        <img class="avatar" src="{avatar_url}" alt="avatar" onerror="this.src='https://ui-avatars.com/api/?name=OSINT&background=2d2d44&color=fff&size=128'">
        <div class="profile-info">
            <h2>{db_results[0].get('full_name', '—') if db_results else '—'}</h2>
            <div class="phone">📞 {db_results[0].get('phone', '—') if db_results else '—'}</div>
            <div class="meta">✉️ {db_results[0].get('email', '—') if db_results else '—'}</div>
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Найдено в БД</div>
            <div class="value">{len(db_results)}</div>
        </div>
        <div class="stat-card">
            <div class="label">OSINT-источников</div>
            <div class="value">{len(osint_result.get('result', {})) if osint_result else 0}</div>
        </div>
        <div class="stat-card">
            <div class="label">Время</div>
            <div class="value">⏱️ ~1.2с</div>
        </div>
    </div>

    <div class="result-list">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px;color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:0.5px;">
            <span>Имя</span>
            <span>Телефон</span>
        </div>
"""

    if db_results:
        for row in db_results[:10]:
            vk_link = "—"
            if row.get('domain'):
                vk_link = f'<a href="https://vk.com/{row["domain"]}" target="_blank" style="color:#00ff88;text-decoration:none;">{row["domain"]}</a>'
            elif row.get('social_vk'):
                if str(row['social_vk']).isdigit():
                    vk_link = f'<a href="https://vk.com/id{row["social_vk"]}" target="_blank" style="color:#00ff88;text-decoration:none;">id{row["social_vk"]}</a>'
                else:
                    vk_link = f'<a href="https://vk.com/{row["social_vk"]}" target="_blank" style="color:#00ff88;text-decoration:none;">{row["social_vk"]}</a>'

            html += f"""
        <div class="result-item">
            <span class="result-name">{row.get('full_name', '—')} {vk_link}</span>
            <span class="result-phone">{row.get('phone', '—')}</span>
        </div>
            """
    else:
        html += '<div style="color:#f87171;padding:20px;text-align:center;">❌ Ничего не найдено в базе</div>'

    html += """
    </div>

    <div class="osint-block">
        <div style="color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">📡 OSINT</div>
"""

    osint_data = osint_result.get('result', {}) if isinstance(osint_result, dict) else {}
    if osint_data:
        if osint_data.get('telegram') and osint_data['telegram'].get('exists'):
            html += f"""
        <div class="osint-item">
            <span class="osint-icon">📱</span>
            <span class="osint-label">Telegram</span>
            <span class="osint-value found">@{osint_data['telegram']['username']}</span>
        </div>
            """
        if osint_data.get('truecaller') and osint_data['truecaller'].get('name', '—') != '—':
            html += f"""
        <div class="osint-item">
            <span class="osint-icon">📞</span>
            <span class="osint-label">Truecaller</span>
            <span class="osint-value found">{osint_data['truecaller']['name']}</span>
        </div>
            """
        if osint_data.get('sherlock') and osint_data['sherlock'] and osint_data['sherlock'] != ['Не найдено']:
            platforms = ', '.join(osint_data['sherlock'][:6])
            html += f"""
        <div class="osint-item">
            <span class="osint-icon">🔎</span>
            <span class="osint-label">Sherlock</span>
            <span class="osint-value found">{platforms}</span>
        </div>
            """
        if osint_data.get('vk') and osint_data['vk']:
            html += f"""
        <div class="osint-item">
            <span class="osint-icon">📸</span>
            <span class="osint-label">VK</span>
            <span class="osint-value found">Найдено {len(osint_data['vk'])} профилей</span>
        </div>
            """
    else:
        html += '<div style="color:#94a3b8;padding:8px 0;">❌ OSINT-данные не найдены</div>'

    html += """
    </div>

    <div class="footer">
        PROBIV+OSINT v7.0 · TORIK
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

@dp.message(lambda message: message.document)
async def handle_uploaded_file(message: types.Message):
    file_name = message.document.file_name
    if not (file_name.endswith('.csv') or file_name.endswith('.rar') or file_name.endswith('.7z') or file_name.endswith('.zip')):
        await message.answer("❌ Поддерживаются только CSV, RAR, 7Z, ZIP")
        return

    await message.answer(f"⏳ Скачиваю файл {file_name}...")
    file = await bot.get_file(message.document.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    os.makedirs("databases", exist_ok=True)
    file_path = f"databases/{file_name}"
    with open(file_path, "wb") as f:
        f.write(downloaded_file.read())

    await message.answer(f"✅ Файл {file_name} загружен в databases/")

    if file_name.endswith('.csv'):
        await message.answer("⏳ Импортирую данные...")
        result = subprocess.run(["python3", "importer.py"], capture_output=True, text=True)
        await message.answer(f"📊 Импорт завершён:\n{result.stdout[-1000:]}")

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
            vk_link = ""
            if row.get('domain'):
                vk_link = f" vk.com/{row['domain']}"
            elif row.get('social_vk'):
                vk_link = f" vk.com/{row['social_vk']}"
            response_text += f"👤 {row.get('full_name', '—')} {vk_link} | 📞 {row.get('phone', '—')} | ✉️ {row.get('email', '—')}\n"
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

@dp.message(lambda message: message.document is not None)
async def handle_uploaded_file(message: types.Message):
    file_name = message.document.file_name
    await message.answer(f"📥 Получен файл: {file_name}")

    if not (file_name.endswith('.csv') or file_name.endswith('.rar') or file_name.endswith('.7z') or file_name.endswith('.zip')):
        await message.answer("❌ Поддерживаются только CSV, RAR, 7Z, ZIP")
        return

    await message.answer("⏳ Скачиваю файл...")
    file = await bot.get_file(message.document.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    os.makedirs("databases", exist_ok=True)
    file_path = f"databases/{file_name}"
    with open(file_path, "wb") as f:
        f.write(downloaded_file.read())

    await message.answer(f"✅ Файл {file_name} сохранён в databases/")

    if file_name.endswith('.csv'):
        await message.answer("⏳ Импортирую данные...")
        result = subprocess.run(["python3", "importer.py"], capture_output=True, text=True)
        await message.answer(f"📊 Импорт завершён:\n{result.stdout[-1000:]}")

async def main():
    await init_db()
    print("✅ Бот PROBIV+OSINT v7.0 (TORIK) запущен!")
    print(f"💰 Цена подписки: {PRICE_STARS} Stars за 30 дней")
    print("🎁 У каждого пользователя 2 бесплатных запроса")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())