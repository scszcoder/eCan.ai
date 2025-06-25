import { Message, Chat, Content, MessageStatus, RoleConfig } from './types/chat';

/**
 * 默认角色配置，用于 Semi UI Chat 组件
 */
export const defaultRoleConfig: RoleConfig = {
  user: {
    name: '用户',
    avatar: '/src/assets/agent0_100.png',
    color: 'blue'
  },
  assistant: {
    name: 'AI助手',
    avatar: '/src/assets/icons1_100.png',
    color: 'green'
  },
  system: {
    name: '系统',
    avatar: '/src/assets/icons0_door_100.png',
    color: 'grey'
  },
  agent: {
    name: '客服代理',
    avatar: '/src/assets/icons2_100.png',
    color: 'purple'
  }
};

/**
 * 客服聊天示例数据
 */
export const customerServiceMessages: Message[] = [
  {
    id: 'cs-msg-1',
    role: 'system',
    createAt: 1710000000000,
    content: '欢迎来到客服中心，请问有什么可以帮您？',
    status: 'complete',
  },
  {
    id: 'cs-msg-2',
    role: 'user',
    createAt: 1710000010000,
    content: '我的订单一直没有发货，订单号是：EC20240625001',
    status: 'complete',
  },
  {
    id: 'cs-msg-3',
    role: 'agent',
    createAt: 1710000020000,
    content: '您好，我是客服小王，很高兴为您服务。我正在查询您的订单信息，请稍等。',
    status: 'complete',
  },
  {
    id: 'cs-msg-4',
    role: 'agent',
    createAt: 1710000030000,
    content: {
      type: 'text',
      text: '已经查询到您的订单，物流信息如下：'
    } as Content,
    status: 'complete',
  },
  {
    id: 'cs-msg-5',
    role: 'agent',
    createAt: 1710000040000,
    content: {
      type: 'code',
      code: {
        lang: 'json',
        value: JSON.stringify({
          orderNo: 'EC20240625001',
          status: 'shipping',
          logistics: {
            company: '顺丰快递',
            trackingNo: 'SF1234567890',
            estimatedDelivery: '2024-06-28'
          }
        }, null, 2)
      }
    } as Content,
    status: 'complete',
  },
  {
    id: 'cs-msg-6',
    role: 'user',
    createAt: 1710000050000,
    content: '谢谢，请问有没有更详细的物流跟踪信息？',
    status: 'complete',
  },
  {
    id: 'cs-msg-7',
    role: 'agent',
    createAt: 1710000060000,
    content: '当然，以下是详细的物流跟踪信息：',
    status: 'complete',
    attachment: [
      {
        uid: 'att-logistics',
        name: 'logistics_tracking.pdf',
        status: 'done',
        url: '/files/logistics_tracking.pdf',
        size: 512000,
        type: 'application/pdf',
      }
    ]
  },
  {
    id: 'cs-msg-8',
    role: 'user',
    createAt: 1710000070000,
    content: '非常感谢您的帮助！',
    status: 'complete',
  },
  {
    id: 'cs-msg-9',
    role: 'agent',
    createAt: 1710000080000,
    content: '不客气，很高兴能帮到您。如果还有其他问题，随时联系我们。祝您生活愉快！',
    status: 'complete',
  }
];

/**
 * AI助手聊天示例数据
 */
export const aiAssistantMessages: Message[] = [
  {
    id: 'ai-msg-1',
    role: 'user',
    createAt: 1710100000000,
    content: '你好，AI助手！',
    status: 'complete',
  },
  {
    id: 'ai-msg-2',
    role: 'assistant',
    createAt: 1710100001000,
    content: '您好！我是您的AI助手。今天我能为您做些什么？',
    status: 'complete',
  },
  {
    id: 'ai-msg-3',
    role: 'user',
    createAt: 1710100002000,
    content: '请帮我写一个简单的React组件，用于显示一个待办事项列表。',
    status: 'complete',
  },
  {
    id: 'ai-msg-4',
    role: 'assistant',
    createAt: 1710100003000,
    content: {
      type: 'code',
      code: {
        lang: 'jsx',
        value: `import React, { useState } from 'react';

const TodoList = () => {
  const [todos, setTodos] = useState([
    { id: 1, text: '学习React', completed: false },
    { id: 2, text: '完成项目', completed: false },
    { id: 3, text: '准备面试', completed: true }
  ]);
  const [input, setInput] = useState('');

  const addTodo = () => {
    if (input.trim() !== '') {
      setTodos([
        ...todos,
        { id: Date.now(), text: input, completed: false }
      ]);
      setInput('');
    }
  };

  const toggleTodo = (id) => {
    setTodos(todos.map(todo => 
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    ));
  };

  return (
    <div className="todo-list">
      <h2>待办事项列表</h2>
      <div className="add-todo">
        <input 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="添加新的待办事项"
        />
        <button onClick={addTodo}>添加</button>
      </div>
      <ul>
        {todos.map(todo => (
          <li 
            key={todo.id}
            style={{ textDecoration: todo.completed ? 'line-through' : 'none' }}
            onClick={() => toggleTodo(todo.id)}
          >
            {todo.text}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default TodoList;`
      }
    } as Content,
    status: 'complete',
  },
  {
    id: 'ai-msg-5',
    role: 'user',
    createAt: 1710100004000,
    content: '能否添加一个删除待办事项的功能？',
    status: 'complete',
  },
  {
    id: 'ai-msg-6',
    role: 'assistant',
    createAt: 1710100005000,
    content: '当然可以，以下是添加了删除功能的组件：',
    status: 'complete',
  },
  {
    id: 'ai-msg-7',
    role: 'assistant',
    createAt: 1710100006000,
    content: {
      type: 'code',
      code: {
        lang: 'jsx',
        value: `import React, { useState } from 'react';
import './TodoList.css'; // 假设有相应的CSS文件

const TodoList = () => {
  const [todos, setTodos] = useState([
    { id: 1, text: '学习React', completed: false },
    { id: 2, text: '完成项目', completed: false },
    { id: 3, text: '准备面试', completed: true }
  ]);
  const [input, setInput] = useState('');

  const addTodo = () => {
    if (input.trim() !== '') {
      setTodos([
        ...todos,
        { id: Date.now(), text: input, completed: false }
      ]);
      setInput('');
    }
  };

  const toggleTodo = (id) => {
    setTodos(todos.map(todo => 
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    ));
  };

  const deleteTodo = (id, e) => {
    e.stopPropagation(); // 阻止事件冒泡，避免触发toggleTodo
    setTodos(todos.filter(todo => todo.id !== id));
  };

  return (
    <div className="todo-list">
      <h2>待办事项列表</h2>
      <div className="add-todo">
        <input 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="添加新的待办事项"
        />
        <button onClick={addTodo}>添加</button>
      </div>
      <ul>
        {todos.map(todo => (
          <li key={todo.id} className="todo-item">
            <span 
              className={todo.completed ? 'completed' : ''}
              onClick={() => toggleTodo(todo.id)}
            >
              {todo.text}
            </span>
            <button 
              className="delete-btn"
              onClick={(e) => deleteTodo(todo.id, e)}
            >
              删除
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default TodoList;`
      }
    } as Content,
    status: 'complete',
  },
  {
    id: 'ai-msg-8',
    role: 'user',
    createAt: 1710100007000,
    content: '太棒了！能否再添加一个CSS文件，让这个组件看起来更美观？',
    status: 'complete',
  },
  {
    id: 'ai-msg-9',
    role: 'assistant',
    createAt: 1710100008000,
    content: {
      type: 'code',
      code: {
        lang: 'css',
        value: `.todo-list {
  max-width: 500px;
  margin: 0 auto;
  padding: 20px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  background-color: #fff;
}

h2 {
  color: #333;
  text-align: center;
  margin-bottom: 20px;
}

.add-todo {
  display: flex;
  margin-bottom: 20px;
}

input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px 0 0 4px;
  font-size: 16px;
}

button {
  padding: 10px 15px;
  background-color: #4caf50;
  color: white;
  border: none;
  border-radius: 0 4px 4px 0;
  cursor: pointer;
  font-size: 16px;
}

button:hover {
  background-color: #45a049;
}

ul {
  list-style-type: none;
  padding: 0;
}

.todo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  margin-bottom: 10px;
  background-color: #f9f9f9;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.todo-item:hover {
  background-color: #f1f1f1;
}

.completed {
  text-decoration: line-through;
  color: #888;
}

.delete-btn {
  background-color: #f44336;
  border-radius: 4px;
  padding: 5px 10px;
}

.delete-btn:hover {
  background-color: #d32f2f;
}`
      }
    } as Content,
    status: 'complete',
  },
  {
    id: 'ai-msg-10',
    role: 'user',
    createAt: 1710100009000,
    content: {
      type: 'image',
      imageUrl: '/src/assets/icons3.png'
    } as Content,
    status: 'complete',
  },
  {
    id: 'ai-msg-11',
    role: 'assistant',
    createAt: 1710100010000,
    content: '这是一张图标图片。如果您想在待办事项应用中使用这些图标，我可以帮您将它们集成到组件中。您希望如何使用这些图标呢？',
    status: 'complete',
  }
];

/**
 * 系统通知示例数据
 */
export const systemNotificationMessages: Message[] = [
  {
    id: 'sys-msg-1',
    role: 'system',
    createAt: 1710200000000,
    content: '欢迎使用我们的聊天系统！',
    status: 'complete',
  },
  {
    id: 'sys-msg-2',
    role: 'system',
    createAt: 1710200001000,
    content: '系统已更新到最新版本 v2.5.0，新增功能：多人群聊、文件共享和消息引用。',
    status: 'complete',
  },
  {
    id: 'sys-msg-3',
    role: 'system',
    createAt: 1710200002000,
    content: {
      type: 'text',
      text: '您的账户已成功激活高级功能，有效期至2025年6月30日。'
    } as Content,
    status: 'complete',
  },
  {
    id: 'sys-msg-4',
    role: 'user',
    createAt: 1710200003000,
    content: '如何使用新的群聊功能？',
    status: 'complete',
  },
  {
    id: 'sys-msg-5',
    role: 'system',
    createAt: 1710200004000,
    content: '请查看以下群聊功能使用指南：',
    status: 'complete',
    attachment: [
      {
        uid: 'att-guide',
        name: 'group_chat_guide.pdf',
        status: 'done',
        url: '/files/group_chat_guide.pdf',
        size: 1024000,
        type: 'application/pdf',
      }
    ]
  },
  {
    id: 'sys-msg-6',
    role: 'system',
    createAt: 1710200005000,
    content: '系统将于今晚22:00-23:00进行维护，期间服务可能短暂不可用。',
    status: 'complete',
  }
];

/**
 * 多人群聊示例数据
 */
export const groupChatMessages: Message[] = [
  {
    id: 'grp-msg-1',
    role: 'system',
    createAt: 1710300000000,
    content: '项目讨论群已创建，已添加所有团队成员。',
    status: 'complete',
  },
  {
    id: 'grp-msg-2',
    role: 'user',
    createAt: 1710300001000,
    content: '大家好，我们今天需要讨论一下新项目的进度。',
    status: 'complete',
    senderId: 'user-1',
    senderName: '张经理',
  },
  {
    id: 'grp-msg-3',
    role: 'agent',
    createAt: 1710300002000,
    content: '我已经完成了UI设计稿，请大家查看并提供反馈。',
    status: 'complete',
    senderId: 'agent-1',
    senderName: '李设计',
    attachment: [
      {
        uid: 'att-design',
        name: 'ui_design.fig',
        status: 'done',
        url: '/files/ui_design.fig',
        size: 5120000,
        type: 'application/figma',
      }
    ]
  },
  {
    id: 'grp-msg-4',
    role: 'agent',
    createAt: 1710300003000,
    content: '后端API已经开发完成，文档如下：',
    status: 'complete',
    senderId: 'agent-2',
    senderName: '王工程',
  },
  {
    id: 'grp-msg-5',
    role: 'agent',
    createAt: 1710300004000,
    content: {
      type: 'code',
      code: {
        lang: 'markdown',
        value: `# API 文档

## 用户认证
- POST /api/auth/login
- POST /api/auth/register
- GET /api/auth/profile

## 数据接口
- GET /api/data/list
- POST /api/data/create
- PUT /api/data/update/{id}
- DELETE /api/data/delete/{id}

所有接口返回格式：
\`\`\`json
{
  "code": 0,
  "message": "success",
  "data": {}
}
\`\`\`

详细参数请参考完整文档。`
      }
    } as Content,
    status: 'complete',
    senderId: 'agent-2',
    senderName: '王工程',
  },
  {
    id: 'grp-msg-6',
    role: 'assistant',
    createAt: 1710300005000,
    content: '我已经将所有需求整理成了测试用例，并创建了自动化测试脚本。',
    status: 'complete',
    senderId: 'assistant-1',
    senderName: 'QA助手',
  },
  {
    id: 'grp-msg-7',
    role: 'user',
    createAt: 1710300006000,
    content: '非常好！我们下周一安排一次全体会议，讨论下一阶段的工作计划。',
    status: 'complete',
    senderId: 'user-1',
    senderName: '张经理',
  },
  {
    id: 'grp-msg-8',
    role: 'agent',
    createAt: 1710300007000,
    content: {
      type: 'image',
      imageUrl: '/src/assets/icons4.png'
    } as Content,
    status: 'complete',
    senderId: 'agent-3',
    senderName: '赵产品',
  },
  {
    id: 'grp-msg-9',
    role: 'agent',
    createAt: 1710300008000,
    content: '这是我设计的新图标，大家觉得怎么样？',
    status: 'complete',
    senderId: 'agent-3',
    senderName: '赵产品',
  },
  {
    id: 'grp-msg-10',
    role: 'user',
    createAt: 1710300009000,
    content: '看起来不错，但颜色可能需要调整一下，与我们的品牌色更一致。',
    status: 'complete',
    senderId: 'user-1',
    senderName: '张经理',
  }
];

/**
 * 错误状态消息示例
 */
export const errorStatusMessages: Message[] = [
  {
    id: 'err-msg-1',
    role: 'user',
    createAt: 1710400000000,
    content: '你能帮我分析一下这段代码吗？',
    status: 'complete',
  },
  {
    id: 'err-msg-2',
    role: 'user',
    createAt: 1710400001000,
    content: {
      type: 'code',
      code: {
        lang: 'javascript',
        value: `function calculateSum(arr) {
  let sum = 0;
  for (let i = 0; i < arr.length; i++) {
    sum += arr[i];
  }
  return sum;
}`
      }
    } as Content,
    status: 'complete',
  },
  {
    id: 'err-msg-3',
    role: 'assistant',
    createAt: 1710400002000,
    content: '正在分析代码...',
    status: 'loading',
  },
  {
    id: 'err-msg-4',
    role: 'assistant',
    createAt: 1710400003000,
    content: '这是一个计算数组元素总和的函数，实现方式是通过循环遍历数组并累加每个元素。这种实现方式简单明了，时间复杂度为O(n)，其中n是数组的长度。',
    status: 'incomplete',
  },
  {
    id: 'err-msg-5',
    role: 'assistant',
    createAt: 1710400004000,
    content: '不过，在现代JavaScript中，你也可以使用数组的reduce方法来实现相同的功能，代码会更简洁：',
    status: 'error',
  },
  {
    id: 'err-msg-6',
    role: 'user',
    createAt: 1710400005000,
    content: '看起来消息发送失败了，能重新发送吗？',
    status: 'complete',
  },
  {
    id: 'err-msg-7',
    role: 'assistant',
    createAt: 1710400006000,
    content: {
      type: 'code',
      code: {
        lang: 'javascript',
        value: `// 使用reduce方法的现代实现
function calculateSum(arr) {
  return arr.reduce((sum, current) => sum + current, 0);
}`
      }
    } as Content,
    status: 'sending',
  },
  {
    id: 'err-msg-8',
    role: 'system',
    createAt: 1710400007000,
    content: '由于网络问题，部分消息可能发送失败。请检查您的网络连接并重试。',
    status: 'complete',
  }
];

// 导出所有示例数据作为 demoChatMessages
export const demoChatMessages: Message[] = [
  ...aiAssistantMessages,
  ...customerServiceMessages.slice(0, 3) // 添加部分客服消息作为示例
];

/**
 * Demo chat data for the chat list
 */
export const demoChatData: Chat[] = [
  {
    id: 'chat-1',
    type: 'user-agent',
    name: 'AI助手',
    avatar: '/src/assets/icons1_100.png',
    members: [
      {
        id: 'user-1',
        role: 'user',
        name: '用户',
        avatar: '/src/assets/agent0_100.png',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        name: 'AI助手',
        avatar: '/src/assets/icons1_100.png',
      }
    ],
    messages: aiAssistantMessages,
    lastMsg: aiAssistantMessages[aiAssistantMessages.length - 1].content.toString(),
    lastMsgTime: aiAssistantMessages[aiAssistantMessages.length - 1].createAt,
    unread: 1,
  },
  {
    id: 'chat-2',
    type: 'user-system',
    name: '系统通知',
    avatar: '/src/assets/icons0_door_100.png',
    members: [
      {
        id: 'user-1',
        role: 'user',
        name: '用户',
        avatar: '/src/assets/agent0_100.png',
      },
      {
        id: 'system-1',
        role: 'system',
        name: '系统',
        avatar: '/src/assets/icons0_door_100.png',
      }
    ],
    messages: systemNotificationMessages,
    lastMsg: systemNotificationMessages[systemNotificationMessages.length - 1].content.toString(),
    lastMsgTime: systemNotificationMessages[systemNotificationMessages.length - 1].createAt,
    unread: 2,
  },
  {
    id: 'chat-3',
    type: 'user-agent',
    name: '客服中心',
    avatar: '/src/assets/icons2_100.png',
    members: [
      {
        id: 'user-1',
        role: 'user',
        name: '用户',
        avatar: '/src/assets/agent0_100.png',
      },
      {
        id: 'agent-1',
        role: 'agent',
        name: '客服代理',
        avatar: '/src/assets/icons2_100.png',
      }
    ],
    messages: customerServiceMessages,
    lastMsg: customerServiceMessages[customerServiceMessages.length - 1].content.toString(),
    lastMsgTime: customerServiceMessages[customerServiceMessages.length - 1].createAt,
    unread: 0,
  },
  {
    id: 'chat-4',
    type: 'group',
    name: '项目讨论组',
    avatar: '/src/assets/icons3.png',
    members: [
      {
        id: 'user-1',
        role: 'user',
        name: '张经理',
        avatar: '/src/assets/agent0_100.png',
      },
      {
        id: 'agent-1',
        role: 'agent',
        name: '李设计',
        avatar: '/src/assets/icons1_100.png',
      },
      {
        id: 'agent-2',
        role: 'agent',
        name: '王工程',
        avatar: '/src/assets/icons2_100.png',
      },
      {
        id: 'agent-3',
        role: 'agent',
        name: '赵产品',
        avatar: '/src/assets/icons3.png',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        name: 'QA助手',
        avatar: '/src/assets/icons5.png',
      }
    ],
    messages: groupChatMessages,
    lastMsg: groupChatMessages[groupChatMessages.length - 1].content.toString(),
    lastMsgTime: groupChatMessages[groupChatMessages.length - 1].createAt,
    unread: 5,
    pinned: true,
  },
  {
    id: 'chat-5',
    type: 'user-assistant',
    name: '错误状态演示',
    avatar: '/src/assets/icons6.png',
    members: [
      {
        id: 'user-1',
        role: 'user',
        name: '用户',
        avatar: '/src/assets/agent0_100.png',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        name: '助手',
        avatar: '/src/assets/icons6.png',
      }
    ],
    messages: errorStatusMessages,
    lastMsg: errorStatusMessages[errorStatusMessages.length - 1].content.toString(),
    lastMsgTime: errorStatusMessages[errorStatusMessages.length - 1].createAt,
    unread: 1,
  }
]; 