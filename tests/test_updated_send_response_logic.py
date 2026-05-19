#!/usr/bin/env python3
"""Test the UPDATED send_response_back logic with sample LLM outputs."""

import json

# Sample LLM outputs that mimic what the skill nodes might return

SAMPLES = [
    {
        "name": "input_type_detector (with message)",
        "llm_result": {
            "message": "已检测到输入类型为 TEXT，正在准备下一步处理...",
            "input_type": "TEXT",
            "action": "DIALOG_COLLECT",
        }
    },
    {
        "name": "input_type_detector (without message - should SKIP)",
        "llm_result": {
            "input_type": "TEXT",
            "action": "DIALOG_COLLECT",
            "detected_url": None,
            "detected_path": None,
            "reason": "输入为纯文本内容"
        }
    },
    {
        "name": "structured_collector (with message)",
        "llm_result": {
            "message": "已收集商品信息：iPhone 17 Pro Max，正在等待更多信息...",
            "product_name": "iPhone 17 Pro Max",
            "condition": "95新",
            "is_complete": False,
        }
    },
    {
        "name": "structured_collector (without message - should SKIP)",
        "llm_result": {
            "product_name": "iPhone 17 Pro Max",
            "condition": "95新",
            "is_complete": False,
            "missing_required_fields": ["price", "description"]
        }
    },
    {
        "name": "ask_followup (with message)",
        "llm_result": {
            "message": "请告诉您的价格和商品描述分别是？"
        }
    },
    {
        "name": "Generic response with 'text' key (should show)",
        "llm_result": {
            "text": "这是一条普通回复"
        }
    },
    {
        "name": "Generic response with 'content' key (should show)",
        "llm_result": {
            "content": "这是一条普通回复"
        }
    },
    {
        "name": "Generic response with 'response' key (should show)",
        "llm_result": {
            "response": "这是一条普通回复"
        }
    },
]

def extract_display_message(llm_result):
    """Simulate the UPDATED send_response_back logic."""
    if isinstance(llm_result, str):
        return llm_result, True
    elif isinstance(llm_result, dict):
        # Try multiple keys
        next_msg = (
            llm_result.get("message") or
            llm_result.get("next_prompt") or
            llm_result.get("content") or
            llm_result.get("text") or
            llm_result.get("clarification_text") or
            llm_result.get("casual_chat_response") or
            ""
        )
        if not next_msg:
            # Check if this is structured data without displayable text
            _data_keys = {"input_type", "action", "detected_url", "detected_path", "reason",
                          "product_name", "size", "condition", "is_complete", "missing_required_fields",
                          "next_action", "missing_fields", "platforms", "competitors",
                          "collected", "pending", "brand", "category", "model", "storage", "color",
                          "gender", "material", "platform", "price", "description", "images",
                          "execution_status", "final", "result", "extracted_content"}
            _has_display_key = any(k in llm_result for k in ["message", "text", "content", "response", "reply", "answer"])
            _has_data_key = any(k in llm_result for k in _data_keys)
            if _has_data_key and not _has_display_key:
                # This is structured data without displayable text - skip sending
                return "", False  # Empty = skip
            else:
                # Fallback: convert to JSON for display
                return json.dumps(llm_result, ensure_ascii=False), True
        return next_msg, True
    else:
        return "sorry, I was lost, could you rephrase your question?", True

print("=" * 80)
print("TESTING: UPDATED send_response_back message extraction logic")
print("=" * 80)

all_passed = True
for sample in SAMPLES:
    name = sample["name"]
    llm_result = sample["llm_result"]

    result, should_show = extract_display_message(llm_result)

    is_json = result.strip().startswith("{") and result.strip().endswith("}")
    will_show = should_show and bool(result.strip())

    # Determine expected behavior
    is_structured = any(k in llm_result for k in ["input_type", "product_name", "is_complete"])
    has_display_key = any(k in llm_result for k in ["message", "text", "content", "response"])

    if is_structured and not has_display_key:
        expected = "SKIP (structured data)"
        expected_skip = True
    else:
        expected = "SHOW"
        expected_skip = False

    actual_skip = not will_show
    passed = actual_skip == expected_skip

    if not passed:
        all_passed = False

    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n{status} {name}:")
    print(f"  Input keys: {list(llm_result.keys())}")
    print(f"  Result: {result[:60]}..." if result else "  Result: (empty)")
    print(f"  Will show: {will_show}, Expected: {expected}")

print("\n" + "=" * 80)
if all_passed:
    print("ALL TESTS PASSED ✓")
else:
    print("SOME TESTS FAILED ✗")
print("=" * 80)
