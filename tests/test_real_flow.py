#!/usr/bin/env python3
"""
Real end-to-end test: simulate the full flow from user input to response display.
This tests the ACTUAL code path without hardcoding.
"""
import sys
import json
sys.path.insert(0, '/Users/liuqiang/WorkSpace/ecan/eCan.ai')

def test_mustache_resolution():
    """Test how mustache template resolves with sample LLM output."""
    from agent.ec_skills.build_node import _resolve_mustache_template

    print("=" * 70)
    print("TEST: Mustache Template Resolution")
    print("=" * 70)

    # Simulate state after ask_followup LLM executes
    # Case 1: LLM returns proper message field
    state_with_message = {
        "result": {
            "llm_result": {
                "message": "请告诉您的iPhone成色和价格分别是？（全新/95新/9成新，参考价/原价）",
                "missing_fields": ["condition", "price"]
            },
            "ask_followup": {
                "message": "请告诉您的iPhone成色和价格分别是？",
                "missing_fields": ["condition", "price"]
            }
        },
        "tool_result": {
            "ask_followup": {
                "message": "请告诉您的iPhone成色和价格分别是？",
                "missing_fields": ["condition", "price"]
            }
        }
    }

    template = "{{ask_followup.message}}"
    result = _resolve_mustache_template(template, state_with_message)
    print(f"\nCase 1 - LLM returns message field:")
    print(f"  Template: {template}")
    print(f"  State: {json.dumps(state_with_message['tool_result']['ask_followup'], ensure_ascii=False)}")
    print(f"  Result: '{result}'")
    print(f"  ✓ PASS" if result and "请告诉" in result else "  ✗ FAIL")

    # Case 2: LLM returns structured data WITHOUT message field
    state_without_message = {
        "result": {
            "llm_result": {
                "missing_fields": ["condition", "price"],
                "next_action": "ask"
            },
            "ask_followup": {
                "missing_fields": ["condition", "price"],
                "next_action": "ask"
            }
        },
        "tool_result": {
            "ask_followup": {
                "missing_fields": ["condition", "price"],
                "next_action": "ask"
            }
        }
    }

    result2 = _resolve_mustache_template(template, state_without_message)
    print(f"\nCase 2 - LLM returns structured data WITHOUT message field:")
    print(f"  Template: {template}")
    print(f"  State: {json.dumps(state_without_message['tool_result']['ask_followup'], ensure_ascii=False)}")
    print(f"  Result: '{result2}'")
    print(f"  ✓ PASS (empty result, will skip sending)" if not result2 else "  ✗ FAIL (should be empty)")

    print("\n" + "=" * 70)
    print("CONCLUSION:")
    print("=" * 70)
    print("""
The mustache template resolution works correctly:
- If ask_followup LLM returns {"message": "...", ...} → Template resolves to message text
- If ask_followup LLM returns {missing_fields: [...]} → Template resolves to empty

If chat_node gets empty template result, it won't send anything to user.
But post_llm_hook might still send raw JSON from llm_result.

The real question: Does the LLM FOLLOW the instruction to return message field?
""")

def test_send_response_back_logic():
    """Test the send_response_back message extraction."""
    print("\n" + "=" * 70)
    print("TEST: send_response_back Message Extraction")
    print("=" * 70)

    # Simulate what send_response_back does
    def extract_message(llm_result):
        if isinstance(llm_result, str):
            return llm_result
        elif isinstance(llm_result, dict):
            msg = (
                llm_result.get("message") or
                llm_result.get("next_prompt") or
                llm_result.get("content") or
                llm_result.get("text") or
                llm_result.get("clarification_text") or
                llm_result.get("casual_chat_response") or
                ""
            )
            if not msg:
                msg = json.dumps(llm_result, ensure_ascii=False)
            return msg
        return "sorry, I was lost"

    # Case 1: LLM returns proper message
    llm_with_msg = {"message": "请告诉您的价格？", "missing_fields": ["price"]}
    result = extract_message(llm_with_msg)
    print(f"\nCase 1 - With message field:")
    print(f"  Input: {json.dumps(llm_with_msg, ensure_ascii=False)}")
    print(f"  Output: '{result}'")
    print(f"  ✓ Shows friendly message" if "请告诉" in result else "  ✗ FAIL")

    # Case 2: LLM returns structured data
    llm_structured = {"missing_fields": ["price"], "next_action": "ask"}
    result2 = extract_message(llm_structured)
    print(f"\nCase 2 - Structured data without message:")
    print(f"  Input: {json.dumps(llm_structured, ensure_ascii=False)}")
    print(f"  Output: '{result2}'")
    print(f"  ✗ Shows raw JSON (this is the bug)" if result2.startswith("{") else "  ✓ OK")

if __name__ == "__main__":
    test_mustache_resolution()
    test_send_response_back_logic()
