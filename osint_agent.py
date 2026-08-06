import os
import openai
from config import BOT_TOKEN  # не используется, но для порядка

# Читаем ключи из переменных окружения
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

if not OPENAI_API_KEY:
    print("⚠️ OPENAI_API_KEY не найден! OpenOSINT не будет работать.")
else:
    print("✅ OPENAI_API_KEY загружен")

# Настройка клиента OpenAI (совместим с DeepSeek)
client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

async def run_osint(query: str) -> str:
    """
    Запускает OpenOSINT через DeepSeek API.
    """
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — OSINT-агент. Помоги найти информацию по запросу."},
                {"role": "user", "content": query}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка OpenOSINT: {e}"