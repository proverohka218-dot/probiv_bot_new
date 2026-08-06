import openosint

async def run_osint(query: str) -> dict:
    """
    Запускает OpenOSINT-агента по запросу пользователя.
    Возвращает словарь с результатами.
    """
    agent = openosint.Agent()
    result = await agent.investigate(query)
    return result