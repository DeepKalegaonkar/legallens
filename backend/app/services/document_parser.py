import io

import docx
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}


class UnsupportedFileTypeError(ValueError):
    pass


def extract_text(filename: str, file_bytes: bytes) -> str:
    extension = _get_extension(filename)

    if extension == ".txt":
        return file_bytes.decode("utf-8", errors="ignore")

    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    if extension == ".docx":
        document = docx.Document(io.BytesIO(file_bytes))
        return "\n\n".join(paragraph.text for paragraph in document.paragraphs)

    raise UnsupportedFileTypeError(f"Unsupported file type: {extension}")


def _get_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()
