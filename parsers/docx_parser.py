from io import BytesIO

from docx import Document


async def extract_docx_text(content: bytes) -> str:
    doc = Document(BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text)
