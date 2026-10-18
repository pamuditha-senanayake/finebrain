# extract.py: plain text from an uploaded file, before S1 takes it in. Text, Markdown and CSV are read as they are;
# PDF and Word are read with pypdf and python-docx. Anything else, or a file with no text, is refused.
# Used by: app/api/documents.py, tests/test_documents.py. Uses: nothing local.
import io
from pathlib import PurePosixPath

from docx import Document as WordDocument
from pypdf import PdfReader

# Config
TEXT_TYPES = {".txt", ".md", ".csv"}
READABLE = TEXT_TYPES | {".pdf", ".docx"}


class UnreadableFile(Exception):
    """The file type is not supported, or the file holds no text we can read."""


def kind_of(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def text_of(filename: str, data: bytes) -> str:
    """The file's text, or UnreadableFile."""
    kind = kind_of(filename)
    if kind not in READABLE:
        raise UnreadableFile(f"unsupported_type:{kind or 'none'}")
    try:
        if kind in TEXT_TYPES:
            text = data.decode("utf-8", errors="replace")
        elif kind == ".pdf":
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        else:
            text = "\n\n".join(paragraph.text for paragraph in WordDocument(io.BytesIO(data)).paragraphs)
    except UnreadableFile:
        raise
    except Exception:  # a broken or encrypted file: the readers raise many kinds of errors
        raise UnreadableFile("broken_file") from None
    if not text.strip():
        raise UnreadableFile("no_text")
    return text.strip()
