"""Shared pytest helpers.

Tests compile the YAML profiles themselves (in memory) instead of relying on the
generated public/profiles/*.json, so `pytest` works on a fresh checkout.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from thesischeck import check
from tools.compile_profiles import PROFILES_DIR, compile_profile_file
from tools.make_samples import to_bytes

SAMPLES_DIR = Path(__file__).parent / "samples"
FIXED_NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def demo_profile() -> dict:
    return compile_profile_file(PROFILES_DIR / "demo.yaml")


@pytest.fixture(scope="session")
def rtu_profile() -> dict:
    return compile_profile_file(PROFILES_DIR / "rtu-fcsite-bachelor.yaml")


def sample_bytes(name: str) -> bytes:
    return (SAMPLES_DIR / f"{name}.docx").read_bytes()


def run(data: bytes, profile: dict) -> dict:
    return check(data, profile, file_name="test.docx", now=FIXED_NOW)


def run_sample(name: str, profile: dict) -> dict:
    return run(sample_bytes(name), profile)


def run_doc(document, profile: dict) -> dict:
    """Check a python-docx Document built inside a test."""
    return run(to_bytes(document), profile)


def rule_ids(report: dict) -> list[str]:
    return [f["rule_id"] for f in report["findings"]]
