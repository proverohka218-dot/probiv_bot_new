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

# ===== УНИВЕРСАЛЬНЫЙ ПОИСК КОЛОНОК =====
def find_columns(headers):
    cols = {
        'first_name': None,
        'last_name': None,
        'phone': None,
        'email': None,
        'address': None,
        'passport': None,
        'birth_date': None,
        'social_vk': None,
        'social_tg': None,
        'social_ok': None
    }
    
    for i, col in enumerate(headers):
        col_lower = col.lower().strip()
        
        if any(k in col_lower for k in ['имя', 'first_name', 'first', 'name']):
            if cols['first_name'] is None:
                cols['first_name'] = i
        if any(k in col_lower for k in ['фамилия', 'last_name', 'last', 'surname']):
            if cols['last_name'] is None:
                cols['last_name'] = i
        if any(k in col_lower for k in ['фио', 'full_name', 'fio']):
            cols['first_name'] = i  # используем как полное имя
        if any(k in col_lower for k in ['телефон', 'phone', 'mobile', 'мобильный', 'номер']):
            if cols['phone'] is None:
                cols['phone'] = i
        if any(k in col_lower for k in ['email', 'почта', 'mail']):
            if cols['email'] is None:
                cols['email'] = i
        if any(k in col_lower for k in ['адрес', 'address']):
            if cols['address'] is None:
                cols['address'] = i
        if any(k in col_lower for k in ['паспорт', 'passport']):
            if cols['passport'] is None:
                cols['passport'] = i
        if any(k in col_lower for k in ['дата рождения', 'birth']):
            if cols['birth_date'] is None:
                cols['birth_date'] = i
        if any(k in col_lower for k in ['vk', 'vkontakte']):
            if cols['social_vk'] is None:
                cols['social_vk'] = i
        if any(k in col_lower for k in ['tg', 'telegram']):
            if cols['social_tg'] is None:
                cols['social_tg'] = i
        if any(k in col_lower for k in ['ok', 'odnoklassniki']):
            if cols['social_ok'] is None:
                cols['social_ok'] = i
    
    # Если не нашли отдельные колонки — ищем ФИО
    if cols['first_name'] is None and cols['last_name'] is None:
        for i, col in enumerate(headers):
            if any(k in col.lower() for k in ['фио', 'full_name', 'fio']):
                cols['first_name'] = i
                break
    
    return cols

# ===== ИМПОРТ CSV =====
async def import_csv(csv_path: str, conn):
    filename = os.path.basename(csv_path)
    print(f"📥 Импортирую: {filename}")
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            delim = '|' if '|' in first_line else ';' if ';' in first_line else ','
        
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=delim)
            if not reader.fieldnames:
                print(f"⚠️ Нет заголовков в {filename}")
                return 0
            
            cols_map = find_columns(reader.fieldnames)
            count = 0
            
            for row in reader:
                parts = [row.get(col, '') for col in reader.fieldnames]
                
                # Имя и фамилия
                if cols_map['first_name'] is not None and cols_map['last_name'] is not None:
                    first = parts[cols_map['first_name']].strip()
                    last = parts[cols_map['last_name']].strip()
                    full_name = f"{first} {last}".strip()
                elif cols_map['first_name'] is not None:
                    full_name = parts[cols_map['first_name']].strip()
                else:
                    full_name = ''
                
                # Телефон
                phone_raw = parts[cols_map['phone']].strip() if cols_map['phone'] is not None else ''
                phone = normalize_phone(phone_raw)
                
                # Email
                email = parts[cols_map['email']].strip() if cols_map['email'] is not None else ''
                
                # Адрес
                address = parts[cols_map['address']].strip() if cols_map['address'] is not None else ''
                
                # Паспорт
                passport = parts[cols_map['passport']].strip() if cols_map['passport'] is not None else ''
                
                # Дата рождения
                birth_date = parts[cols_map['birth_date']].strip() if cols_map['birth_date'] is not None else ''
                
                # Соцсети
                social_vk = parts[cols_map['social_vk']].strip() if cols_map['social_vk'] is not None else ''
                social_tg = parts[cols_map['social_tg']].strip() if cols_map['social_tg'] is not None else ''
                social_ok = parts[cols_map['social_ok']].strip() if cols_map['social_ok'] is not None else ''
                
                if not full_name and not phone and not email:
                    continue
                
                await conn.execute('''
                    INSERT INTO people (
                        phone, email, full_name, address,
                        social_vk, social_tg, social_ok,
                        passport, birth_date
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO NOTHING
                ''', phone, email, full_name, address, social_vk, social_tg, social_ok, passport, birth_date)
                
                count += 1
            
            print(f"   ✅ Импортировано {count} записей")
            return count
            
    except Exception as e:
        print(f"❌ Ошибка импорта {filename}: {e}")
        return 0

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
async def main():
    print("🔥 УНИВЕРСАЛЬНЫЙ ИМПОРТ В TIGERDATA")
    print("═" * 60)
    
    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"📁 Папка '{INPUT_FOLDER}' создана. Положите туда CSV-файлы.")
        return
    
    csv_files = []
    for root, _, files in os.walk(INPUT_FOLDER):
        for f in files:
            if f.endswith('.csv'):
                csv_files.append(os.path.join(root, f))
    
    if not csv_files:
        print("❌ В папке 'databases' нет CSV-файлов.")
        return
    
    print(f"📂 Найдено CSV-файлов: {len(csv_files)}")
    
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Подключение к TigerData установлено")
    except Exception as e:
        print(f"❌ Ошибка подключения к TigerData: {e}")
        return
    
    total = 0
    async with pool.acquire() as conn:
        for csv_path in csv_files:
            count = await import_csv(csv_path, conn)
            total += count
    
    await pool.close()
    print(f"\n✅ Импортировано ВСЕГО: {total} записей")

if __name__ == "__main__":
    asyncio.run(main())