"""Open a .docx safely (BUILD_PROMPT §10).

A .docx file is really a ZIP archive full of XML files. A malicious or broken file
could try to:
  * be tiny when zipped but enormous when unzipped (a "zip bomb"),
  * contain thousands of entries to exhaust memory,
  * use names like "../../evil" (path traversal),
  * use XML tricks (<!DOCTYPE …>) to read local files (XXE) or explode in size
    ("billion laughs"),
  * carry macros (.docm / vbaProject.bin).
So BEFORE python-docx touches the bytes we inspect the archive ourselves and reject
anything suspicious with a clear error code. We never execute anything from the file.
"""

from __future__ import annotations

import io
import re
import zipfile

from lxml import etree

from .model import EngineError

MAX_COMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB input cap (assumed, §8)
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB when unzipped
MAX_ENTRIES = 2000
MAX_RATIO = 100  # an entry may unzip to at most 100× its zipped size

# Old binary Office files (.doc, and password-protected .docx) start with this
# "OLE compound file" signature instead of the ZIP signature "PK".
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# A password-protected .docx is an OLE file containing a stream with this name
# (stored as UTF-16, hence the zero bytes between letters).
ENCRYPTED_MARK = "EncryptedPackage".encode("utf-16-le")
ZIP_MAGIC = b"PK\x03\x04"

_DOCTYPE_RE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)
_CHUNK = 1024 * 1024


def safe_xml_parser() -> etree.XMLParser:
    """An lxml parser that never loads DTDs, never expands entities, never uses the network."""
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def safe_parse(xml_bytes: bytes) -> etree._Element:
    """Parse XML we read ourselves (e.g. the theme part). Rejects any DOCTYPE."""
    if _DOCTYPE_RE.search(xml_bytes):
        raise EngineError("CORRUPT", "XML part contains a DOCTYPE")
    try:
        return etree.fromstring(xml_bytes, safe_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise EngineError("CORRUPT", f"XML syntax error: {exc}") from exc


def _is_unsafe_name(name: str) -> bool:
    """Entry names must be simple relative paths inside the archive."""
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        return True
    return ".." in normalised.split("/")


def inspect_package(data: bytes) -> None:
    """Raise EngineError if `data` is not a safe, ordinary .docx. Returns None if OK."""
    if len(data) > MAX_COMPRESSED_BYTES:
        raise EngineError("FILE_TOO_LARGE", f"{len(data)} bytes")

    if data.startswith(OLE_MAGIC):
        if ENCRYPTED_MARK in data:
            raise EngineError("ENCRYPTED", "OLE file with EncryptedPackage stream")
        raise EngineError("LEGACY_DOC", "OLE compound file (old .doc format)")

    if not data.startswith(ZIP_MAGIC):
        raise EngineError("NOT_DOCX", "file does not start with a ZIP signature")

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as exc:
        raise EngineError("CORRUPT", f"not a readable ZIP: {exc}") from exc

    with archive:
        _check_entries(archive)


def _check_entries(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise EngineError("ZIP_BOMB", f"{len(infos)} entries (limit {MAX_ENTRIES})")

    names = {info.filename for info in infos}
    for name in names:
        if _is_unsafe_name(name):
            raise EngineError("CORRUPT", f"unsafe entry name: {name!r}")

    # OpenDocument (.odt) files are ZIPs too; they announce themselves in "mimetype".
    if "mimetype" in names:
        mimetype = archive.read("mimetype")[:200]
        if mimetype.startswith(b"application/vnd.oasis.opendocument"):
            raise EngineError("ODT", mimetype.decode("ascii", "replace"))

    lower_names = {n.lower() for n in names}
    if any(n.endswith("vbaproject.bin") for n in lower_names):
        raise EngineError("MACRO_DOCM", "archive contains vbaProject.bin")

    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise EngineError("NOT_DOCX", "missing [Content_Types].xml or word/document.xml")

    # Read every entry in chunks, counting the bytes we ACTUALLY get. The sizes
    # written in the ZIP header can lie, so we never trust them alone.
    total = 0
    for info in infos:
        total += _read_entry_checked(archive, info, MAX_UNCOMPRESSED_BYTES - total)

    content_types = archive.read("[Content_Types].xml")
    if b"macroEnabled" in content_types:
        raise EngineError("MACRO_DOCM", "macro-enabled content type")


def _read_entry_checked(archive: zipfile.ZipFile, info: zipfile.ZipInfo, budget: int) -> int:
    """Read one entry, enforcing the size budget and the 100:1 ratio. Returns its size."""
    is_xml = info.filename.lower().endswith((".xml", ".rels"))
    max_for_ratio = max(info.compress_size, 1) * MAX_RATIO
    size = 0
    head = b""
    try:
        with archive.open(info) as stream:
            while chunk := stream.read(_CHUNK):
                size += len(chunk)
                if size > budget:
                    raise EngineError("ZIP_BOMB", "uncompressed size over 200 MB")
                if size > max_for_ratio:
                    raise EngineError(
                        "ZIP_BOMB", f"{info.filename}: compression ratio over {MAX_RATIO}:1"
                    )
                if is_xml and _DOCTYPE_RE.search(head[-16:] + chunk):
                    raise EngineError("CORRUPT", f"{info.filename}: DOCTYPE not allowed")
                head = chunk
    except EngineError:
        raise
    except (zipfile.BadZipFile, EOFError, OSError, NotImplementedError) as exc:
        # BadZipFile here usually means a CRC mismatch: the entry is damaged.
        raise EngineError("CORRUPT", f"{info.filename}: {exc}") from exc
    return size


def open_docx(data: bytes):
    """Inspect `data`, then open it with python-docx. Returns a docx Document.

    `data` itself is never modified: python-docx reads from an in-memory copy.
    """
    inspect_package(data)
    # Imported here so that just importing this module stays cheap.
    import docx

    try:
        return docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises many different error types
        raise EngineError("CORRUPT", f"python-docx could not open it: {exc}") from exc
