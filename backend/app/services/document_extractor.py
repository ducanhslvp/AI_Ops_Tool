import io
import re
from zipfile import ZipFile

from pypdf import PdfReader


def extract_document(data: bytes, suffix: str) -> str:
    if suffix in {".md", ".txt"}:
        return data.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if suffix == ".docx":
        with ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    raise ValueError("Unsupported document type")
