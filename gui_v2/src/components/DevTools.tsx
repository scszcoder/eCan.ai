import React, { useEffect, useState } from 'react';
import { useIPC } from '../hooks/useIPC';
import { logger } from '../utils/logger';
import { LogEntry, NetworkRequest, ElementLog } from '../services/ipc';

interface PageInfo {
  title: string;
  url: string;
  timestamp: string;
}

export const DevTools: React.FC = () => {
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [consoleLogs, setConsoleLogs] = useState<LogEntry[]>([]);
  const [networkLogs, setNetworkLogs] = useState<NetworkRequest[]>([]);
  const [elementLogs, setElementLogs] = useState<ElementLog[]>([]);

  const {
    reload,
    toggleDevTools,
    clearLogs,
    executeScript,
    getPageInfo,
    getConsoleLogs,
    getNetworkLogs,
    getElementLogs
  } = useIPC({
    onEvent: (eventType, data) => {
      logger.info(`Received event: ${eventType}`, data);
    }
  });

  // 加载页面信息和日志
  useEffect(() => {
    const loadData = async () => {
      try {
        const info = await getPageInfo();
        setPageInfo(info);

        const logs = await getConsoleLogs();
        setConsoleLogs(logs);

        const network = await getNetworkLogs();
        setNetworkLogs(network);

        const elements = await getElementLogs();
        setElementLogs(elements);
      } catch (e) {
        logger.error('Error loading data:', e);
      }
    };

    loadData();
  }, [getPageInfo, getConsoleLogs, getNetworkLogs, getElementLogs]);

  return (
    <div className="dev-tools">
      <div className="toolbar">
        <button onClick={reload}>重新加载</button>
        <button onClick={toggleDevTools}>开发者工具</button>
        <button onClick={clearLogs}>清除日志</button>
        <button onClick={() => executeScript('console.log("Hello from DevTools")')}>
          执行脚本
        </button>
        <button onClick={() => {
          getPageInfo().then(setPageInfo);
          getConsoleLogs().then(setConsoleLogs);
          getNetworkLogs().then(setNetworkLogs);
          getElementLogs().then(setElementLogs);
        }}>
          刷新日志
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

          <div className="element-logs">
            <h3>元素日志</h3>
            <pre>{JSON.stringify(elementLogs, null, 2)}</pre>
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
        .network-logs,
        .element-logs {
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