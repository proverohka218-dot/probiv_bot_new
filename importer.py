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
ARCHIVE_PASSWORD = None

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

def extract_archive(file_path, output_dir, password=None):
    ext = os.path.splitext(file_path)[1].lower()
    if os.system('which 7zz >/dev/null 2>&1') == 0:
        cmd = ['7zz', 'x', file_path, f'-o{output_dir}', '-y']
    elif os.system('which 7z >/dev/null 2>&1') == 0:
        cmd = ['7z', 'x', file_path, f'-o{output_dir}', '-y']
    else:
        print("❌ 7zz/7z не найден. Установи p7zip.")
        return False
    if password:
        cmd.append('-p' + password)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Распакован: {os.path.basename(file_path)}")
        return True
    except Exception as e:
        print(f"❌ Ошибка распаковки {os.path.basename(file_path)}: {e}")
        return False

def find_data_files(folder):
    files = []
    for root, _, items in os.walk(folder):
        for f in items:
            if f.endswith('.csv') or f.endswith('.txt'):
                files.append(os.path.join(root, f))
    return files

def detect_column(header_row):
    cols = {
        'full_name': 0,
        'phone': 1,
        'email': None,
        'address': None,
        'school': None,
        'class': None,
        'class_teacher': None,
        'inn': None,
        'passport': None,
        'birth_date': None,
        'social_vk': None,
        'social_tg': None,
        'social_ok': None,
    }
    return cols

async def import_data_file(file_path: str, conn):
    print(f"📥 Импортирую: {os.path.basename(file_path)}")
    
    # ===== УВЕЛИЧИВАЕМ ЛИМИТ ДЛИНЫ СТРОКИ (ИСПРАВЛЕНИЕ ОШИБКИ) =====
    csv.field_size_limit(10_000_000)
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            if '\t' in first_line:
                delim = '\t'
            elif ';' in first_line:
                delim = ';'
            elif '|' in first_line:
                delim = '|'
            else:
                delim = ','

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter=delim)
            header_row = next(reader, None)
            if not header_row:
                print(f"⚠️ Файл пустой: {os.path.basename(file_path)}")
                return 0

            cols = detect_column(header_row)
            print(f"   🔍 Телефон: колонка {cols['phone']}, Имя: колонка {cols['full_name']}")

            count = 0
            for row in reader:
                if not row or all(cell.strip() == '' for cell in row):
                    continue

                phone = None
                full_name = ''

                if cols['phone'] is not None and cols['phone'] < len(row):
                    phone = normalize_phone(row[cols['phone']].strip())
                if cols['full_name'] is not None and cols['full_name'] < len(row):
                    full_name = row[cols['full_name']].strip()

                if not full_name and not phone:
                    continue

                await conn.execute('''
                    INSERT INTO people (phone, email, full_name, address,
                                        social_vk, social_tg, social_ok,
                                        passport, birth_date,
                                        school, class, inn, class_teacher)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (id) DO NOTHING
                ''', phone, '', full_name, '', '', '', '', '', '', '', '', '', '')

                count += 1
                if count % 100 == 0:
                    print(f"   📊 Импортировано: {count}")

            print(f"   ✅ Импортировано {count} записей")
            return count

    except Exception as e:
        print(f"❌ Ошибка импорта {os.path.basename(file_path)}: {e}")
        return 0

async def main():
    print("🔥 УНИВЕРСАЛЬНЫЙ ИМПОРТ (С ФИКСОМ ДЛИННЫХ СТРОК)")
    print("═" * 60)
    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"📁 Папка '{INPUT_FOLDER}' создана. Положите туда файлы.")
        return

    all_files = []
    for root, _, files in os.walk(INPUT_FOLDER):
        for f in files:
            all_files.append(os.path.join(root, f))

    if not all_files:
        print("❌ В папке 'databases' нет файлов.")
        return

    print(f"📂 Найдено файлов: {len(all_files)}")
    temp_dir = tempfile.mkdtemp()
    data_files = []

    for file_path in all_files:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.rar', '.7z', '.zip']:
            print(f"📦 Распаковка: {os.path.basename(file_path)}")
            if extract_archive(file_path, temp_dir, ARCHIVE_PASSWORD):
                data_files.extend(find_data_files(temp_dir))
        elif ext in ['.csv', '.txt']:
            data_files.append(file_path)

    if not data_files:
        print("❌ Не найдено CSV/TXT-файлов после распаковки.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    print(f"📄 Найдено файлов для импорта: {len(data_files)}")
    for f in data_files:
        print(f"   {f}")

    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Подключение к TigerData установлено")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    total = 0
    async with pool.acquire() as conn:
        for file_path in data_files:
            count = await import_data_file(file_path, conn)
            total += count

    await pool.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"\n✅ Импортировано ВСЕГО: {total} записей")

if __name__ == "__main__":
    asyncio.run(main())