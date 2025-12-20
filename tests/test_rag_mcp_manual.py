"""
MCP RAG Tools Test Script

Tests the ragify and rag_query MCP tools that integrate with LightRAG.

Prerequisites:
1. LightRAG server running at http://localhost:9621 (or configured via HOST/PORT env vars)
2. eCan application running with MCP server at http://localhost:4668

Usage:
    python tests/test_rag_mcp_manual.py
"""

import asyncio
import os
import sys
import time

# Add project root to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.mcp.local_client import mcp_call_tool


def check_result(result) -> bool:
    """Check if MCP call result indicates success."""
    if result is None:
        return False
    # Handle dict result (error case from mcp_call_tool)
    if isinstance(result, dict):
        return not result.get("isError", False)
    # Handle CallToolResult object
    if hasattr(result, 'isError'):
        return not result.isError
    return True


async def test_ragify_with_file():
    """Test ragify tool with file upload."""
    print("\n" + "="*60)
    print("[TEST 1] ragify - File Upload")
    print("="*60)
    
    # Create test file
    test_file = "test_rag_doc.txt"
    with open(test_file, "w") as f:
        f.write("LightRAG is a Retrieval-Augmented Generation system. "
                "It supports graph-based indexing and retrieval. "
                "LightRAG uses knowledge graphs to enhance RAG capabilities.")
    
    test_file_path = os.path.abspath(test_file)
    print(f"📝 Created test file: {test_file_path}")

    ragify_args = {
        "input": {
            "file_paths": [test_file_path]
        }
    }
    
    try:
        result = await mcp_call_tool("ragify", ragify_args)
        print(f"✅ Result: {result}")
        return check_result(result)
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"🧹 Cleaned up: {test_file}")


async def test_ragify_with_text():
    """Test ragify tool with direct text insertion."""
    print("\n" + "="*60)
    print("[TEST 2] ragify - Text Insert")
    print("="*60)
    
    ragify_args = {
        "input": {
            "text": "eCan.ai is an AI-powered automation platform. "
                    "It provides intelligent agents for various business tasks.",
            "file_source": "test_text_source"
        }
    }
    
    try:
        result = await mcp_call_tool("ragify", ragify_args)
        print(f"✅ Result: {result}")
        return check_result(result)
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


async def test_rag_query_basic():
    """Test rag_query tool with basic query."""
    print("\n" + "="*60)
    print("[TEST 3] rag_query - Basic Query")
    print("="*60)
    
    query_args = {
        "input": {
            "query": "What is LightRAG?",
            "mode": "mix"  # Options: local, global, hybrid, naive, mix, bypass
        }
    }
    
    try:
        result = await mcp_call_tool("rag_query", query_args)
        print(f"✅ Result: {result}")
        
        # Extract answer from result
        if check_result(result):
            # Handle CallToolResult object
            if hasattr(result, 'content') and result.content:
                text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                print(f"\n🤖 Answer: {text[:500]}...")
        return check_result(result)
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


async def test_rag_query_advanced():
    """Test rag_query tool with advanced options."""
    print("\n" + "="*60)
    print("[TEST 4] rag_query - Advanced Options")
    print("="*60)
    
    query_args = {
        "input": {
            "query": "What are the features of LightRAG?",
            "mode": "hybrid",
            "top_k": 10,
            "include_references": True,
            "response_type": "Bullet Points"
        }
    }
    
    try:
        result = await mcp_call_tool("rag_query", query_args)
        print(f"✅ Result: {result}")
        return check_result(result)
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


async def test_rag_query_with_history():
    """Test rag_query tool with conversation history."""
    print("\n" + "="*60)
    print("[TEST 5] rag_query - With Conversation History")
    print("="*60)
    
    query_args = {
        "input": {
            "query": "Can you explain more about its architecture?",
            "mode": "mix",
            "conversation_history": [
                {"role": "user", "content": "What is LightRAG?"},
                {"role": "assistant", "content": "LightRAG is a graph-based RAG system."}
            ]
        }
    }
    
    try:
        result = await mcp_call_tool("rag_query", query_args)
        print(f"✅ Result: {result}")
        return check_result(result)
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting MCP RAG Tools Test Suite")
    print("="*60)
    print("Prerequisites:")
    print("  - LightRAG server: http://localhost:9621")
    print("  - MCP server: http://localhost:4668")
    print("="*60)
    
    results = {}
    
    # Run tests
    results["ragify_file"] = await test_ragify_with_file()
    results["ragify_text"] = await test_ragify_with_text()
    
    # Wait for indexing (LightRAG processes documents asynchronously)
    print("\n⏳ Waiting 3 seconds for document indexing...")
    time.sleep(3)  # Use sync sleep to avoid cancel scope issues with anyio
    
    results["query_basic"] = await test_rag_query_basic()
    results["query_advanced"] = await test_rag_query_advanced()
    results["query_history"] = await test_rag_query_with_history()
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
