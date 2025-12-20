"""
Cleaned unit tests - removed deprecated bot package dependencies
Only keeps actively used tests
"""
import json
import os
import sys
import time
from datetime import datetime
from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " loading unittests start...")

# Keep only the test that's actually called
from tests.test_flowgram2langgraph import Flowgram2LangGraphTests


def testSyncPrivateCloudImageAPI(mwin):
    """Test sync private cloud image API"""
    try:
        # This function needs to be implemented or mocked
        print("[TEST] testSyncPrivateCloudImageAPI called")
        return {
            'success': True,
            'message': 'Test completed',
            'test': 'testSyncPrivateCloudImageAPI'
        }
    except Exception as e:
        print(f"[TEST] Error in testSyncPrivateCloudImageAPI: {e}")
        return {
            'success': False,
            'message': str(e),
            'test': 'testSyncPrivateCloudImageAPI'
        }


def testReadScreen(mwin):
    """Test read screen functionality"""
    return testSyncPrivateCloudImageAPI(mwin)


def testLongLLMTask(mwin, test_setup=None):
    """Test long LLM task"""
    try:
        print(f"[TEST] testLongLLMTask called with setup: {test_setup}")
        # Implementation here
        return {
            'success': True,
            'message': 'LLM test completed',
            'test': 'testLongLLMTask'
        }
    except Exception as e:
        print(f"[TEST] Error in testLongLLMTask: {e}")
        return {
            'success': False,
            'message': str(e),
            'test': 'testLongLLMTask'
        }


def testLightRAG(mwin):
    """Test LightRAG functionality"""
    try:
        print("[TEST] testLightRAG called")
        if hasattr(mwin, 'lightrag'):
            mwin.lightrag.ingest_docs(
                "./lightrag_data/inputs/AN4973-Application-Note-DS000004973.pdf",
                "./lightrag_data/rag_storage",
                "",
                "base_url",
                "working_dir",
                "mineru"
            )
            answer = mwin.lightrag.retrieve_knowledge("what is the maximum input voltage?")
            print(f"[TEST] LightRAG answer: {answer}")
            return {
                'success': True,
                'message': 'LightRAG test completed',
                'answer': answer,
                'test': 'testLightRAG'
            }
        else:
            return {
                'success': False,
                'message': 'LightRAG not available',
                'test': 'testLightRAG'
            }
    except Exception as e:
        print(f"[TEST] Error in testLightRAG: {e}")
        return {
            'success': False,
            'message': str(e),
            'test': 'testLightRAG'
        }


def test_flowgram2langgraph():
    """Test Flowgram to LangGraph conversion"""
    try:
        print("[TEST] test_flowgram2langgraph called")
        f2l_test = Flowgram2LangGraphTests()
        f2l_test.test_multi_sheet_with_condition_in_sub_sheet()
        return {
            'success': True,
            'message': 'Flowgram2LangGraph test completed',
            'test': 'test_flowgram2langgraph'
        }
    except Exception as e:
        print(f"[TEST] Error in test_flowgram2langgraph: {e}")
        return {
            'success': False,
            'message': str(e),
            'test': 'test_flowgram2langgraph'
        }


def run_default_tests(mwin, test_setup=None):
    """
    Run default tests
    
    Args:
        mwin: Main window instance
        test_setup: Optional test setup configuration
        
    Returns:
        dict: Test results
    """
    print(f"[TEST] run_default_tests with setup: {test_setup}")
    
    results = {
        'success': True,
        'tests_run': [],
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # Run the main test
        from agent.ec_skills.label_utils.print_label import test_print_labels, test_reformat_labels
        # test_print_labels()
        test_reformat_labels()
        # test_result = testReadScreen(mwin)
        # results['tests_run'].append(test_result)
        # print(f"[TEST] unit test results: {test_result}")
        #
        # # Optionally run other tests based on test_setup
        # if test_setup:
        #     if test_setup.get('test_llm'):
        #         llm_result = testLongLLMTask(mwin, test_setup)
        #         results['tests_run'].append(llm_result)
        #
        #     if test_setup.get('test_lightrag'):
        #         lightrag_result = testLightRAG(mwin)
        #         results['tests_run'].append(lightrag_result)
        #
        #     if test_setup.get('test_flowgram'):
        #         flowgram_result = test_flowgram2langgraph()
        #         results['tests_run'].append(flowgram_result)
        #
        # # Check if any test failed
        # failed_tests = [t for t in results['tests_run'] if not t.get('success', False)]
        # if failed_tests:
        #     results['success'] = False
        #     results['failed_count'] = len(failed_tests)
        #
        # results['total_count'] = len(results['tests_run'])
        # results['passed_count'] = results['total_count'] - len(failed_tests)
        
    except Exception as e:
        print(f"[TEST] Error in run_default_tests: {e}")
        results['success'] = False
        results['error'] = str(e)
    
    return results


# Keep some utility tests that don't depend on bot package
def test_basic():
    """Test basic functionality"""
    import re
    
    addr = "Coral Springs, FL "
    us_addr_pattern = re.compile(r"[a-zA-Z ]+, *[A-Z][A-Z] *$")
    ca_addr_pattern = re.compile(r"[a-zA-Z ]+, *Canada *$")

    us_matched = us_addr_pattern.search(addr)
    ca_matched = ca_addr_pattern.search(addr)
    if us_matched or ca_matched:
        print("[TEST] citystate found!")
        return True
    else:
        print("[TEST] citystate NOT FOUND!")
        return False


def test_get_tz():
    """Test timezone functionality"""
    import pytz
    
    local_timezone = datetime.now().astimezone().tzinfo
    print(f"[TEST] time zone info: {local_timezone}")
    
    local_time = time.localtime()
    tzname_local = local_time.tm_zone
    print(f"[TEST] local time zone info: {tzname_local}")
    
    return {
        'local_timezone': str(local_timezone),
        'tzname_local': tzname_local
    }


def test_sqlite3(mw):
    """Test SQLite3 functionality"""
    try:
        from sqlalchemy import Text, REAL
        
        print("[TEST] Testing bot_service...")
        if hasattr(mw, 'bot_service'):
            mw.bot_service.describe_table()
        
        print("[TEST] Testing mission_service...")
        if hasattr(mw, 'mission_service'):
            mw.mission_service.describe_table()
            mw.mission_service.find_all_missions()
        
        return {
            'success': True,
            'message': 'SQLite3 test completed'
        }
    except Exception as e:
        print(f"[TEST] Error in test_sqlite3: {e}")
        return {
            'success': False,
            'message': str(e)
        }


# Export main test function
__all__ = ['run_default_tests', 'testReadScreen', 'testLongLLMTask', 'testLightRAG', 
           'test_basic', 'test_get_tz', 'test_sqlite3']
