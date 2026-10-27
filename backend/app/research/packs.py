# packs.py: reads an uploaded experiment pack safely (in memory, size and path limits, no links, text only), gives it a
# stable hash, and parses every file against its schema (pack_schemas.py). Parse errors become the Schema audit.
# Used by: research/pack_audits.py, research/routes.py, scripts/research_convert_execution_v1.py. Uses: research/pack_schemas.py.
import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath

from pydantic import BaseModel, ValidationError

from app.research.pack_schemas import KINDS, DocumentMeta, Manifest

# Config
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024  # stops a zip bomb before it is read
MAX_FILES = 5000
JUNK = {".DS_Store", "Thumbs.db", "desktop.ini"}  # left by file managers; ignored and not hashed, so the same pack hashes the same
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
SYMLINK = 0o120000


class PackRefused(ValueError):
    """The upload cannot be read as a pack at all. Its code says why, in words the screen shows."""


# --- Reading the zip

def is_junk(name: str) -> bool:
    path = PurePosixPath(name)
    return "__MACOSX" in path.parts or path.name in JUNK or path.name.startswith("._")  # macOS resource forks too


def check_entry(info: zipfile.ZipInfo) -> None:
    """Refuse paths that leave the pack, links, and encrypted files."""
    parts = PurePosixPath(info.filename).parts
    if info.filename.startswith(("/", "\\")) or ".." in parts or "\\" in info.filename:
        raise PackRefused(f"unsafe_path: {info.filename}")
    if (info.external_attr >> 16) & 0o170000 == SYMLINK:
        raise PackRefused(f"link_not_allowed: {info.filename}")
    if info.flag_bits & 0x1:
        raise PackRefused(f"encrypted: {info.filename}")


def normalized(raw: bytes, name: str) -> str:
    """UTF-8 text with Unix line endings and no byte order mark, so the hash does not depend on the machine that zipped it."""
    try:
        return raw.decode("utf-8").removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        raise PackRefused(f"not_text: {name}") from None


def without_top_folder(files: dict[str, str]) -> dict[str, str]:
    """A pack zipped as its folder has every path under one name; the pack starts inside it."""
    tops = {path.split("/", 1)[0] for path in files}
    if "manifest.json" in files or len(tops) != 1 or all("/" not in path for path in files):
        return files
    return {path.split("/", 1)[1]: text for path, text in files.items()}


def read_zip(data: bytes) -> dict[str, str]:
    """Every file of the pack as text, keyed by its path inside the pack."""
    if len(data) > MAX_ZIP_BYTES:
        raise PackRefused("too_large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PackRefused("not_a_zip") from None
    entries = [info for info in archive.infolist() if not info.is_dir() and not is_junk(info.filename)]
    if len(entries) > MAX_FILES or sum(info.file_size for info in entries) > MAX_UNPACKED_BYTES:
        raise PackRefused("too_large")
    for info in entries:
        check_entry(info)
    return without_top_folder({info.filename: normalized(archive.read(info), info.filename) for info in entries})


def pack_hash(files: dict[str, str]) -> str:
    """sha256 over every path and its normalized text, in path order."""
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode() + b"\0" + files[path].encode() + b"\0")
    return digest.hexdigest()


# --- Parsing

def front_matter(text: str) -> tuple[dict, str]:
    """Flat `key: value` lines; `[a, b]` is a list and an empty value is unset."""
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in filter(str.strip, match.group(1).split("\n")):
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        elif value:
            meta[key.strip()] = value.strip("'\"")
    return meta, match.group(2)


def parse_lines(text: str | None, model: type[BaseModel], path: str, errors: list[str]) -> list[BaseModel]:
    """One model per non-empty line; each bad line is an error naming its file and line number."""
    rows = []
    for number, line in enumerate((text or "").split("\n"), start=1):
        if not line.strip():
            continue
        try:
            rows.append(model.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as error:
            errors.append(f"{path}:{number}: {str(error).splitlines()[0]}")
    return rows


def parse_documents(files: dict[str, str], errors: list[str]) -> dict[str, dict]:
    documents = {}
    for path in sorted(p for p in files if p.startswith("documents/") and p.endswith((".md", ".txt"))):
        meta, body = front_matter(files[path])
        try:
            documents[meta.get("doc_id", path)] = {"meta": DocumentMeta.model_validate(meta), "body": body, "path": path}
        except ValidationError as error:
            errors.append(f"{path}: {str(error).splitlines()[0]}")
    return documents


def parse_pack(files: dict[str, str]) -> dict:
    """The manifest, documents, main and gold rows and extra files, plus every schema error found on the way."""
    errors: list[str] = []
    try:
        manifest = Manifest.model_validate(json.loads(files.get("manifest.json", "")))
    except (json.JSONDecodeError, ValidationError) as error:
        return {"manifest": None, "errors": [f"manifest.json: {str(error).splitlines()[0]}"], "files": files}
    kind = KINDS[manifest.kind]
    (main_path, main_model), (gold_path, gold_model) = kind["main"], kind["gold"]
    missing = [path for path in [main_path, gold_path, *kind["extra"], *manifest.files] if path not in files]
    errors += [f"{path}: missing" for path in sorted(set(missing))]
    return {"manifest": manifest, "files": files, "errors": errors, "documents": parse_documents(files, errors),
            "main": parse_lines(files.get(main_path), main_model, main_path, errors),
            "gold": parse_lines(files.get(gold_path), gold_model, gold_path, errors),
            "extra": {path: parse_lines(files.get(path), model, path, errors) for path, model in kind["extra"].items()}}
