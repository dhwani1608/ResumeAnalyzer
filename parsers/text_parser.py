async def extract_text(content: bytes) -> str:
    return content.decode("utf-8", errors="ignore")
