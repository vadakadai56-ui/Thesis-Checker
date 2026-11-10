"""Data files shipped with the engine stay valid and up to date."""

from __future__ import annotations

from thesischeck.rules.ai_disclosure import ai_reference, ai_tools
from thesischeck.rules.consistency import spelling_pairs
from tools.make_spelling_pairs import OUT, render

AMBIGUOUS_US = {"program", "license", "meter", "practice", "check", "tire", "draft", "dialog"}


def test_spelling_pairs_up_to_date():
    """If this fails, run `python tools/make_spelling_pairs.py` and commit the TSV."""
    assert OUT.read_text(encoding="utf-8") == render()


def test_spelling_pairs_are_sane():
    uk_map, us_map = spelling_pairs()
    assert len(uk_map) > 1000
    assert all(uk != us for uk, (us, _) in uk_map.items())
    assert not AMBIGUOUS_US & set(us_map)  # these are also correct British words
    assert uk_map["organise"] == ("organize", "ize")
    assert uk_map["colour"] == ("color", "other")


def test_ai_tools_list():
    tools = ai_tools()
    assert "ChatGPT" in tools["OpenAI"] and "Claude" in tools["Anthropic"]


def test_ai_reference_needs_developer_or_prompt():
    assert ai_reference("OpenAI. ChatGPT. Prompt: hi. https://chatgpt.com/x [accessed 01.01.2026.]")
    assert ai_reference("ChatGPT 4o. Prompt: summarise. https://chatgpt.com/x") == "OpenAI"
    # An author called Claude is not the AI tool.
    assert ai_reference("Claude, A. (2020). A study of bridges. Demo Press.") is None
