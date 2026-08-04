#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import re
import asyncio
import asyncpg
from config import DATABASE_URL

INPUT_FOLDER = "databases"

# ===== НОРМАЛИЗАЦИЯ ТЕЛЕФОНА =====
def normalize_phone(phone):
    if not phone:
        return None
    phone = re.sub(r'[\s\(\)\-+]', '', str(phone))
    if phone.startswith('8') and len(phone) == 11:
        return '+7' + phone[1:]
    elif phone.startswith('7') and len(phone) == 11:
        return '+' + phone
    elif phone.startswith('+'):
        return phone
    else:
        return None

# ===== ИМПОРТ CSV В POSTGRESQL =====
async def import_csv_to_tigerdata(csv_path: str, conn):
    print(f"📥 Импортирую: {os.path.basename(csv_path)}")

    try:
        # Определяем разделитель
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            if '|' in first_line:
                delim = '|'
            elif ';' in first_line:
                delim = ';'
            elif ',' in first_line:
                delim = ','
            else:
                delim = ';'

        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=delim)
            if not reader.fieldnames:
                print(f"⚠️ Нет заголовков в {os.path.basename(csv_path)}")
                return 0

            cols = reader.fieldnames

            # Ищем колонки
            name_col = None
            phone_col = None
            email_col = None
            passport_col = None
            birth_date_col = None
            address_col = None

            for i, col in enumerate(cols):
                col_lower = col.lower().strip()
                if any(k in col_lower for k in ['фио', 'name', 'имя', 'фамилия']):
                    name_col = i
                if any(k in col_lower for k in ['телефон', 'phone', 'mobile', 'мобильный', 'номер']):
                    phone_col = i
                if any(k in col_lower for k in ['email', 'почта', 'mail']):
                    email_col = i
                if any(k in col_lower for k in ['паспорт', 'passport', 'серия']):
                    passport_col = i
                if any(k in col_lower for k in ['дата рождения', 'birth', 'день рождения']):
                    birth_date_col = i
                if any(k in col_lower for k in ['адрес', 'address', 'место']):
                    address_col = i

            # Если не нашли колонки — используем первую и вторую
            if name_col is None and phone_col is None:
                if len(cols) >= 2:
                    name_col = 0
                    phone_col = 1
                else:
                    print(f"⚠️ Недостаточно колонок в {os.path.basename(csv_path)}")
                    return 0

            count = 0
            for row in reader:
                parts = [row.get(col, '') for col in cols]

                name = parts[name_col].strip() if name_col is not None else ''
                phone_raw = parts[phone_col].strip() if phone_col is not None else ''
                phone = normalize_phone(phone_raw)
                email = parts[email_col].strip() if email_col is not None else ''
                passport = parts[passport_col].strip() if passport_col is not None else ''
                birth_date = parts[birth_date_col].strip() if birth_date_col is not None else ''
                address = parts[address_col].strip() if address_col is not None else ''

                if not name and not phone:
                    continue

                await conn.execute('''
                    INSERT INTO people (phone, email, full_name, address, passport, birth_date)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                ''', phone, email, name, address, passport, birth_date)

                count += 1

            print(f"   ✅ Импортировано {count} записей")
            return count

    except Exception as e:
        print(f"❌ Ошибка импорта {os.path.basename(csv_path)}: {e}")
        return 0

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
async def main():
    print("🔥 ИМПОРТ В TIGERDATA (PostgreSQL)")
    print("═" * 50)

    # Создаём папку, если её нет
    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"📁 Папка '{INPUT_FOLDER}' создана. Положите туда CSV-файлы.")
        return

    # Собираем все CSV-файлы
    csv_files = []
    for root, dirs, files in os.walk(INPUT_FOLDER):
        for f in files:
            if f.endswith('.csv'):
                csv_files.append(os.path.join(root, f))

    if not csv_files:
        print("❌ В папке 'databases' нет CSV-файлов.")
        return

    print(f"📂 Найдено CSV-файлов: {len(csv_files)}")

    # Подключаемся к TigerData
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Подключение к TigerData установлено")
    except Exception as e:
        print(f"❌ Ошибка подключения к TigerData: {e}")
        return

    total = 0
    async with pool.acquire() as conn:
        for csv_path in csv_files:
            count = await import_csv_to_tigerdata(csv_path, conn)
            total += count

    await pool.close()
    print(f"\n✅ Импортировано ВСЕГО: {total} записей в TigerData")

if __name__ == "__main__":
    asyncio.run(main())