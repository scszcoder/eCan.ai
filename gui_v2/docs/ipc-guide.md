# IPC 通信使用指南

本文档详细说明了如何在 gui_v2 和 Python 后端之间使用 IPC (进程间通信) 进行双向通信。

## 目录
- [基本概念](#基本概念)
- [在 gui_v2 中使用 IPC](#在-gui_v2-中使用-ipc)
- [在 Python 中使用 IPC](#在-python-中使用-ipc)
- [可用的命令和请求](#可用的命令和请求)
- [错误处理](#错误处理)
- [最佳实践](#最佳实践)

## 基本概念

IPC 系统基于 PySide6 的 WebChannel 实现，提供了以下功能：

- 双向通信：支持从 GUI 到 Python 和从 Python 到 GUI 的通信
- 类型安全：使用 TypeScript 确保类型安全
- 错误处理：内置错误处理和日志记录
- 可扩展：易于添加新的命令和请求

## 在 gui_v2 中使用 IPC

### 1. 导入 IPC 服务

```typescript
import { ipcService } from '../services/ipc';
```

### 2. 发送命令到 Python

```typescript
// 基本命令
ipcService.sendCommand('reload');

// 带参数的命令
ipcService.sendCommand('execute_script', {
  script: 'console.log("Hello from Python")'
});
```

### 3. 发送请求到 Python

```typescript
// 基本请求
ipcService.sendRequest('get_page_info');

// 带参数的请求
ipcService.sendRequest('custom_request', {
  param1: 'value1',
  param2: 'value2'
});
```

### 4. 处理 Python 的响应

```typescript
import { useEffect } from 'react';

function MyComponent() {
  useEffect(() => {
    // 注册响应处理器
    ipcService.onResponse('command_result', (result) => {
      console.log('Command result:', result);
    });

    ipcService.onResponse('request_result', (result) => {
      console.log('Request result:', result);
    });

    // 清理处理器
    return () => {
      ipcService.offResponse('command_result');
      ipcService.offResponse('request_result');
    };
  }, []);

  return (
    // 组件内容
  );
}
```

### 5. 使用 Promise 包装请求

```typescript
// 创建一个 Promise 包装的请求函数
function getPageInfo(): Promise<any> {
  return new Promise((resolve, reject) => {
    const handler = (result: any) => {
      ipcService.offResponse('request_result');
      resolve(result);
    };

    ipcService.onResponse('request_result', handler);
    ipcService.sendRequest('get_page_info');
  });
}

// 使用 async/await
async function handleGetPageInfo() {
  try {
    const pageInfo = await getPageInfo();
    console.log('Page info:', pageInfo);
  } catch (error) {
    console.error('Error:', error);
  }
}
```

## 在 Python 中使用 IPC

### 1. 发送消息到 GUI

```python
# 发送普通消息
self.bridge.sendToJavaScript({
    'type': 'response',
    'responseType': 'message',
    'result': {
        'message': 'Hello from Python'
    }
})

# 发送状态更新
self.bridge.sendToJavaScript({
    'type': 'response',
    'responseType': 'state_update',
    'result': {
        'status': 'running',
        'progress': 50
    }
})
```

### 2. 执行 JavaScript 代码

```python
# 执行 JavaScript 代码
script = "console.log('Hello from Python')"
self.web_view.page().runJavaScript(script)
```

### 3. 处理来自 GUI 的命令和请求

```python
def handleCommand(self, data):
    command = data.get('command')
    params = data.get('params', {})
    
    if command == 'custom_command':
        # 处理自定义命令
        result = self.process_custom_command(params)
        self.sendResponse('command_result', result)

def handleRequest(self, data):
    request = data.get('request')
    params = data.get('params', {})
    
    if request == 'custom_request':
        # 处理自定义请求
        result = self.process_custom_request(params)
        self.sendResponse('request_result', result)
```

## 可用的命令和请求

### 命令列表

| 命令 | 描述 | 参数 |
|------|------|------|
| `reload` | 重新加载页面 | 无 |
| `toggle_dev_tools` | 切换开发者工具 | 无 |
| `clear_logs` | 清除日志 | 无 |
| `execute_script` | 执行 JavaScript 代码 | `script`: 要执行的代码 |

### 请求列表

| 请求 | 描述 | 参数 | 返回数据 |
|------|------|------|----------|
| `get_page_info` | 获取页面信息 | 无 | `{title, url, is_loading}` |
| `get_console_logs` | 获取控制台日志 | 无 | `{logs}` |
| `get_network_logs` | 获取网络日志 | 无 | `{logs}` |
| `get_element_logs` | 获取元素日志 | 无 | `{logs}` |

## 错误处理

### GUI 端错误处理

```typescript
try {
  await ipcService.sendRequest('some_request');
} catch (error) {
  console.error('Error:', error);
  // 处理错误
}
```

### Python 端错误处理

```python
try:
    self.bridge.sendToJavaScript({
        'type': 'response',
        'responseType': 'error',
        'result': {
            'message': 'Error occurred',
            'details': str(error)
        }
    })
except Exception as e:
    logger_helper.error(f"Error sending to JavaScript: {e}")
```

## 最佳实践

1. **类型安全**
   - 使用 TypeScript 接口定义消息类型
   - 为所有消息添加类型检查

2. **错误处理**
   - 始终使用 try-catch 包装 IPC 调用
   - 实现适当的错误恢复机制

3. **性能优化**
   - 避免频繁的小消息
   - 批量处理相关操作

4. **调试**
   - 使用开发者工具监控消息
   - 记录关键操作日志

5. **安全性**
   - 验证所有输入数据
   - 限制敏感操作

## 示例代码

### 完整的组件示例

```typescript
import React, { useEffect, useState } from 'react';
import { ipcService } from '../services/ipc';

interface PageInfo {
  title: string;
  url: string;
  is_loading: boolean;
}

function PageInfoComponent() {
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 注册响应处理器
    ipcService.onResponse('request_result', (result) => {
      if (result.error) {
        setError(result.error);
      } else {
        setPageInfo(result);
      }
    });

    // 获取页面信息
    ipcService.sendRequest('get_page_info');

    return () => {
      ipcService.offResponse('request_result');
    };
  }, []);

  if (error) {
    return <div>Error: {error}</div>;
  }

  if (!pageInfo) {
    return <div>Loading...</div>;
  }

  return (
    <div>
      <h2>Page Information</h2>
      <p>Title: {pageInfo.title}</p>
      <p>URL: {pageInfo.url}</p>
      <p>Loading: {pageInfo.is_loading ? 'Yes' : 'No'}</p>
    </div>
  );
}

export default PageInfoComponent;
```

### Python 端完整示例

```python
class CustomWebGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bridge = WebChannelBridge(self)
        
    def handle_custom_command(self, params):
        try:
            # 处理命令
            result = self.process_command(params)
            
            # 发送成功响应
            self.bridge.sendResponse('command_result', {
                'status': 'success',
                'result': result
            })
        except Exception as e:
            # 发送错误响应
            self.bridge.sendResponse('command_result', {
                'status': 'error',
                'message': str(e)
            })
            
    def process_command(self, params):
        # 实现命令处理逻辑
        return {'processed': True}
``` 