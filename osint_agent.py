import subprocess

async def run_osint(query: str) -> str:
    """
    Запускает OpenOSINT через командную строку.
    """
    result = subprocess.run(
        ["openosint", query],
        capture_output=True,
        text=True
    )
    return result.stdout