import React, { useEffect } from 'react';
import { ContextPanel } from './ContextPanel';
import { useContextStore } from '@/stores/contextStore';

/**
 * Test wrapper for ContextPanel
 * This bypasses IPC and directly loads test data
 * Use this to verify the UI works before testing IPC
 */
export const ContextPanelTest: React.FC = () => {
  const { setContexts } = useContextStore();

  useEffect(() => {
    // Load test data directly without IPC
    const testContexts = [
      {
        uid: 'ctx-test-1',
        title: 'Customer Support Inquiry',
        messageCount: 5,
        mostRecentTimestamp: new Date(Date.now() - 5 * 60000).toISOString(),
        mostRecentMessage: 'Thank you for your help with the account issue!',
        items: [
          {
            uid: 'item-1',
            type: 'text' as const,
            timestamp: new Date(Date.now() - 30 * 60000).toISOString(),
            generator: 'human' as const,
            generatorName: 'User',
            content: {
              message: "I'm having trouble logging into my account. Can you help?"
            }
          },
          {
            uid: 'item-2',
            type: 'tool_call' as const,
            timestamp: new Date(Date.now() - 28 * 60000).toISOString(),
            generator: 'agent' as const,
            generatorName: 'Support Agent',
            content: {
              description: 'Checking user authentication status',
              toolName: 'check_user_auth',
              toolParams: { user_id: '12345', check_level: 'full' },
              toolResult: { status: 'locked', reason: 'Too many failed attempts' }
            }
          },
          {
            uid: 'item-3',
            type: 'code_execution' as const,
            timestamp: new Date(Date.now() - 25 * 60000).toISOString(),
            generator: 'agent' as const,
            generatorName: 'Support Agent',
            content: {
              description: 'Unlocking user account',
              code: `# Reset failed login attempts
db.users.update_one(
    {'user_id': '12345'},
    {'$set': {'failed_attempts': 0, 'locked': False}}
)`,
              codeLanguage: 'python'
            }
          }
        ],
        isArchived: false
      },
      {
        uid: 'ctx-test-2',
        title: 'API Integration Setup',
        messageCount: 3,
        mostRecentTimestamp: new Date(Date.now() - 2 * 3600000).toISOString(),
        mostRecentMessage: 'Successfully configured the webhook endpoint',
        items: [
          {
            uid: 'item-4',
            type: 'text' as const,
            timestamp: new Date(Date.now() - 3 * 3600000).toISOString(),
            generator: 'human' as const,
            generatorName: 'Developer',
            content: {
              message: 'I need to set up a webhook for payment notifications'
            }
          },
          {
            uid: 'item-5',
            type: 'api_call' as const,
            timestamp: new Date(Date.now() - 2.5 * 3600000).toISOString(),
            generator: 'agent' as const,
            generatorName: 'Integration Agent',
            content: {
              description: 'Creating webhook endpoint',
              toolName: 'create_webhook',
              toolParams: {
                url: 'https://api.example.com/webhooks/payment',
                events: ['payment.success', 'payment.failed']
              },
              toolResult: {
                webhook_id: 'wh_xyz789',
                status: 'active'
              }
            }
          }
        ],
        isArchived: false
      },
      {
        uid: 'ctx-test-3',
        title: 'Data Migration Task',
        messageCount: 4,
        mostRecentTimestamp: new Date(Date.now() - 86400000).toISOString(),
        mostRecentMessage: 'Migration completed: 10,000 records processed',
        items: [
          {
            uid: 'item-6',
            type: 'text' as const,
            timestamp: new Date(Date.now() - 90000000).toISOString(),
            generator: 'human' as const,
            generatorName: 'Admin',
            content: {
              message: 'Need to migrate user data from old database to new schema'
            }
          },
          {
            uid: 'item-7',
            type: 'system_event' as const,
            timestamp: new Date(Date.now() - 86400000).toISOString(),
            generator: 'system' as const,
            generatorName: 'System',
            content: {
              message: 'Migration completed: 10,000 records processed successfully',
              json: {
                total: 10000,
                processed: 10000,
                failed: 0,
                status: 'completed'
              }
            }
          }
        ],
        isArchived: false
      }
    ];

    console.log('[ContextPanelTest] Loading test data:', testContexts);
    setContexts(testContexts);
  }, [setContexts]);

  return <ContextPanel />;
};
