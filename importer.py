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
ARCHIVE_PASSWORD = None  # Если нужен пароль — вставь сюда

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
    cmd = []
    if ext == '.rar':
        cmd = ['unrar', 'x', '-y']
        if password:
            cmd.extend(['-p' + password])
        cmd.extend([file_path, output_dir])
    elif ext == '.7z':
        cmd = ['7z', 'x', file_path, f'-o{output_dir}', '-y']
        if password:
            cmd.append('-p' + password)
    elif ext == '.zip':
        cmd = ['unzip', '-o']
        if password:
            cmd.extend(['-P', password])
        cmd.extend([file_path, '-d', output_dir])
    else:
        return False
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Распакован: {os.path.basename(file_path)}")
        return True
    except Exception as e:
        print(f"❌ Ошибка распаковки {os.path.basename(file_path)}: {e}")
        return False

def find_csv_files(folder):
    csv_files = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith('.csv'):
                csv_files.append(os.path.join(root, f))
    return csv_files

# ===== УНИВЕРСАЛЬНЫЙ ПОИСК КОЛОНОК =====
def detect_column(header_row):
    cols = {}
    lower_headers = [str(h).lower().strip() for h in header_row]

    keywords = {
        'full_name': ['фио', 'ф.и.о.', 'fio', 'имя', 'фамилия', 'name', 'fullname', 'ученик', 'учащийся', 'студент', 'сотрудник', 'заказчик', 'клиент', 'контакт', 'лицо', 'человек', 'пользователь'],
        'phone': ['телефон', 'phone', 'мобильный', 'мобильный телефон', 'номер', 'contact', 'tel', 'whatsapp', 'viber', 'telegram'],
        'email': ['email', 'почта', 'e-mail', 'mail', 'эл.почта', 'электронная почта'],
        'address': ['адрес', 'address', 'место', 'проживание', 'регистрация', 'локация', 'location'],
        'school': ['школа', 'school', 'гимназия', 'лицей', 'учебное заведение', 'место учебы', 'education', 'учится'],
        'class': ['класс', 'class', 'группа', 'курс', 'параллель', 'year', 'grade'],
        'class_teacher': ['классный руководитель', 'классный', 'class teacher', 'учитель', 'преподаватель', 'куратор', 'наставник', 'классрук'],
        'inn': ['инн', 'inn', 'иин', 'налоговый номер', 'идентификационный номер'],
        'passport': ['паспорт', 'passport', 'серия', 'номер паспорта', 'удостоверение', 'документ'],
        'birth_date': ['дата рождения', 'birth', 'день рождения', 'год рождения', 'рождения', 'age', 'возраст'],
        'social_vk': ['vk', 'вк', 'vkontakte'],
        'social_tg': ['tg', 'telegram', 'телеграм'],
        'social_ok': ['ok', 'одноклассники', 'odnoklassniki'],
    }

    for field, words in keywords.items():
        found = False
        for i, header in enumerate(lower_headers):
            if any(word in header for word in words):
                cols[field] = i
                found = True
                break
        if not found:
            cols[field] = None

    if cols['full_name'] is None and cols['phone'] is None:
        if len(header_row) >= 2:
            cols['full_name'] = 0
            cols['phone'] = 1
        elif len(header_row) == 1:
            cols['full_name'] = 0

    return cols

async def import_csv_file(csv_path: str, conn):
    print(f"📥 Импортирую: {os.path.basename(csv_path)}")
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            delim = '|' if '|' in first_line else ';' if ';' in first_line else ','

        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter=delim)
            header_row = next(reader, None)
            if not header_row:
                print(f"⚠️ Файл пустой: {os.path.basename(csv_path)}")
                return 0

            cols = detect_column(header_row)
            print(f"   🔍 Найдены колонки: {cols}")

            count = 0
            for row in reader:
                if not row or all(cell.strip() == '' for cell in row):
                    continue

                full_name = ''
                phone = None
                email = ''
                address = ''
                school = ''
                class_name = ''
                class_teacher = ''
                inn = ''
                passport = ''
                birth_date = ''
                social_vk = ''
                social_tg = ''
                social_ok = ''

                if cols['full_name'] is not None and cols['full_name'] < len(row):
                    full_name = row[cols['full_name']].strip()
                if cols['phone'] is not None and cols['phone'] < len(row):
                    phone = normalize_phone(row[cols['phone']].strip())
                if cols['email'] is not None and cols['email'] < len(row):
                    email = row[cols['email']].strip()
                if cols['address'] is not None and cols['address'] < len(row):
                    address = row[cols['address']].strip()
                if cols['school'] is not None and cols['school'] < len(row):
                    school = row[cols['school']].strip()
                if cols['class'] is not None and cols['class'] < len(row):
                    class_name = row[cols['class']].strip()
                if cols['class_teacher'] is not None and cols['class_teacher'] < len(row):
                    class_teacher = row[cols['class_teacher']].strip()
                if cols['inn'] is not None and cols['inn'] < len(row):
                    inn = row[cols['inn']].strip()
                if cols['passport'] is not None and cols['passport'] < len(row):
                    passport = row[cols['passport']].strip()
                if cols['birth_date'] is not None and cols['birth_date'] < len(row):
                    birth_date = row[cols['birth_date']].strip()
                if cols['social_vk'] is not None and cols['social_vk'] < len(row):
                    social_vk = row[cols['social_vk']].strip()
                if cols['social_tg'] is not None and cols['social_tg'] < len(row):
                    social_tg = row[cols['social_tg']].strip()
                if cols['social_ok'] is not None and cols['social_ok'] < len(row):
                    social_ok = row[cols['social_ok']].strip()

                if not full_name and not phone:
                    continue

                await conn.execute('''
                    INSERT INTO people (
                        phone, email, full_name, address,
                        social_vk, social_tg, social_ok,
                        passport, birth_date,
                        school, class, inn, class_teacher
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (id) DO NOTHING
                ''', phone, email, full_name, address, social_vk, social_tg, social_ok, passport, birth_date, school, class_name, inn, class_teacher)

                count += 1
                if count % 100 == 0:
                    print(f"   📊 Импортировано: {count}")

            print(f"   ✅ Импортировано {count} записей")
            return count

    except Exception as e:
        print(f"❌ Ошибка импорта {os.path.basename(csv_path)}: {e}")
        return 0

async def main():
    print("🔥 УНИВЕРСАЛЬНЫЙ ИМПОРТ (С ИНН, ШКОЛОЙ, КЛАССОМ И КЛАССНЫМ РУКОВОДИТЕЛЕМ)")
    print("═" * 60)

    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"📁 Папка '{INPUT_FOLDER}' создана. Положите туда CSV или архивы.")
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
    csv_files = []

    for file_path in all_files:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.rar', '.7z', '.zip']:
            print(f"📦 Распаковка: {os.path.basename(file_path)}")
            if extract_archive(file_path, temp_dir, ARCHIVE_PASSWORD):
                csv_files.extend(find_csv_files(temp_dir))
        elif ext == '.csv':
            csv_files.append(file_path)

    if not csv_files:
        print("❌ Не найдено CSV-файлов после распаковки.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    print(f"📄 Найдено CSV-файлов: {len(csv_files)}")
    for f in csv_files:
        print(f"   {f}")

    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Подключение к TigerData установлено")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    total = 0
    async with pool.acquire() as conn:
        for csv_path in csv_files:
            count = await import_csv_file(csv_path, conn)
            total += count

    await pool.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"\n✅ Импортировано ВСЕГО: {total} записей")

if __name__ == "__main__":
    asyncio.run(main())