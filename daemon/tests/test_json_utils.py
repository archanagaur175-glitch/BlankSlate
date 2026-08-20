"""Tests for JSON extraction utilities."""

from blankslate.util.json import extract_json, strip_code_fences


def test_extract_json_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_surrounding_text():
    text = 'Sure, here is the result: {"plan": ["a", "b"]} hope this helps'
    assert extract_json(text) == {"plan": ["a", "b"]}


def test_extract_json_inside_code_fence():
    text = '```json\n{"tools": ["open_url"]}\n```'
    assert extract_json(text) == {"tools": ["open_url"]}


def test_extract_json_balanced_braces_in_strings():
    text = '{"msg": "contains { brace", "n": 2}'
    assert extract_json(text) == {"msg": "contains { brace", "n": 2}


def test_extract_json_array():
    assert extract_json('[1, 2, 3]') == [1, 2, 3]


def test_extract_json_none_when_invalid():
    assert extract_json("no json here") is None
    assert extract_json("") is None


def test_strip_code_fences():
    assert strip_code_fences("```json\n{}\n```") == "{}"
    assert strip_code_fences("nope") == "nope"