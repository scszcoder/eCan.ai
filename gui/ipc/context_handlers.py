"""
Context Panel IPC Handlers
Handles context-related requests from the frontend
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from utils.logger_helper import logger_helper as logger
from app_context import AppContext


def generate_test_contexts():
    """Generate test context data for UI testing"""
    now = datetime.now()
    
    contexts = [
        {
            "uid": str(uuid.uuid4()),
            "title": "Customer Support Inquiry",
            "messageCount": 5,
            "mostRecentTimestamp": (now - timedelta(minutes=5)).isoformat(),
            "mostRecentMessage": "Thank you for your help with the account issue!",
            "items": [
                {
                    "uid": str(uuid.uuid4()),
                    "type": "text",
                    "timestamp": (now - timedelta(minutes=30)).isoformat(),
                    "generator": "human",
                    "generatorName": "User",
                    "content": {
                        "message": "I'm having trouble logging into my account. Can you help?"
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "tool_call",
                    "timestamp": (now - timedelta(minutes=28)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Support Agent",
                    "content": {
                        "description": "Checking user authentication status",
                        "toolName": "check_user_auth",
                        "toolParams": {"user_id": "12345", "check_level": "full"},
                        "toolResult": {"status": "locked", "reason": "Too many failed attempts"}
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "code_execution",
                    "timestamp": (now - timedelta(minutes=25)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Support Agent",
                    "content": {
                        "description": "Unlocking user account",
                        "code": "# Reset failed login attempts\ndb.users.update_one(\n    {'user_id': '12345'},\n    {'$set': {'failed_attempts': 0, 'locked': False}}\n)",
                        "codeLanguage": "python"
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "db_access",
                    "timestamp": (now - timedelta(minutes=20)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Support Agent",
                    "content": {
                        "description": "Verified account unlock",
                        "json": {
                            "query": "SELECT * FROM users WHERE user_id = '12345'",
                            "result": {
                                "user_id": "12345",
                                "email": "user@example.com",
                                "locked": False,
                                "failed_attempts": 0
                            }
                        }
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "text",
                    "timestamp": (now - timedelta(minutes=5)).isoformat(),
                    "generator": "human",
                    "generatorName": "User",
                    "content": {
                        "message": "Thank you for your help with the account issue! I can log in now."
                    }
                }
            ],
            "isArchived": False
        },
        {
            "uid": str(uuid.uuid4()),
            "title": "API Integration Setup",
            "messageCount": 3,
            "mostRecentTimestamp": (now - timedelta(hours=2)).isoformat(),
            "mostRecentMessage": "Successfully configured the webhook endpoint",
            "items": [
                {
                    "uid": str(uuid.uuid4()),
                    "type": "text",
                    "timestamp": (now - timedelta(hours=3)).isoformat(),
                    "generator": "human",
                    "generatorName": "Developer",
                    "content": {
                        "message": "I need to set up a webhook for payment notifications"
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "api_call",
                    "timestamp": (now - timedelta(hours=2, minutes=30)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Integration Agent",
                    "content": {
                        "description": "Creating webhook endpoint",
                        "toolName": "create_webhook",
                        "toolParams": {
                            "url": "https://api.example.com/webhooks/payment",
                            "events": ["payment.success", "payment.failed"],
                            "secret": "wh_secret_abc123"
                        },
                        "toolResult": {
                            "webhook_id": "wh_xyz789",
                            "status": "active",
                            "created_at": (now - timedelta(hours=2, minutes=30)).isoformat()
                        }
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "text",
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Integration Agent",
                    "content": {
                        "message": "Successfully configured the webhook endpoint. You'll receive POST requests at https://api.example.com/webhooks/payment for payment events."
                    }
                }
            ],
            "isArchived": False
        },
        {
            "uid": str(uuid.uuid4()),
            "title": "Data Migration Task",
            "messageCount": 4,
            "mostRecentTimestamp": (now - timedelta(days=1)).isoformat(),
            "mostRecentMessage": "Migration completed: 10,000 records processed",
            "items": [
                {
                    "uid": str(uuid.uuid4()),
                    "type": "text",
                    "timestamp": (now - timedelta(days=1, hours=3)).isoformat(),
                    "generator": "human",
                    "generatorName": "Admin",
                    "content": {
                        "message": "Need to migrate user data from old database to new schema"
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "code_execution",
                    "timestamp": (now - timedelta(days=1, hours=2)).isoformat(),
                    "generator": "agent",
                    "generatorName": "Migration Agent",
                    "content": {
                        "description": "Running migration script",
                        "code": "import pandas as pd\nfrom sqlalchemy import create_engine\n\n# Connect to databases\nold_db = create_engine('postgresql://old_db')\nnew_db = create_engine('postgresql://new_db')\n\n# Read data\ndf = pd.read_sql('SELECT * FROM users', old_db)\n\n# Transform data\ndf['full_name'] = df['first_name'] + ' ' + df['last_name']\ndf = df.drop(['first_name', 'last_name'], axis=1)\n\n# Write to new database\ndf.to_sql('users_v2', new_db, if_exists='append', index=False)\nprint(f'Migrated {len(df)} records')",
                        "codeLanguage": "python"
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "system_event",
                    "timestamp": (now - timedelta(days=1, hours=1)).isoformat(),
                    "generator": "system",
                    "generatorName": "System",
                    "content": {
                        "message": "Migration progress: 5,000 / 10,000 records (50%)",
                        "json": {
                            "total": 10000,
                            "processed": 5000,
                            "failed": 0,
                            "status": "in_progress"
                        }
                    }
                },
                {
                    "uid": str(uuid.uuid4()),
                    "type": "system_event",
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "generator": "system",
                    "generatorName": "System",
                    "content": {
                        "message": "Migration completed: 10,000 records processed successfully",
                        "json": {
                            "total": 10000,
                            "processed": 10000,
                            "failed": 0,
                            "status": "completed",
                            "duration_seconds": 3600
                        }
                    }
                }
            ],
            "isArchived": False
        }
    ]
    
    return contexts


@IPCHandlerRegistry.handler('send_all_contexts')
def handle_send_all_contexts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Backend-initiated IPC to push all contexts to GUI upon init
    This is called by the backend to send initial context data to the frontend
    """
    try:
        logger.info("[Context] Sending all contexts to frontend")
        
        # For now, send test data
        # In production, this would fetch from database or backend state
        contexts = generate_test_contexts()
        
        # Push to frontend via IPC
        main_window = AppContext.get_main_window()
        if main_window:
            # Use push_to_web to send data to frontend
            main_window.push_to_web('send_all_contexts', contexts)
            logger.info(f"[Context] Pushed {len(contexts)} contexts to frontend")
        
        return create_success_response(request, {"sent": len(contexts)})
        
    except Exception as e:
        logger.error(f"[Context] Error sending contexts: {e}", exc_info=True)
        return create_error_response(request, 'SEND_CONTEXTS_ERROR', str(e))


@IPCHandlerRegistry.handler('update_contexts')
def handle_update_contexts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Backend-initiated IPC to add/update a context in the GUI
    This is called when new context data is available
    """
    try:
        context = params.get('context') if params else None
        
        if not context:
            return create_error_response(request, 'INVALID_PARAMS', 'Context data required')
        
        logger.info(f"[Context] Updating context: {context.get('uid', 'unknown')}")
        
        # Push to frontend via IPC
        main_window = AppContext.get_main_window()
        if main_window:
            main_window.push_to_web('update_contexts', context)
            logger.info("[Context] Pushed context update to frontend")
        
        return create_success_response(request, {"updated": True})
        
    except Exception as e:
        logger.error(f"[Context] Error updating context: {e}", exc_info=True)
        return create_error_response(request, 'UPDATE_CONTEXT_ERROR', str(e))


@IPCHandlerRegistry.handler('delete_context')
def handle_delete_context(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Frontend-initiated IPC to delete a context
    """
    try:
        context_id = params.get('contextId') if params else None
        
        if not context_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Context ID required')
        
        logger.info(f"[Context] Deleting context: {context_id}")
        
        # In production, this would delete from database
        # For now, just acknowledge
        
        return create_success_response(request, {"deleted": True, "contextId": context_id})
        
    except Exception as e:
        logger.error(f"[Context] Error deleting context: {e}", exc_info=True)
        return create_error_response(request, 'DELETE_CONTEXT_ERROR', str(e))


@IPCHandlerRegistry.handler('refresh_contexts')
def handle_refresh_contexts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Frontend-initiated IPC to request latest contexts
    """
    try:
        logger.info("[Context] Refreshing contexts")
        
        # Send latest contexts to frontend
        contexts = generate_test_contexts()
        
        main_window = AppContext.get_main_window()
        if main_window:
            main_window.push_to_web('send_all_contexts', contexts)
            logger.info(f"[Context] Refreshed {len(contexts)} contexts")
        
        return create_success_response(request, {"refreshed": True, "count": len(contexts)})
        
    except Exception as e:
        logger.error(f"[Context] Error refreshing contexts: {e}", exc_info=True)
        return create_error_response(request, 'REFRESH_CONTEXTS_ERROR', str(e))


# Auto-register handlers when module is imported
logger.info("[Context] Context handlers registered")
