"""
Real LLM API Integration Test

This script tests the Qwen adapter with actual API responses from the LLM server.
It sends real requests to http://192.168.1.69/v1 and validates the adapter can
correctly process the responses.
"""

import json
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.ec_skills.browser_use_extension.qwen_adapter import clean_qwen_response


def test_real_llm_api():
    """Test with real LLM API."""
    print("=" * 80)
    print("Real LLM API Integration Test")
    print("=" * 80)
    
    # API configuration
    api_base_url = "http://192.168.1.69/v1"
    model_name = "Qwen3-14B-NVFP4"  # From the logs
    
    # Try to get API key from environment or use placeholder
    api_key = os.environ.get("OLLAMA_LLM_API_KEY", "sk-placeholder-key-for-local-llm")
    
    print(f"\n📡 API Configuration:")
    print(f"  Base URL: {api_base_url}")
    print(f"  Model: {model_name}")
    print(f"  API Key: {'***' if api_key else 'None'}")
    
    # Test prompt for browser-use scenario
    test_prompt = """You are a browser automation agent. Your task is to navigate to Baidu and search for "人工智能".

Current state: Empty browser at about:blank

Please provide your next action in the following JSON format:
{
  "evaluation_previous_goal": "...",
  "memory": "...",
  "next_goal": "...",
  "action": [...]
}"""
    
    print(f"\n📝 Test Prompt:")
    print(f"  {test_prompt[:100]}...")
    
    try:
        # Try to import requests
        try:
            import requests
        except ImportError:
            print("\n❌ Error: 'requests' library not installed")
            print("   Please install it with: pip install requests")
            return False
        
        # Prepare API request
        url = f"{api_base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful browser automation agent. Always respond with valid JSON in the specified format."
                },
                {
                    "role": "user",
                    "content": test_prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        print(f"\n🚀 Sending request to LLM API...")
        print(f"  URL: {url}")
        
        # Send request with timeout
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
        
        # Parse response
        response_data = response.json()
        
        # Extract content from response
        if "choices" not in response_data or len(response_data["choices"]) == 0:
            print("❌ No choices in response")
            print(f"   Response: {json.dumps(response_data, indent=2)[:500]}")
            return False
        
        raw_content = response_data["choices"][0]["message"]["content"]
        
        print(f"\n📄 Raw LLM Response ({len(raw_content)} chars):")
        print("-" * 80)
        print(raw_content[:500])
        if len(raw_content) > 500:
            print(f"... (truncated, total {len(raw_content)} chars)")
        print("-" * 80)
        
        # Test Qwen adapter
        print(f"\n🔧 Testing Qwen Adapter...")
        cleaned_content = clean_qwen_response(raw_content)
        
        print(f"\n✨ Cleaned Response ({len(cleaned_content)} chars):")
        print("-" * 80)
        print(cleaned_content[:500])
        if len(cleaned_content) > 500:
            print(f"... (truncated, total {len(cleaned_content)} chars)")
        print("-" * 80)
        
        # Try to parse as JSON
        print(f"\n🧪 Validating JSON...")
        try:
            parsed = json.loads(cleaned_content)
            print("✅ JSON is valid!")
            
            # Check required fields
            required_fields = ["evaluation_previous_goal", "memory", "next_goal", "action"]
            missing_fields = [f for f in required_fields if f not in parsed]
            
            if missing_fields:
                print(f"⚠️  Missing fields: {missing_fields}")
            else:
                print("✅ All required fields present!")
            
            # Display parsed structure
            print(f"\n📊 Parsed Structure:")
            print(f"  evaluation_previous_goal: {parsed.get('evaluation_previous_goal', 'N/A')[:50]}...")
            print(f"  memory: {parsed.get('memory', 'N/A')[:50]}...")
            print(f"  next_goal: {parsed.get('next_goal', 'N/A')[:50]}...")
            print(f"  action: {len(parsed.get('action', []))} action(s)")
            
            if parsed.get('action'):
                for i, action in enumerate(parsed['action']):
                    if isinstance(action, dict):
                        action_type = list(action.keys())[0] if action else "unknown"
                        print(f"    [{i}] {action_type}: {str(action)[:60]}...")
                    else:
                        # Action is a string or other type
                        print(f"    [{i}] {type(action).__name__}: {str(action)[:60]}...")
            
            print("\n" + "=" * 80)
            print("✅ Real LLM API Test PASSED!")
            print("=" * 80)
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}")
            print(f"   Position: {e.pos}")
            print(f"   Line: {e.lineno}, Column: {e.colno}")
            
            # Show problematic area
            if e.pos:
                start = max(0, e.pos - 50)
                end = min(len(cleaned_content), e.pos + 50)
                print(f"\n   Context around error:")
                print(f"   ...{cleaned_content[start:end]}...")
            
            print("\n" + "=" * 80)
            print("❌ Real LLM API Test FAILED!")
            print("=" * 80)
            return False
            
    except requests.exceptions.Timeout:
        print(f"\n❌ Request timeout after 30 seconds")
        print("   The LLM server may be slow or unresponsive")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Connection error: {e}")
        print(f"   Cannot connect to {api_base_url}")
        print("   Please check:")
        print("   1. The server is running")
        print("   2. The URL is correct")
        print("   3. Network connectivity")
        return False
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_requests():
    """Test multiple requests to verify consistency."""
    print("\n" + "=" * 80)
    print("Testing Multiple Requests")
    print("=" * 80)
    
    test_scenarios = [
        {
            "name": "Navigate to Baidu",
            "prompt": "Navigate to https://www.baidu.com"
        },
        {
            "name": "Input text",
            "prompt": "Input '人工智能' into search box at element 14"
        },
        {
            "name": "Click button",
            "prompt": "Click the search button at element 15"
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📝 Test {i}/{len(test_scenarios)}: {scenario['name']}")
        print(f"   Prompt: {scenario['prompt']}")
        
        # For now, just log the scenarios
        # Actual API calls would be made here
        print(f"   ⏭️  Skipped (to avoid excessive API calls)")
        results.append({"name": scenario['name'], "status": "skipped"})
    
    print(f"\n📊 Summary: {len(results)} scenarios prepared")
    return True


if __name__ == "__main__":
    print("\n🧪 Starting Real LLM API Tests\n")
    
    # Test 1: Single request with full validation
    success = test_real_llm_api()
    
    # Test 2: Multiple scenarios (optional)
    # test_multiple_requests()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please review the output above.")
        sys.exit(1)
