#!/usr/bin/env python3
"""Test the GENERIC structured data detection logic (no hardcoded keys)."""

import json

SAMPLES = [
    {
        "name": "Structured data (should SKIP)",
        "llm_result": {
            "input_type": "TEXT",
            "action": "DIALOG_COLLECT",
            "detected_url": None,
            "detected_path": None,
            "reason": "输入为纯文本内容"
        },
        "expected_skip": True
    },
    {
        "name": "Structured data - product info (should SKIP)",
        "llm_result": {
            "product_name": "iPhone 17",
            "condition": "95新",
            "is_complete": False,
            "missing_required_fields": ["price"]
        },
        "expected_skip": True
    },
    {
        "name": "Message with long text (should SHOW)",
        "llm_result": {
            "message": "已检测到输入类型为 TEXT，正在准备下一步处理..."
        },
        "expected_skip": False
    },
    {
        "name": "Plain text response (should SHOW)",
        "llm_result": {
            "text": "这是一条普通回复消息"
        },
        "expected_skip": False
    },
    {
        "name": "Content with long text (should SHOW)",
        "llm_result": {
            "content": "请告诉您的价格和商品描述分别是？这是一条很长的追问消息。"
        },
        "expected_skip": False
    },
    {
        "name": "Generic response (should SHOW - fallback)",
        "llm_result": {
            "any_other_key": "some value"
        },
        "expected_skip": False  # Only 1 field, will be json.dumps
    },
    {
        "name": "Mixed with long text (should SHOW)",
        "llm_result": {
            "result": "这是处理结果，长文本内容用于显示给用户",
            "status": "success"
        },
        "expected_skip": False
    },
]

def detect_structured_data(llm_result):
    """Generic detection - no hardcoded field names."""
    if not isinstance(llm_result, dict):
        return False

    _display_keys = {"message", "text", "content", "response", "reply", "answer",
                     "next_prompt", "clarification_text", "casual_chat_response"}
    _has_display_key = any(k in llm_result for k in _display_keys)

    if _has_display_key:
        return False  # Has display key, don't skip

    # Count simple fields vs complex fields
    _simple_count = 0
    _total_count = 0
    _has_long_text = False
    for k, v in llm_result.items():
        _total_count += 1
        if isinstance(v, (str, int, float, bool, type(None))):
            _simple_count += 1
            if isinstance(v, str) and len(v) > 50:
                _has_long_text = True

    # If mostly simple fields (>=70%) and many fields (>3), likely structured data
    _is_structured = (
        _total_count > 3 and
        (_simple_count / max(_total_count, 1) >= 0.7) and
        not _has_long_text
    )

    return _is_structured

print("=" * 80)
print("TESTING: GENERIC structured data detection (no hardcoded keys)")
print("=" * 80)

all_passed = True
for sample in SAMPLES:
    name = sample["name"]
    llm_result = sample["llm_result"]
    expected_skip = sample["expected_skip"]

    is_structured = detect_structured_data(llm_result)
    actual_skip = is_structured

    passed = actual_skip == expected_skip
    if not passed:
        all_passed = False

    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n{status} {name}:")
    print(f"  Keys: {list(llm_result.keys())}")
    print(f"  Expected skip: {expected_skip}, Actual: {actual_skip}")

print("\n" + "=" * 80)
if all_passed:
    print("ALL TESTS PASSED ✓")
else:
    print("SOME TESTS FAILED ✗")
print("=" * 80)
