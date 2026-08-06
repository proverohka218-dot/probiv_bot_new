import os
import openai
from config import BOT_TOKEN  # не используется, но для порядка

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

async def run_osint(query: str) -> dict:
    """
    Запускает OpenOSINT через DeepSeek API.
    Возвращает словарь с ключом 'result'.
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
        return {"result": response.choices[0].message.content}
    except Exception as e:
        return {"result": f"❌ Ошибка OpenOSINT: {e}"}