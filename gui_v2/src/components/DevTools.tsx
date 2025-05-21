import React, { useEffect, useState } from 'react';
import { logger } from '../utils/logger';

interface PageInfo {
  title: string;
  url: string;
  timestamp: string;
}

interface LogEntry {
  level: string;
  message: string;
  timestamp: string;
}

interface NetworkRequest {
  url: string;
  method: string;
  status: number;
  timestamp: string;
}

export const DevTools: React.FC = () => {
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [consoleLogs, setConsoleLogs] = useState<LogEntry[]>([]);
  const [networkLogs, setNetworkLogs] = useState<NetworkRequest[]>([]);

  // 加载页面信息
  const loadPageInfo = () => {
    setPageInfo({
      title: document.title,
      url: window.location.href,
      timestamp: new Date().toISOString()
    });
  };

  // 重新加载页面
  const reload = () => {
    window.location.reload();
  };

  // 清除日志
  const clearLogs = () => {
    setConsoleLogs([]);
    setNetworkLogs([]);
    console.clear();
  };

  // 执行脚本
  const executeScript = (script: string) => {
    try {
      // eslint-disable-next-line no-eval
      eval(script);
    } catch (e) {
      logger.error('Error executing script:', e);
    }
  };

  // 初始化控制台日志监听
  useEffect(() => {
    const originalConsole = {
      log: console.log,
      info: console.info,
      warn: console.warn,
      error: console.error
    };

    const addLog = (level: string, ...args: unknown[]) => {
      setConsoleLogs(prev => [...prev, {
        level,
        message: args.map(arg => 
          typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
        ).join(' '),
        timestamp: new Date().toISOString()
      }]);
    };

    console.log = (...args) => {
      originalConsole.log.apply(console, args);
      addLog('log', ...args);
    };

    console.info = (...args) => {
      originalConsole.info.apply(console, args);
      addLog('info', ...args);
    };

    console.warn = (...args) => {
      originalConsole.warn.apply(console, args);
      addLog('warn', ...args);
    };

    console.error = (...args) => {
      originalConsole.error.apply(console, args);
      addLog('error', ...args);
    };

    return () => {
      console.log = originalConsole.log;
      console.info = originalConsole.info;
      console.warn = originalConsole.warn;
      console.error = originalConsole.error;
    };
  }, []);

  // 初始化网络请求监听
  useEffect(() => {
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const startTime = new Date().toISOString();
      try {
        const response = await originalFetch.apply(window, args);
        const url = args[0] instanceof Request ? args[0].url : args[0].toString();
        setNetworkLogs(prev => [...prev, {
          url,
          method: args[1]?.method || 'GET',
          status: response.status,
          timestamp: startTime
        }]);
        return response;
      } catch (error) {
        const url = args[0] instanceof Request ? args[0].url : args[0].toString();
        setNetworkLogs(prev => [...prev, {
          url,
          method: args[1]?.method || 'GET',
          status: 0,
          timestamp: startTime
        }]);
        throw error;
      }
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  // 初始化页面信息
  useEffect(() => {
    loadPageInfo();
  }, []);

  return (
    <div className="dev-tools">
      <div className="toolbar">
        <button onClick={reload}>重新加载</button>
        <button onClick={clearLogs}>清除日志</button>
        <button onClick={() => executeScript('console.log("Hello from DevTools")')}>
          执行脚本
        </button>
        <button onClick={loadPageInfo}>
          刷新信息
        </button>
      </div>

      <div className="content">
        <div className="page-info">
          <h3>页面信息</h3>
          {pageInfo && (
            <div>
              <p>标题: {pageInfo.title}</p>
              <p>URL: {pageInfo.url}</p>
              <p>时间: {pageInfo.timestamp}</p>
            </div>
          )}
        </div>

        <div className="logs">
          <div className="console-logs">
            <h3>控制台日志</h3>
            <pre>{JSON.stringify(consoleLogs, null, 2)}</pre>
          </div>

          <div className="network-logs">
            <h3>网络日志</h3>
            <pre>{JSON.stringify(networkLogs, null, 2)}</pre>
          </div>
        </div>
      </div>

      <style>{`
        .dev-tools {
          padding: 1rem;
          background: #1e1e1e;
          color: #d4d4d4;
          font-family: monospace;
        }

        .toolbar {
          margin-bottom: 1rem;
          display: flex;
          gap: 0.5rem;
        }

        .toolbar button {
          padding: 0.5rem 1rem;
          background: #333;
          color: #fff;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }

        .toolbar button:hover {
          background: #444;
        }

        .content {
          display: grid;
          grid-template-columns: 300px 1fr;
          gap: 1rem;
        }

        .page-info {
          background: #252526;
          padding: 1rem;
          border-radius: 4px;
        }

        .logs {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .console-logs,
        .network-logs {
          background: #252526;
          padding: 1rem;
          border-radius: 4px;
        }

        pre {
          margin: 0;
          white-space: pre-wrap;
          word-wrap: break-word;
        }

        h3 {
          margin-top: 0;
          margin-bottom: 1rem;
          color: #569cd6;
        }
      `}</style>
    </div>
  );
}; 