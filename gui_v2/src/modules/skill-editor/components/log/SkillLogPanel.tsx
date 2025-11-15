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
  user-select: none;
`;

const CollapseHandle = styled.div`
  width: 120px;
  height: 20px;
  border-radius: 6px;
  background: #111;
  color: #ffd400;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.8;
  margin: 4px auto;
`;

const Panel = styled.div<{ height: number }>`
  position: relative;
  width: 100%;
  height: ${(p) => p.height}px;
  background: #000;
  border-top: 1px solid #222;
  display: flex;
  flex-direction: column;
`;

const DragBar = styled.div`
  height: 6px;
  cursor: ns-resize;
  background: #222;
  &:hover { background: #333; }
`;

const ScrollArea = styled.div`
  flex: 1;
  overflow: auto;
  padding: 8px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.4;
  color: #ffd400;
`;

const Line = styled.div<{ kind: LogEntry['type'] }>`
  white-space: pre-wrap;
  word-break: break-word;
  color: ${(p) => (p.kind === 'error' ? '#ff6b6b' : p.kind === 'warning' ? '#f3da7a' : '#ffd400')};
`;

const Icon = styled.span<{ kind: LogEntry['type'] }>`
  display: inline-block;
  width: 16px;
  text-align: center;
  margin-right: 6px;
  color: ${(p) => (p.kind === 'error' ? '#ff6b6b' : p.kind === 'warning' ? '#f3db7b' : '#ffd400')};
`;

export const SkillLogPanel: React.FC = () => {
  const [open, setOpen] = React.useState(false);
  const [height, setHeight] = React.useState(200);
  const [logs, setLogs] = React.useState<LogEntry[]>([]);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

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

  return (
    <Container>
      {!open && (
        <CollapseHandle onClick={() => setOpen(true)}>
          ▲ Logs
        </CollapseHandle>
      )}
      {open && (
        <Panel height={height}>
          <DragBar onMouseDown={(e) => onDownRef.current(e)} />
          <ScrollArea ref={scrollRef}>
            {logs.map((l, i) => {
              const iconChar = l.type === 'error' ? '⛔' : l.type === 'warning' ? '⚠' : '●';
              return (
                <Line key={i} kind={l.type}>
                  <Icon kind={l.type}>{iconChar}</Icon>
                  [{new Date(l.timestamp || Date.now()).toLocaleTimeString()}] {l.text}
                </Line>
              );
            })}
          </ScrollArea>
          <CollapseHandle onClick={() => setOpen(false)}>
            ▼ Hide Logs
          </CollapseHandle>
        </Panel>
      )}
    </Container>
  );
};
