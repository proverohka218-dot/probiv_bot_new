#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import re
import subprocess
import shutil
import tempfile
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

# ===== РАСПАКОВКА АРХИВОВ =====
def extract_archive(file_path, output_dir):
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.rar', '.7z', '.zip']:
        cmd = []
        if ext == '.rar':
            cmd = ['unrar', 'x', '-y', file_path, output_dir]
        elif ext == '.7z':
            cmd = ['7z', 'x', file_path, f'-o{output_dir}', '-y']
        elif ext == '.zip':
            cmd = ['unzip', '-o', file_path, '-d', output_dir]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"✅ Распакован: {os.path.basename(file_path)}")
            return True
        except:
            pass
    return False

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
async def main():
    print("🔥 ИМПОРТ В TIGERDATA (С РАСПАКОВКОЙ)")
    print("═" * 60)

    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"📁 Папка '{INPUT_FOLDER}' создана. Положите туда CSV или архивы.")
        return

    # Собираем все файлы
    all_files = []
    for root, _, files in os.walk(INPUT_FOLDER):
        for f in files:
            all_files.append(os.path.join(root, f))

    if not all_files:
        print("❌ В папке 'databases' нет файлов.")
        return

    print(f"📂 Найдено файлов: {len(all_files)}")

    # Временная папка для распакованных файлов
    temp_dir = tempfile.mkdtemp()
    csv_files = []

    for file_path in all_files:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.rar', '.7z', '.zip']:
            print(f"📦 Распаковка: {os.path.basename(file_path)}")
            if extract_archive(file_path, temp_dir):
                # Ищем CSV в распакованном
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if f.endswith('.csv'):
                            csv_files.append(os.path.join(root, f))
        elif ext == '.csv':
            csv_files.append(file_path)

    if not csv_files:
        print("❌ Не найдено CSV-файлов после распаковки.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    print(f"📄 Найдено CSV-файлов: {len(csv_files)}")

    # Подключаемся к БД
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Подключение к TigerData установлено")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    total = 0
    async with pool.acquire() as conn:
        for csv_path in csv_files:
            print(f"📥 Импортирую: {os.path.basename(csv_path)}")
            try:
                with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                    first_line = f.readline()
                    delim = '|' if '|' in first_line else ';' if ';' in first_line else ','
                with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.DictReader(f, delimiter=delim)
                    if not reader.fieldnames:
                        continue
                    cols = reader.fieldnames
                    name_col = next((i for i,c in enumerate(cols) if any(k in c.lower() for k in ['фио','name','имя'])), None)
                    phone_col = next((i for i,c in enumerate(cols) if any(k in c.lower() for k in ['телефон','phone','mobile'])), None)
                    email_col = next((i for i,c in enumerate(cols) if any(k in c.lower() for k in ['email','почта'])), None)
                    if name_col is None and phone_col is None:
                        if len(cols) >= 2:
                            name_col, phone_col = 0, 1
                        else:
                            continue
                    count = 0
                    for row in reader:
                        parts = [row.get(c, '') for c in cols]
                        name = parts[name_col].strip() if name_col is not None else ''
                        phone_raw = parts[phone_col].strip() if phone_col is not None else ''
                        phone = normalize_phone(phone_raw)
                        email = parts[email_col].strip() if email_col is not None else ''
                        if not name and not phone:
                            continue
                        await conn.execute('''
                            INSERT INTO people (phone, email, full_name)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (id) DO NOTHING
                        ''', phone, email, name)
                        count += 1
                    print(f"   ✅ Импортировано {count} записей")
                    total += count
            except Exception as e:
                print(f"❌ Ошибка импорта {os.path.basename(csv_path)}: {e}")

    await pool.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"\n✅ Импортировано ВСЕГО: {total} записей")

if __name__ == "__main__":
    asyncio.run(main())