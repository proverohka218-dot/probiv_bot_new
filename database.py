#!#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncpg
import hashlib
import json
import random
import string
import re
from datetime import datetime, timedelta
from config import DATABASE_URL

pool = None

async def init_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS people (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20),
                email VARCHAR(255),
                full_name TEXT,
                address TEXT,
                social_vk VARCHAR(50),
                social_tg VARCHAR(50),
                social_ok VARCHAR(50),
                passport VARCHAR(20),
                birth_date TEXT,
                school TEXT,
                class VARCHAR(20),
                inn VARCHAR(20),
                class_teacher TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id BIGINT PRIMARY KEY,
                subscription_end TIMESTAMP,
                promo_code TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                duration_days INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                query TEXT,
                result_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS osint_cache (
                query_hash TEXT PRIMARY KEY,
                query_type TEXT,
                query_value TEXT,
                result JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                free_queries INTEGER DEFAULT 2
            )
        ''')
        print("✅ База данных инициализирована")

async def is_subscription_active(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT subscription_end FROM subscriptions WHERE user_id = $1', user_id)
        if row:
            return row['subscription_end'] > datetime.now()
    return False

async def activate_subscription(user_id: int, days: int = 30, promo_code: str = None):
    end_date = datetime.now() + timedelta(days=days)
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO subscriptions (user_id, subscription_end, promo_code)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET subscription_end = $2, promo_code = $3
        ''', user_id, end_date, promo_code)

async def get_subscription_info(user_id: int) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT subscription_end, promo_code FROM subscriptions WHERE user_id = $1', user_id)
        if row:
            days_left = (row['subscription_end'] - datetime.now()).days
            return {'active': days_left > 0, 'days_left': max(0, days_left), 'promo_code': row['promo_code']}
    return {'active': False, 'days_left': 0, 'promo_code': None}

def generate_promo_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def add_promo_code(code: str, duration_days: int, created_by: int):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO promocodes (code, duration_days, created_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (code) DO NOTHING
        ''', code, duration_days, created_by)

async def get_promo_duration(code: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT duration_days FROM promocodes WHERE code = $1', code)
        if row:
            return row['duration_days']
    return 0

async def search_db(query: str):
    # Если это номер телефона — нормализуем его
    if re.match(r'^\+?\d{10,15}$', query) or re.match(r'^8\d{10}$', query):
        raw_number = re.sub(r'[^0-9]', '', query)
        if raw_number.startswith('8') and len(raw_number) == 11:
            raw_number = '7' + raw_number[1:]
        query = raw_number

    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return []

    conditions = []
    params = []
    for word in words:
        conditions.append(f"(phone ILIKE ${len(params)+1} OR email ILIKE ${len(params)+2} OR full_name ILIKE ${len(params)+3})")
        params.extend([f'%{word}%', f'%{word}%', f'%{word}%'])

    sql_query = f"""
        SELECT * FROM people 
        WHERE {' AND '.join(conditions)}
        LIMIT 20
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql_query, *params)
        return [dict(row) for row in rows]

async def log_search(user_id: int, query: str, result_count: int):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO search_history (user_id, query, result_count)
            VALUES ($1, $2, $3)
        ''', user_id, query, result_count)

def get_cache_key(query: str, qtype: str) -> str:
    return hashlib.md5(f"{qtype}:{query}".encode()).hexdigest()

async def get_cached_result(query_hash: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT result FROM osint_cache 
            WHERE query_hash = $1 AND created_at > NOW() - INTERVAL '24 hours'
        ''', query_hash)
        if row:
            return row['result']
    return None

async def save_to_cache(query_hash: str, qtype: str, query: str, result: dict):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO osint_cache (query_hash, query_type, query_value, result)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (query_hash) DO UPDATE SET result = $4, created_at = NOW()
        ''', query_hash, qtype, query, json.dumps(result, default=str))

async def get_free_queries(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT free_queries FROM users WHERE user_id = $1', user_id)
        if row:
            return row['free_queries']
    return 2

async def decrement_free_queries(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, free_queries) VALUES ($1, 2)
            ON CONFLICT (user_id) DO UPDATE SET free_queries = users.free_queries - 1
        ''', user_id)