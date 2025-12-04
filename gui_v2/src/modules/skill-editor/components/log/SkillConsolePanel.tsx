import React from 'react';
import styled from 'styled-components';
import { eventBus } from '@/utils/eventBus';

interface LogEntry {
  type: 'log' | 'warning' | 'error';
  text: string;
  timestamp?: number;
}

const Container = styled.div`
  position: relative;
  width: 100%;
  user-select: text;
`;

// Chrome DevTools style collapse handle
const CollapseHandle = styled.div<{ $expanded?: boolean }>`
  height: 28px;
  background: linear-gradient(180deg, #3c3c3c 0%, #2d2d2d 100%);
  border-top: 1px solid #4a4a4a;
  border-bottom: 1px solid #1a1a1a;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  cursor: pointer;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 12px;
  color: #cccccc;
  gap: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  position: relative;
  
  &:hover {
    background: linear-gradient(180deg, #454545 0%, #363636 100%);
  }
  
  .console-icon {
    font-size: 14px;
    color: #569cd6;
  }
  
  .title {
    font-weight: 500;
    color: #e0e0e0;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  
  .counts {
    display: flex;
    gap: 6px;
    margin-left: 8px;
  }
  
  .count {
    background: #3c4043;
    color: #9aa0a6;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
  }
  
  .error-count {
    background: #5c2b29;
    color: #f28b82;
  }
  
  .warning-count {
    background: #4a3f24;
    color: #fdd663;
  }
  
  .close-btn {
    position: absolute;
    right: 12px;
    font-size: 16px;
    color: #888;
    padding: 2px 6px;
    border-radius: 3px;
    line-height: 1;
    
    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #e0e0e0;
    }
  }
`;

const Panel = styled.div<{ height: number }>`
  position: relative;
  width: 100%;
  height: ${(p) => p.height}px;
  background: #1e1e1e;
  display: flex;
  flex-direction: column;
`;

const DragBar = styled.div`
  height: 4px;
  cursor: ns-resize;
  background: #3c3c3c;
  &:hover { background: #4a4a4a; }
  &:active { background: #5a5a5a; }
`;

const Toolbar = styled.div`
  height: 28px;
  background: #252526;
  border-bottom: 1px solid #3c3c3c;
  display: flex;
  align-items: center;
  padding: 0 8px;
  gap: 8px;
  
  .clear-btn {
    font-size: 11px;
    color: #9aa0a6;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 3px;
    
    &:hover {
      background: #3c3c3c;
      color: #e8eaed;
    }
  }
  
  .filter-tabs {
    display: flex;
    gap: 2px;
    margin-left: auto;
  }
  
  .filter-tab {
    font-size: 11px;
    color: #9aa0a6;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    
    &:hover {
      background: #3c3c3c;
    }
    
    &.active {
      background: #3c3c3c;
      color: #e8eaed;
    }
  }
`;

const ScrollArea = styled.div`
  flex: 1;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
`;

const Line = styled.div<{ kind: LogEntry['type'] }>`
  padding: 4px 8px 4px 28px;
  border-bottom: 1px solid #2a2a2a;
  position: relative;
  white-space: pre-wrap;
  word-break: break-word;
  cursor: text;
  user-select: text;
  
  background: ${(p) => 
    p.kind === 'error' ? 'rgba(242, 139, 130, 0.1)' : 
    p.kind === 'warning' ? 'rgba(253, 214, 99, 0.1)' : 
    'transparent'
  };
  
  color: ${(p) => 
    p.kind === 'error' ? '#f28b82' : 
    p.kind === 'warning' ? '#fdd663' : 
    '#e8eaed'
  };
  
  &:hover {
    background: ${(p) => 
      p.kind === 'error' ? 'rgba(242, 139, 130, 0.15)' : 
      p.kind === 'warning' ? 'rgba(253, 214, 99, 0.15)' : 
      '#2a2a2a'
    };
  }
  
  .timestamp {
    color: #6e6e6e;
    font-size: 11px;
    margin-right: 8px;
    user-select: text;
  }
  
  .log-text {
    user-select: text;
  }
`;

const Icon = styled.span<{ kind: LogEntry['type'] }>`
  position: absolute;
  left: 8px;
  top: 5px;
  font-size: 12px;
  color: ${(p) => 
    p.kind === 'error' ? '#f28b82' : 
    p.kind === 'warning' ? '#fdd663' : 
    '#81c995'
  };
`;

export const SkillConsolePanel: React.FC = () => {
  const [open, setOpen] = React.useState(false);
  const [height, setHeight] = React.useState(200);
  const [logs, setLogs] = React.useState<LogEntry[]>([]);
  const [filter, setFilter] = React.useState<'all' | 'error' | 'warning' | 'log'>('all');
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  // Count logs by type
  const counts = React.useMemo(() => {
    const result = { error: 0, warning: 0, log: 0 };
    logs.forEach(l => result[l.type]++);
    return result;
  }, [logs]);

  // Filtered logs
  const filteredLogs = React.useMemo(() => {
    if (filter === 'all') return logs;
    return logs.filter(l => l.type === filter);
  }, [logs, filter]);

  React.useEffect(() => {
    const handler = (entry: LogEntry) => {
      setLogs((prev) => [...prev, entry]);
      if (!open) setOpen(true);
      // autoscroll on next frame
      requestAnimationFrame(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      });
    };
    eventBus.on('skill-editor:log', handler);
    return () => { eventBus.off('skill-editor:log', handler); };
  }, [open]);

  // drag resize
  React.useEffect(() => {
    let startY = 0;
    let startH = 0;
    const onMove = (e: MouseEvent) => {
      const dy = startY - e.clientY; // dragging up increases height
      const next = Math.max(100, Math.min(window.innerHeight * 0.9, startH + dy));
      setHeight(next);
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    const onDown = (e: React.MouseEvent) => {
      startY = e.clientY;
      startH = height;
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    };
    // store onDown for use in JSX via ref to avoid re-binding
    (onDownRef as any).current = onDown;
  }, [height]);

  const onDownRef = React.useRef<(e: React.MouseEvent) => void>(() => {});

  const clearLogs = () => setLogs([]);

  const copyAllLogs = async () => {
    const text = filteredLogs.map(l => {
      const time = new Date(l.timestamp || Date.now()).toLocaleTimeString();
      const prefix = l.type === 'error' ? '[ERROR]' : l.type === 'warning' ? '[WARN]' : '[LOG]';
      return `${time} ${prefix} ${l.text}`;
    }).join('\n');
    
    try {
      await navigator.clipboard.writeText(text);
      // Could show a toast notification here
    } catch (err) {
      console.error('Failed to copy logs:', err);
    }
  };

  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen(false);
  };

  return (
    <Container>
      {/* Collapse handle - always visible */}
      <CollapseHandle $expanded={open} onClick={() => setOpen(!open)}>
        <span className="console-icon">⌘</span>
        <span className="title">Console</span>
        {logs.length > 0 && (
          <div className="counts">
            {counts.error > 0 && <span className="count error-count">{counts.error} errors</span>}
            {counts.warning > 0 && <span className="count warning-count">{counts.warning} warnings</span>}
            {counts.log > 0 && <span className="count">{counts.log} logs</span>}
          </div>
        )}
        {open && (
          <span className="close-btn" onClick={handleClose} title="Close Console">×</span>
        )}
      </CollapseHandle>
      
      {open && (
        <Panel height={height}>
          <DragBar onMouseDown={(e) => onDownRef.current(e)} />
          <Toolbar>
            <span className="clear-btn" onClick={clearLogs}>🚫 Clear</span>
            <span className="clear-btn" onClick={copyAllLogs} title="Copy all logs">📋 Copy</span>
            <div className="filter-tabs">
              <span 
                className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                All
              </span>
              <span 
                className={`filter-tab ${filter === 'error' ? 'active' : ''}`}
                onClick={() => setFilter('error')}
              >
                Errors {counts.error > 0 && `(${counts.error})`}
              </span>
              <span 
                className={`filter-tab ${filter === 'warning' ? 'active' : ''}`}
                onClick={() => setFilter('warning')}
              >
                Warnings {counts.warning > 0 && `(${counts.warning})`}
              </span>
            </div>
          </Toolbar>
          <ScrollArea ref={scrollRef}>
            {filteredLogs.length === 0 ? (
              <div style={{ padding: '20px', color: '#6e6e6e', textAlign: 'center' }}>
                No logs to display
              </div>
            ) : (
              filteredLogs.map((l, i) => {
                const iconChar = l.type === 'error' ? '✕' : l.type === 'warning' ? '⚠' : '●';
                return (
                  <Line key={i} kind={l.type}>
                    <Icon kind={l.type}>{iconChar}</Icon>
                    <span className="timestamp">
                      {new Date(l.timestamp || Date.now()).toLocaleTimeString()}
                    </span>
                    <span className="log-text">{l.text}</span>
                  </Line>
                );
              })
            )}
          </ScrollArea>
        </Panel>
      )}
    </Container>
  );
};
