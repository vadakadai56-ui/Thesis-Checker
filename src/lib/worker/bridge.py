"""Glue between the Web Worker (JavaScript) and the thesischeck engine.

This file lives with the browser code on purpose: the engine package itself
(engine/thesischeck) must never know about JavaScript or Pyodide (BUILD_PROMPT §7).

Every function takes plain values and returns a JSON string (plus bytes for the
file-producing ones), so nothing complicated crosses the JS <-> Python boundary.
Expected problems with the file come back as {"ok": false, "error": {...}}.
"""

import json
from datetime import datetime

import thesischeck
from thesischeck.model import EngineError


def _now(now_iso):
    return datetime.fromisoformat(now_iso) if now_iso else None


def _run(fn):
    try:
        return fn()
    except EngineError as err:
        return json.dumps({"ok": False, "error": err.to_dict()}), None
    except MemoryError:
        error = {"code": "OUT_OF_MEMORY", "message": "", "detail": "MemoryError"}
        return json.dumps({"ok": False, "error": error}), None
    except Exception as exc:  # anything unexpected: report it, never crash the worker
        error = {"code": "INTERNAL", "message": "", "detail": f"{type(exc).__name__}: {exc}"}
        return json.dumps({"ok": False, "error": error}), None


def engine_version():
    return thesischeck.ENGINE_VERSION


def check(data, profile_json, file_name, now_iso=None):
    def go():
        report = thesischeck.check(
            bytes(data), json.loads(profile_json), file_name=file_name, now=_now(now_iso)
        )
        return json.dumps({"ok": True, "report": report}), None

    return _run(go)


def _file_job(fn, data, profile_json, file_name, now_iso):
    def go():
        result = fn(bytes(data), json.loads(profile_json), file_name=file_name, now=_now(now_iso))
        out = result.pop("bytes")
        return json.dumps({"ok": True, "result": result}), out

    return _run(go)


def fix(data, profile_json, file_name, now_iso=None):
    return _file_job(thesischeck.fix, data, profile_json, file_name, now_iso)


def annotate(data, profile_json, file_name, now_iso=None):
    return _file_job(thesischeck.annotate, data, profile_json, file_name, now_iso)
