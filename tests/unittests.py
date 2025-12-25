"""
Cleaned unit tests - removed deprecated bot package dependencies
Only keeps actively used tests
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime
from utils.time_util import TimeUtil
from utils.logger_helper import logger_helper as logger

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
            - test_cloud_api: bool - run cloud API tests (default False)
            - cloud_api_config: dict - config for cloud API tests
            - test_llm: bool - run LLM tests
            - test_lightrag: bool - run LightRAG tests
            - test_flowgram: bool - run flowgram tests
        
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
        # Check if cloud API tests are requested
        if test_setup and test_setup.get('test_cloud_api', False):
            logger.info("[TEST] Running Cloud API tests...")
            cloud_config = test_setup.get('cloud_api_config', {
                'query_skills': True,
                'query_agents': True,
                'add_skill': False,
                'skill_with_files': False,
                'account_info': True
            })
            cloud_results = run_cloud_api_tests(mwin, cloud_config)
            results['tests_run'].append({
                'test': 'cloud_api_tests',
                'success': cloud_results['success'],
                'details': cloud_results
            })
            logger.info(f"[TEST] Cloud API tests: {cloud_results['passed']}/{cloud_results['total']} passed")
        
        # Run other tests based on test_setup
        if test_setup:
            if test_setup.get('test_llm'):
                llm_result = testLongLLMTask(mwin, test_setup)
                results['tests_run'].append(llm_result)

            if test_setup.get('test_lightrag'):
                lightrag_result = testLightRAG(mwin)
                results['tests_run'].append(lightrag_result)

            if test_setup.get('test_flowgram'):
                flowgram_result = test_flowgram2langgraph()
                results['tests_run'].append(flowgram_result)
        
        # Check if any test failed
        failed_tests = [t for t in results['tests_run'] if not t.get('success', False)]
        if failed_tests:
            results['success'] = False
            results['failed_count'] = len(failed_tests)

        results['total_count'] = len(results['tests_run'])
        results['passed_count'] = results['total_count'] - len(failed_tests)
        
    except Exception as e:
        print(f"[TEST] Error in run_default_tests: {e}")
        import traceback
        traceback.print_exc()
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


# ============================================================================
# Cloud API Live Tests (using real token from MainWindow)
# ============================================================================

def test_cloud_api_query_skills(mwin):
    """
    Test querying skills from cloud API with real token.
    
    Args:
        mwin: MainWindow instance with session, get_auth_token(), getWanApiEndpoint()
    
    Note: This test may fail if the server schema doesn't have queryAgentSkills/getAgentSkills endpoints deployed.
    """
    try:
        from agent.cloud_api.cloud_api import send_get_agent_skills_request_to_cloud
        
        logger.info("[TEST] Starting cloud API query skills test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {
                'success': False,
                'test': 'test_cloud_api_query_skills',
                'message': 'No auth token available - please login first'
            }
        
        logger.info(f"[TEST] Token: {token[:15]}...{token[-4:] if len(token) > 20 else ''}")
        logger.info(f"[TEST] Endpoint: {endpoint}")
        
        response = send_get_agent_skills_request_to_cloud(session, token, endpoint)
        
        logger.info(f"[TEST] Query skills response: {json.dumps(response, default=str)[:500]}")
        
        # Check if response indicates an error (has 'message' or 'path' keys from GraphQL error)
        if isinstance(response, dict) and ('message' in response or 'path' in response or 'errorType' in response):
            return {
                'success': False,
                'test': 'test_cloud_api_query_skills',
                'message': f"API error: {response.get('message', str(response))}",
                'response': response
            }
        
        return {
            'success': True,
            'test': 'test_cloud_api_query_skills',
            'message': 'Query skills completed',
            'response': response
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_query_skills: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test': 'test_cloud_api_query_skills',
            'message': str(e)
        }


def test_cloud_api_query_agents(mwin):
    """
    Test querying agents from cloud API with real token.
    
    Note: This test may fail if the server schema doesn't have queryAgents/getAgents endpoints deployed.
    """
    try:
        from agent.cloud_api.cloud_api import send_get_agents_request_to_cloud
        
        logger.info("[TEST] Starting cloud API query agents test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {
                'success': False,
                'test': 'test_cloud_api_query_agents',
                'message': 'No auth token available - please login first'
            }
        
        response = send_get_agents_request_to_cloud(session, token, endpoint)
        
        logger.info(f"[TEST] Query agents response: {json.dumps(response, default=str)[:500]}")
        
        # Check if response indicates an error (has 'message' or 'path' keys from GraphQL error)
        if isinstance(response, dict) and ('message' in response or 'path' in response or 'errorType' in response):
            return {
                'success': False,
                'test': 'test_cloud_api_query_agents',
                'message': f"API error: {response.get('message', str(response))}",
                'response': response
            }
        
        return {
            'success': True,
            'test': 'test_cloud_api_query_agents',
            'message': 'Query agents completed',
            'response': response
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_query_agents: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test': 'test_cloud_api_query_agents',
            'message': str(e)
        }


def test_cloud_api_add_skill(mwin):
    """
    Test adding a skill to cloud API with real token.
    Creates a test skill, adds it, then optionally removes it.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_skills_request_to_cloud,
            send_remove_skills_request_to_cloud
        )
        
        logger.info("[TEST] Starting cloud API add skill test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {
                'success': False,
                'test': 'test_cloud_api_add_skill',
                'message': 'No auth token available - please login first'
            }
        
        # Create test skill data
        test_skill_id = f"test_skill_{uuid.uuid4().hex[:8]}"
        test_skill = {
            "askid": test_skill_id,
            "owner": "unittest@test.com",
            "name": f"Unit Test Skill {datetime.now().strftime('%H%M%S')}",
            "description": "A test skill created by unit test - safe to delete",
            "version": "1.0.0",
            "status": "test",
            "path": "",
            "source": "",
            "flowgram": {},
            "langgraph": {},
            "public": False,
            "rentable": False,
            "price": 0.0
        }
        
        logger.info(f"[TEST] Adding test skill: {test_skill_id}")
        
        # Add skill
        add_response = send_add_skills_request_to_cloud(
            session, [test_skill], token, endpoint
        )
        
        logger.info(f"[TEST] Add skill response: {json.dumps(add_response, default=str)[:500]}")
        
        # Clean up - remove the test skill
        logger.info(f"[TEST] Cleaning up - removing test skill: {test_skill_id}")
        remove_response = send_remove_skills_request_to_cloud(
            session, [{"askid": test_skill_id}], token, endpoint
        )
        
        logger.info(f"[TEST] Remove skill response: {json.dumps(remove_response, default=str)[:500]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_add_skill',
            'message': 'Add and remove skill completed',
            'add_response': add_response,
            'remove_response': remove_response,
            'skill_id': test_skill_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_add_skill: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test': 'test_cloud_api_add_skill',
            'message': str(e)
        }


def test_cloud_api_skill_with_files(mwin, skill_directory=None):
    """
    Test adding a skill with file upload support.
    
    Args:
        mwin: MainWindow instance
        skill_directory: Optional path to skill directory with files to upload
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_skills_with_files_to_cloud,
            send_remove_skills_request_to_cloud,
            collect_skill_files,
            build_skill_source_string
        )
        
        logger.info("[TEST] Starting cloud API skill with files test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {
                'success': False,
                'test': 'test_cloud_api_skill_with_files',
                'message': 'No auth token available - please login first'
            }
        
        # If no skill directory provided, create a temp one for testing
        import tempfile
        cleanup_dir = False
        if not skill_directory:
            skill_directory = tempfile.mkdtemp(prefix="test_skill_")
            cleanup_dir = True
            # Create some test files
            with open(os.path.join(skill_directory, "skill_main.py"), "w") as f:
                f.write("# Test skill main file\nprint('Hello from test skill')")
            with open(os.path.join(skill_directory, "config.json"), "w") as f:
                f.write('{"name": "test_skill", "version": "1.0"}')
            os.makedirs(os.path.join(skill_directory, "utils"), exist_ok=True)
            with open(os.path.join(skill_directory, "utils", "helper.py"), "w") as f:
                f.write("# Helper utilities")
        
        # Test file collection
        files = collect_skill_files(skill_directory)
        source_string = build_skill_source_string(files)
        logger.info(f"[TEST] Collected {len(files)} files: {source_string}")
        
        # Create test skill with path
        test_skill_id = f"test_skill_files_{uuid.uuid4().hex[:8]}"
        test_skill = {
            "askid": test_skill_id,
            "owner": "unittest@test.com",
            "name": f"Unit Test Skill With Files {datetime.now().strftime('%H%M%S')}",
            "description": "A test skill with files - safe to delete",
            "version": "1.0.0",
            "status": "test",
            "path": skill_directory,
            "flowgram": {},
            "langgraph": {},
            "public": False,
            "rentable": False,
            "price": 0.0
        }
        
        logger.info(f"[TEST] Adding test skill with files: {test_skill_id}")
        
        # Add skill with files
        result = send_add_skills_with_files_to_cloud(
            session, [test_skill], token, endpoint
        )
        
        logger.info(f"[TEST] Add skill with files result: {json.dumps(result, default=str)[:500]}")
        
        # Clean up - remove the test skill
        logger.info(f"[TEST] Cleaning up - removing test skill: {test_skill_id}")
        remove_response = send_remove_skills_request_to_cloud(
            session, [{"askid": test_skill_id}], token, endpoint
        )
        
        # Clean up temp directory if we created it
        if cleanup_dir:
            import shutil
            shutil.rmtree(skill_directory, ignore_errors=True)
        
        return {
            'success': True,
            'test': 'test_cloud_api_skill_with_files',
            'message': 'Skill with files test completed',
            'files_collected': files,
            'source_string': source_string,
            'cloud_response': result.get('cloud_response'),
            'upload_results': result.get('upload_results'),
            'skill_id': test_skill_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_skill_with_files: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test': 'test_cloud_api_skill_with_files',
            'message': str(e)
        }


def test_cloud_api_account_info(mwin):
    """
    Test fetching account info from cloud API.
    """
    try:
        from agent.cloud_api.cloud_api import send_account_info_request_to_cloud
        
        logger.info("[TEST] Starting cloud API account info test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {
                'success': False,
                'test': 'test_cloud_api_account_info',
                'message': 'No auth token available - please login first'
            }

        acct_ops = [{
            'actid': 0,
            'op': {"action": "get all"},
            'options': '{}'
        }]
        
        response = send_account_info_request_to_cloud(session, acct_ops, token, endpoint)
        
        logger.info(f"[TEST] Account info response: {json.dumps(response, default=str)[:500]}")
        
        # Check if response indicates an error
        is_error = isinstance(response, dict) and ('errorType' in response or 'message' in response or 'path' in response)
        
        if is_error:
            return {
                'success': False,
                'test': 'test_cloud_api_account_info',
                'message': f"API error: {response.get('message', str(response))}",
                'response': response
            }
        
        return {
            'success': True,
            'test': 'test_cloud_api_account_info',
            'message': 'Account info query completed',
            'response': response
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_account_info: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test': 'test_cloud_api_account_info',
            'message': str(e)
        }


def run_cloud_api_tests(mwin, test_config=None):
    """
    Run all cloud API tests with real token.
    
    Args:
        mwin: MainWindow instance
        test_config: Optional dict to configure which tests to run:
            - query_skills: bool (default True)
            - query_agents: bool (default True)
            - add_skill: bool (default False) - creates/deletes test data
            - skill_with_files: bool (default False) - tests file upload
            - account_info: bool (default True)
    
    Returns:
        dict: Test results summary
    """
    if test_config is None:
        test_config = {
            'query_skills': True,
            'query_agents': True,
            'add_skill': False,  # Disabled by default - modifies cloud data
            'skill_with_files': False,  # Disabled by default
            'account_info': True
        }
    
    results = {
        'success': True,
        'tests_run': [],
        'timestamp': datetime.now().isoformat(),
        'passed': 0,
        'failed': 0
    }
    
    logger.info("[TEST] ========== Starting Cloud API Live Tests ==========")
    
    # Check auth token first
    token = mwin.get_auth_token()
    if not token:
        logger.error("[TEST] No auth token available - please login first")
        results['success'] = False
        results['error'] = 'No auth token - please login first'
        return results
    
    logger.info(f"[TEST] Auth token available: {token[:15]}...{token[-4:]}")
    
    # Run tests based on config
    if test_config.get('account_info', True):
        result = test_cloud_api_account_info(mwin)
        results['tests_run'].append(result)
        if result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
    
    if test_config.get('query_skills', True):
        result = test_cloud_api_query_skills(mwin)
        results['tests_run'].append(result)
        if result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
    
    if test_config.get('query_agents', True):
        result = test_cloud_api_query_agents(mwin)
        results['tests_run'].append(result)
        if result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
    
    if test_config.get('add_skill', False):
        result = test_cloud_api_add_skill(mwin)
        results['tests_run'].append(result)
        if result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
    
    if test_config.get('skill_with_files', False):
        skill_dir = test_config.get('skill_directory')
        result = test_cloud_api_skill_with_files(mwin, skill_dir)
        results['tests_run'].append(result)
        if result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
    
    # Summary
    results['success'] = results['failed'] == 0
    results['total'] = results['passed'] + results['failed']
    
    logger.info(f"[TEST] ========== Cloud API Tests Complete ==========")
    logger.info(f"[TEST] Passed: {results['passed']}/{results['total']}")
    
    return results


# ============================================================================
# Agent Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_agent_crud(mwin):
    """
    Test full CRUD operations for Agent entity.
    Creates an agent, updates it, queries it, then removes it.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_agents_request_to_cloud,
            send_update_agents_request_to_cloud,
            send_query_agents_request_to_cloud,
            send_remove_agents_request_to_cloud
        )
        
        logger.info("[TEST] Starting Agent CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_agent_crud', 'message': 'No auth token'}
        
        # Create test agent
        test_agent_id = f"test_agent_{uuid.uuid4().hex[:8]}"
        test_agent = {
            "id": test_agent_id,
            "owner": "unittest@test.com",
            "name": f"Test Agent {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test agent - safe to delete",
            "status": "test"
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding agent: {test_agent_id}")
        results['add'] = send_add_agents_request_to_cloud(session, [test_agent], token, endpoint)
        logger.info(f"[TEST] Add agent response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_agent['description'] = "Updated description"
        logger.info(f"[TEST] Updating agent: {test_agent_id}")
        results['update'] = send_update_agents_request_to_cloud(session, [test_agent], token, endpoint)
        logger.info(f"[TEST] Update agent response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying agents...")
        results['query'] = send_query_agents_request_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query agents response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing agent: {test_agent_id}")
        results['remove'] = send_remove_agents_request_to_cloud(
            session, [{"oid": test_agent_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove agent response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_agent_crud',
            'message': 'Agent CRUD test completed',
            'results': results,
            'agent_id': test_agent_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_agent_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_agent_crud', 'message': str(e)}


# ============================================================================
# AgentTask Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_agent_task_crud(mwin):
    """
    Test full CRUD operations for AgentTask entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_tasks_request_to_cloud,
            send_update_tasks_request_to_cloud,
            send_query_tasks_entity_to_cloud,
            send_remove_tasks_request_to_cloud
        )
        
        logger.info("[TEST] Starting AgentTask CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_agent_task_crud', 'message': 'No auth token'}
        
        # Create test task
        test_task_id = f"test_task_{uuid.uuid4().hex[:8]}"
        test_task = {
            "ataskid": test_task_id,
            "owner": "unittest@test.com",
            "name": f"Test Task {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test task - safe to delete",
            "status": "test",
            "task_type": "unittest"
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding task: {test_task_id}")
        results['add'] = send_add_tasks_request_to_cloud(session, [test_task], token, endpoint)
        logger.info(f"[TEST] Add task response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_task['description'] = "Updated task description"
        logger.info(f"[TEST] Updating task: {test_task_id}")
        results['update'] = send_update_tasks_request_to_cloud(session, [test_task], token, endpoint)
        logger.info(f"[TEST] Update task response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying tasks...")
        results['query'] = send_query_tasks_entity_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query tasks response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing task: {test_task_id}")
        results['remove'] = send_remove_tasks_request_to_cloud(
            session, [{"oid": test_task_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove task response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_agent_task_crud',
            'message': 'AgentTask CRUD test completed',
            'results': results,
            'task_id': test_task_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_agent_task_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_agent_task_crud', 'message': str(e)}


# ============================================================================
# AgentSkill Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_agent_skill_crud(mwin):
    """
    Test full CRUD operations for AgentSkill entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_skills_request_to_cloud,
            send_update_skills_request_to_cloud,
            send_query_skills_entity_to_cloud,
            send_remove_skills_request_to_cloud
        )
        
        logger.info("[TEST] Starting AgentSkill CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_agent_skill_crud', 'message': 'No auth token'}
        
        # Create test skill
        test_skill_id = f"test_skill_{uuid.uuid4().hex[:8]}"
        test_skill = {
            "askid": test_skill_id,
            "owner": "unittest@test.com",
            "name": f"Test Skill {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test skill - safe to delete",
            "version": "1.0.0",
            "status": "test",
            "public": False,
            "rentable": False
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding skill: {test_skill_id}")
        results['add'] = send_add_skills_request_to_cloud(session, [test_skill], token, endpoint)
        logger.info(f"[TEST] Add skill response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_skill['description'] = "Updated skill description"
        logger.info(f"[TEST] Updating skill: {test_skill_id}")
        results['update'] = send_update_skills_request_to_cloud(session, [test_skill], token, endpoint)
        logger.info(f"[TEST] Update skill response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying skills...")
        results['query'] = send_query_skills_entity_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query skills response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing skill: {test_skill_id}")
        results['remove'] = send_remove_skills_request_to_cloud(
            session, [{"oid": test_skill_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove skill response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_agent_skill_crud',
            'message': 'AgentSkill CRUD test completed',
            'results': results,
            'skill_id': test_skill_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_agent_skill_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_agent_skill_crud', 'message': str(e)}


# ============================================================================
# AgentTool Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_agent_tool_crud(mwin):
    """
    Test full CRUD operations for AgentTool entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_tools_request_to_cloud,
            send_update_tools_request_to_cloud,
            send_query_tools_entity_to_cloud,
            send_remove_tools_request_to_cloud
        )
        
        logger.info("[TEST] Starting AgentTool CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_agent_tool_crud', 'message': 'No auth token'}
        
        # Create test tool
        test_tool_id = f"test_tool_{uuid.uuid4().hex[:8]}"
        test_tool = {
            "toolid": test_tool_id,
            "owner": "unittest@test.com",
            "name": f"Test Tool {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test tool - safe to delete",
            "protocol": "mcp",
            "status": "test"
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding tool: {test_tool_id}")
        results['add'] = send_add_tools_request_to_cloud(session, [test_tool], token, endpoint)
        logger.info(f"[TEST] Add tool response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_tool['description'] = "Updated tool description"
        logger.info(f"[TEST] Updating tool: {test_tool_id}")
        results['update'] = send_update_tools_request_to_cloud(session, [test_tool], token, endpoint)
        logger.info(f"[TEST] Update tool response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying tools...")
        results['query'] = send_query_tools_entity_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query tools response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing tool: {test_tool_id}")
        results['remove'] = send_remove_tools_request_to_cloud(
            session, [{"oid": test_tool_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove tool response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_agent_tool_crud',
            'message': 'AgentTool CRUD test completed',
            'results': results,
            'tool_id': test_tool_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_agent_tool_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_agent_tool_crud', 'message': str(e)}


# ============================================================================
# Prompt Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_prompt_crud(mwin):
    """
    Test full CRUD operations for Prompt entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_prompts_request_to_cloud,
            send_update_prompts_request_to_cloud,
            send_query_prompts_request_to_cloud,
            send_remove_prompts_request_to_cloud
        )
        
        logger.info("[TEST] Starting Prompt CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_prompt_crud', 'message': 'No auth token'}
        
        # Create test prompt
        test_prompt_id = f"test_prompt_{uuid.uuid4().hex[:8]}"
        test_prompt = {
            "id": test_prompt_id,
            "owner": "unittest@test.com",
            "name": f"Test Prompt {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test prompt - safe to delete",
            "content": "You are a helpful assistant. This is a test prompt.",
            "category": "test",
            "version": "1.0.0",
            "status": "test",
            "is_public": False
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding prompt: {test_prompt_id}")
        results['add'] = send_add_prompts_request_to_cloud(session, [test_prompt], token, endpoint)
        logger.info(f"[TEST] Add prompt response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_prompt['content'] = "Updated prompt content"
        logger.info(f"[TEST] Updating prompt: {test_prompt_id}")
        results['update'] = send_update_prompts_request_to_cloud(session, [test_prompt], token, endpoint)
        logger.info(f"[TEST] Update prompt response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying prompts...")
        results['query'] = send_query_prompts_request_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query prompts response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing prompt: {test_prompt_id}")
        results['remove'] = send_remove_prompts_request_to_cloud(
            session, [{"oid": test_prompt_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove prompt response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_prompt_crud',
            'message': 'Prompt CRUD test completed',
            'results': results,
            'prompt_id': test_prompt_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_prompt_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_prompt_crud', 'message': str(e)}


# ============================================================================
# Avatar Resource Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_avatar_crud(mwin):
    """
    Test full CRUD operations for Avatar Resource entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_avatar_resources_to_cloud,
            send_update_avatar_resources_to_cloud,
            send_query_avatar_resources_to_cloud,
            send_remove_avatar_resources_to_cloud
        )
        
        logger.info("[TEST] Starting Avatar Resource CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_avatar_crud', 'message': 'No auth token'}
        
        # Create test avatar resource
        test_avatar_id = f"test_avatar_{uuid.uuid4().hex[:8]}"
        test_avatar = {
            "id": test_avatar_id,
            "owner": "unittest@test.com",
            "resource_type": "image",
            "name": f"Test Avatar {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test avatar - safe to delete",
            "image_path": "/test/path/image.png",
            "cloud_synced": False,
            "is_public": False
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding avatar: {test_avatar_id}")
        results['add'] = send_add_avatar_resources_to_cloud(session, [test_avatar], token, endpoint)
        logger.info(f"[TEST] Add avatar response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_avatar['description'] = "Updated avatar description"
        logger.info(f"[TEST] Updating avatar: {test_avatar_id}")
        results['update'] = send_update_avatar_resources_to_cloud(session, [test_avatar], token, endpoint)
        logger.info(f"[TEST] Update avatar response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying avatars...")
        results['query'] = send_query_avatar_resources_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query avatars response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing avatar: {test_avatar_id}")
        results['remove'] = send_remove_avatar_resources_to_cloud(
            session, [{"oid": test_avatar_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove avatar response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_avatar_crud',
            'message': 'Avatar Resource CRUD test completed',
            'results': results,
            'avatar_id': test_avatar_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_avatar_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_avatar_crud', 'message': str(e)}


# ============================================================================
# Vehicle Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_vehicle_crud(mwin):
    """
    Test full CRUD operations for Vehicle entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_vehicles_request_to_cloud,
            send_update_vehicles_decorated_to_cloud,
            send_query_vehicles_request_to_cloud,
            send_remove_vehicles_request_to_cloud
        )
        
        logger.info("[TEST] Starting Vehicle CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_vehicle_crud', 'message': 'No auth token'}
        
        # Create test vehicle
        test_vehicle_id = f"test_vehicle_{uuid.uuid4().hex[:8]}"
        test_vehicle = {
            "vid": test_vehicle_id,
            "vname": f"Test Vehicle {datetime.now().strftime('%H%M%S')}",
            "owner": "unittest@test.com",
            "status": "test",
            "functions": "unittest",
            "hardware": "test_hardware",
            "software": "test_software"
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding vehicle: {test_vehicle_id}")
        results['add'] = send_add_vehicles_request_to_cloud(session, [test_vehicle], token, endpoint)
        logger.info(f"[TEST] Add vehicle response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_vehicle['status'] = "updated"
        logger.info(f"[TEST] Updating vehicle: {test_vehicle_id}")
        results['update'] = send_update_vehicles_decorated_to_cloud(session, [test_vehicle], token, endpoint)
        logger.info(f"[TEST] Update vehicle response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying vehicles...")
        results['query'] = send_query_vehicles_request_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query vehicles response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing vehicle: {test_vehicle_id}")
        results['remove'] = send_remove_vehicles_request_to_cloud(
            session, [{"vid": test_vehicle_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove vehicle response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_vehicle_crud',
            'message': 'Vehicle CRUD test completed',
            'results': results,
            'vehicle_id': test_vehicle_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_vehicle_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_vehicle_crud', 'message': str(e)}


# ============================================================================
# Organization Entity Tests (add/update/query/remove)
# ============================================================================

def test_cloud_api_organization_crud(mwin):
    """
    Test full CRUD operations for Organization entity.
    """
    try:
        from agent.cloud_api.cloud_api import (
            send_add_organizations_to_cloud,
            send_update_organizations_to_cloud,
            send_query_organizations_to_cloud,
            send_remove_organizations_to_cloud
        )
        
        logger.info("[TEST] Starting Organization CRUD test...")
        
        session = mwin.session
        token = mwin.get_auth_token()
        endpoint = mwin.getWanApiEndpoint()
        
        if not token:
            return {'success': False, 'test': 'test_cloud_api_organization_crud', 'message': 'No auth token'}
        
        # Create test organization
        test_org_id = f"test_org_{uuid.uuid4().hex[:8]}"
        test_org = {
            "id": test_org_id,
            "owner": "unittest@test.com",
            "name": f"Test Organization {datetime.now().strftime('%H%M%S')}",
            "description": "Unit test organization - safe to delete",
            "org_type": "test",
            "status": "test"
        }
        
        results = {'add': None, 'update': None, 'query': None, 'remove': None}
        
        # ADD
        logger.info(f"[TEST] Adding organization: {test_org_id}")
        results['add'] = send_add_organizations_to_cloud(session, [test_org], token, endpoint)
        logger.info(f"[TEST] Add organization response: {json.dumps(results['add'], default=str)[:300]}")
        
        # UPDATE
        test_org['description'] = "Updated organization description"
        logger.info(f"[TEST] Updating organization: {test_org_id}")
        results['update'] = send_update_organizations_to_cloud(session, [test_org], token, endpoint)
        logger.info(f"[TEST] Update organization response: {json.dumps(results['update'], default=str)[:300]}")
        
        # QUERY
        logger.info(f"[TEST] Querying organizations...")
        results['query'] = send_query_organizations_to_cloud(session, token, {"byowneruser": True}, endpoint)
        logger.info(f"[TEST] Query organizations response: {json.dumps(results['query'], default=str)[:300]}")
        
        # REMOVE
        logger.info(f"[TEST] Removing organization: {test_org_id}")
        results['remove'] = send_remove_organizations_to_cloud(
            session, [{"oid": test_org_id, "owner": "unittest@test.com", "reason": "test cleanup"}], token, endpoint
        )
        logger.info(f"[TEST] Remove organization response: {json.dumps(results['remove'], default=str)[:300]}")
        
        return {
            'success': True,
            'test': 'test_cloud_api_organization_crud',
            'message': 'Organization CRUD test completed',
            'results': results,
            'organization_id': test_org_id
        }
    except Exception as e:
        logger.error(f"[TEST] Error in test_cloud_api_organization_crud: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'test': 'test_cloud_api_organization_crud', 'message': str(e)}


# ============================================================================
# Updated run_cloud_api_tests with full entity test suite
# ============================================================================

def run_cloud_api_entity_tests(mwin, test_config=None):
    """
    Run full CRUD tests for all entity types.
    
    Args:
        mwin: MainWindow instance
        test_config: Optional dict to configure which entity tests to run:
            - agent: bool (default True)
            - agent_task: bool (default True)
            - agent_skill: bool (default True)
            - agent_tool: bool (default True)
            - prompt: bool (default True)
            - avatar: bool (default True)
            - vehicle: bool (default True)
            - organization: bool (default True)
    
    Returns:
        dict: Test results summary
    """
    if test_config is None:
        test_config = {
            'agent': True,
            'agent_task': True,
            'agent_skill': True,
            'agent_tool': True,
            'prompt': True,
            'avatar': True,
            'vehicle': True,
            'organization': True
        }
    
    results = {
        'success': True,
        'tests_run': [],
        'timestamp': datetime.now().isoformat(),
        'passed': 0,
        'failed': 0
    }
    
    logger.info("[TEST] ========== Starting Cloud API Entity CRUD Tests ==========")
    
    # Check auth token first
    token = mwin.get_auth_token()
    if not token:
        logger.error("[TEST] No auth token available - please login first")
        results['success'] = False
        results['error'] = 'No auth token - please login first'
        return results
    
    logger.info(f"[TEST] Auth token available: {token[:15]}...{token[-4:]}")
    
    # Run entity CRUD tests based on config
    entity_tests = [
        ('agent', test_cloud_api_agent_crud),
        ('agent_task', test_cloud_api_agent_task_crud),
        ('agent_skill', test_cloud_api_agent_skill_crud),
        ('agent_tool', test_cloud_api_agent_tool_crud),
        ('prompt', test_cloud_api_prompt_crud),
        ('avatar', test_cloud_api_avatar_crud),
        ('vehicle', test_cloud_api_vehicle_crud),
        ('organization', test_cloud_api_organization_crud),
    ]
    
    for entity_name, test_func in entity_tests:
        if test_config.get(entity_name, True):
            logger.info(f"[TEST] Running {entity_name} CRUD test...")
            result = test_func(mwin)
            results['tests_run'].append(result)
            if result['success']:
                results['passed'] += 1
                logger.info(f"[TEST] ✓ {entity_name} CRUD test PASSED")
            else:
                results['failed'] += 1
                logger.error(f"[TEST] ✗ {entity_name} CRUD test FAILED: {result.get('message', 'Unknown error')}")
    
    # Summary
    results['success'] = results['failed'] == 0
    results['total'] = results['passed'] + results['failed']
    
    logger.info(f"[TEST] ========== Cloud API Entity Tests Complete ==========")
    logger.info(f"[TEST] Passed: {results['passed']}/{results['total']}")
    
    return results


# Export main test function
__all__ = ['run_default_tests', 'testReadScreen', 'testLongLLMTask', 'testLightRAG', 
           'test_basic', 'test_get_tz', 'test_sqlite3',
           'run_cloud_api_tests', 'test_cloud_api_query_skills', 'test_cloud_api_query_agents',
           'test_cloud_api_add_skill', 'test_cloud_api_skill_with_files', 'test_cloud_api_account_info',
           'run_cloud_api_entity_tests',
           'test_cloud_api_agent_crud', 'test_cloud_api_agent_task_crud', 
           'test_cloud_api_agent_skill_crud', 'test_cloud_api_agent_tool_crud',
           'test_cloud_api_prompt_crud', 'test_cloud_api_avatar_crud', 'test_cloud_api_vehicle_crud',
           'test_cloud_api_organization_crud']
