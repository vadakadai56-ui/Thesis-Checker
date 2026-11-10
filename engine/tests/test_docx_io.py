"""Safe opening of files (docx_io). Stage 2 adds the full test_security.py suite."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile

import pytest

from conftest import run, sample_bytes
from thesischeck.docx_io import MAX_ENTRIES, OLE_MAGIC, inspect_package, safe_parse
from thesischeck.model import EngineError


def _zip(entries: dict[str, bytes], method=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _docx_entries() -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(sample_bytes("clean"))) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _code(data: bytes) -> str:
    with pytest.raises(EngineError) as err:
        inspect_package(data)
    return err.value.code


def test_clean_sample_is_accepted():
    inspect_package(sample_bytes("clean"))


def test_random_bytes():
    assert _code(os.urandom(4096)) == "NOT_DOCX"


def test_legacy_doc():
    assert _code(OLE_MAGIC + b"\x00" * 600) == "LEGACY_DOC"


def test_encrypted_docx():
    assert _code(OLE_MAGIC + b"\x00" * 64 + "EncryptedPackage".encode("utf-16-le")) == "ENCRYPTED"


def test_odt():
    data = _zip({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b"<x/>"})
    assert _code(data) == "ODT"


def test_docm_macros():
    entries = _docx_entries() | {"word/vbaProject.bin": b"\x00" * 10}
    assert _code(_zip(entries)) == "MACRO_DOCM"


def test_truncated_zip():
    assert _code(sample_bytes("clean")[:2000]) == "CORRUPT"


def test_path_traversal():
    entries = _docx_entries() | {"../evil.txt": b"x"}
    assert _code(_zip(entries)) == "CORRUPT"


def test_too_many_entries():
    entries = _docx_entries() | {f"word/media/x{i}.bin": b"" for i in range(MAX_ENTRIES)}
    assert _code(_zip(entries, zipfile.ZIP_STORED)) == "ZIP_BOMB"


def test_high_compression_ratio():
    entries = _docx_entries() | {"word/media/big.bin": b"\x00" * (5 * 1024 * 1024)}
    assert _code(_zip(entries)) == "ZIP_BOMB"


def test_doctype_rejected():
    xxe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    entries = _docx_entries() | {"word/document.xml": xxe}
    assert _code(_zip(entries)) == "CORRUPT"


def test_safe_parse_rejects_doctype():
    with pytest.raises(EngineError):
        safe_parse(b'<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')


def test_check_raises_engine_error_with_friendly_message(demo_profile):
    with pytest.raises(EngineError) as err:
        run(b"not a docx", demo_profile)
    assert err.value.code == "NOT_DOCX"
    assert "Word .docx" in err.value.message


def test_input_bytes_unchanged_and_hashed(demo_profile):
    data = sample_bytes("clean")
    before = hashlib.sha256(data).hexdigest()
    report = run(data, demo_profile)
    assert hashlib.sha256(data).hexdigest() == before == report["document_sha256"]
