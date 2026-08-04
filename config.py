import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # ← НОВОЕ

PRICE_STARS = 500

DB_PATH = os.path.join(os.path.dirname(__file__), "probiv.db")

API_KEYS = {
    "truecaller": os.getenv("TRUECALLER_KEY", ""),
    "numverify": os.getenv("NUMVERIFY_KEY", ""),
    "hunter": os.getenv("HUNTER_KEY", ""),
    "dehashed_email": os.getenv("DEHASHED_EMAIL", ""),
    "dehashed_api": os.getenv("DEHASHED_API", ""),
    "emailrep": os.getenv("EMAILREP_KEY", ""),
    "ip2location": os.getenv("IP2LOCATION_KEY", ""),
    "abuseipdb": os.getenv("ABUSEIPDB_KEY", ""),
    "vk": os.getenv("VK_TOKEN", ""),
    "ok_app": os.getenv("OK_APP_KEY", ""),
    "ok_session": os.getenv("OK_SESSION_KEY", ""),
    "fb": os.getenv("FB_TOKEN", ""),
    "telegram_bot": BOT_TOKEN,
    "fedresurs": os.getenv("FEDRESURS_KEY", ""),
    "opencage": os.getenv("OPENCAGE_KEY", ""),
    "pastebin": os.getenv("PASTEBIN_KEY", "")
}