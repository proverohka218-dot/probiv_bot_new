#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncpg
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
        print("✅ База данных обновлена (добавлены school, class, inn, class_teacher)")