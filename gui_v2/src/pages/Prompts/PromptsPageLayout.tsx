import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, Tooltip } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface PromptsPageLayoutProps {
  /** The collapsible prompt list (left column). */
  listContent: React.ReactNode;
  /**
   * The editor/preview pane (already arranged side-by-side internally
   * by PromptsDetail when `splitLayout` is on).
   */
  detailsContent: React.ReactNode;
  /** The bottom chat panel (PromptAgentChat). */
  chatContent: React.ReactNode;
  /**
   * Title displayed in the details card header (e.g. selected prompt title).
   */
  detailsTitle?: React.ReactNode;
}

// ---------------------------------------------------------------------------
// localStorage keys — keep them grouped here so they survive renames.
// ---------------------------------------------------------------------------
const LS_LIST_COLLAPSED = 'prompts:layout:listCollapsed';
const LS_CHAT_COLLAPSED = 'prompts:layout:chatCollapsed';
const LS_CHAT_HEIGHT = 'prompts:layout:chatHeight';
const LS_LIST_WIDTH = 'prompts:layout:listWidth';

const DEFAULT_LIST_WIDTH = 300;
const MIN_LIST_WIDTH = 220;
const MAX_LIST_WIDTH = 520;

const DEFAULT_CHAT_HEIGHT = 260;
const MIN_CHAT_HEIGHT = 120;
const MAX_CHAT_HEIGHT = 600;

/**
 * Page-level layout for the Prompts editor.
 *
 * Replaces the generic `DetailLayout` for this page because we need
 * three regions instead of two:
 *
 *   ┌─────────────────────────────────────────────┐
 *   │ [list] │  editor    │ preview    (top row)  │
 *   │        │ ─────────────────────              │
 *   │        │  prompt-agent chat  (bottom row)   │
 *   └─────────────────────────────────────────────┘
 *
 * The list column is hide-able via a floating chevron at the top-left.
 * The chat panel is hide-able via the chevron in its header (and the
 * floating button at top-right when collapsed).
 *
 * Both collapse states + the two splitter widths are persisted in
 * localStorage so a returning user lands back in their preferred
 * layout.
 */
const PromptsPageLayout: React.FC<PromptsPageLayoutProps> = ({
  listContent,
  detailsContent,
  chatContent,
  detailsTitle,
}) => {
  const { t } = useTranslation();

  // ─── Collapse states ──────────────────────────────────────────────
  const [listCollapsed, setListCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_LIST_COLLAPSED) === '1';
    } catch {
      return false;
    }
  });
  const [chatCollapsed, setChatCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_CHAT_COLLAPSED) === '1';
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(LS_LIST_COLLAPSED, listCollapsed ? '1' : '0');
    } catch {}
  }, [listCollapsed]);
  useEffect(() => {
    try {
      localStorage.setItem(LS_CHAT_COLLAPSED, chatCollapsed ? '1' : '0');
    } catch {}
  }, [chatCollapsed]);

  // ─── List width drag-resize ───────────────────────────────────────
  const [listWidth, setListWidth] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(LS_LIST_WIDTH);
      const v = raw ? Number(raw) : NaN;
      if (Number.isFinite(v)) return Math.min(MAX_LIST_WIDTH, Math.max(MIN_LIST_WIDTH, v));
    } catch {}
    return DEFAULT_LIST_WIDTH;
  });
  const listDraggingRef = useRef(false);
  const listDragStartXRef = useRef(0);
  const listDragStartWRef = useRef(0);
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!listDraggingRef.current) return;
      const dx = e.clientX - listDragStartXRef.current;
      const next = Math.min(
        MAX_LIST_WIDTH,
        Math.max(MIN_LIST_WIDTH, listDragStartWRef.current + dx)
      );
      setListWidth(next);
    };
    const onUp = () => {
      if (!listDraggingRef.current) return;
      listDraggingRef.current = false;
      try {
        localStorage.setItem(LS_LIST_WIDTH, String(listWidth));
      } catch {}
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [listWidth]);

  // ─── Chat height drag-resize ──────────────────────────────────────
  const [chatHeight, setChatHeight] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(LS_CHAT_HEIGHT);
      const v = raw ? Number(raw) : NaN;
      if (Number.isFinite(v))
        return Math.min(MAX_CHAT_HEIGHT, Math.max(MIN_CHAT_HEIGHT, v));
    } catch {}
    return DEFAULT_CHAT_HEIGHT;
  });
  const chatDraggingRef = useRef(false);
  const chatDragStartYRef = useRef(0);
  const chatDragStartHRef = useRef(0);
  const detailsHostRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!chatDraggingRef.current) return;
      // Dragging UP increases chat height (chat lives at the bottom).
      const dy = chatDragStartYRef.current - e.clientY;
      const next = Math.min(
        MAX_CHAT_HEIGHT,
        Math.max(MIN_CHAT_HEIGHT, chatDragStartHRef.current + dy)
      );
      setChatHeight(next);
    };
    const onUp = () => {
      if (!chatDraggingRef.current) return;
      chatDraggingRef.current = false;
      try {
        localStorage.setItem(LS_CHAT_HEIGHT, String(chatHeight));
      } catch {}
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [chatHeight]);

  const startChatDrag = useCallback(
    (e: React.MouseEvent) => {
      chatDraggingRef.current = true;
      chatDragStartYRef.current = e.clientY;
      chatDragStartHRef.current = chatHeight;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    },
    [chatHeight]
  );

  const startListDrag = useCallback(
    (e: React.MouseEvent) => {
      listDraggingRef.current = true;
      listDragStartXRef.current = e.clientX;
      listDragStartWRef.current = listWidth;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    },
    [listWidth]
  );

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'row',
        height: '100%',
        gap: 0,
        position: 'relative',
      }}
    >
      {/* ─── List column (hide-able) ───────────────────────────────── */}
      {!listCollapsed && (
        <>
          <Card
            variant="borderless"
            style={{ width: listWidth, height: '100%', display: 'flex', flexDirection: 'column' }}
            styles={{
              body: {
                flex: '1 1 0',
                minHeight: 0,
                overflow: 'hidden',
                padding: 0,
                display: 'flex',
                flexDirection: 'column',
              },
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Inline header with a fold button — saves vertical space. */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  padding: '4px 8px 0 8px',
                }}
              >
                <Tooltip
                  title={t('pages.prompts.layout.collapseList', {
                    defaultValue: 'Hide prompt list',
                  })}
                  placement="bottomLeft"
                >
                  <Button
                    type="text"
                    size="small"
                    icon={<MenuFoldOutlined />}
                    onClick={() => setListCollapsed(true)}
                    style={{ color: 'rgba(255,255,255,0.7)' }}
                  />
                </Tooltip>
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>{listContent}</div>
            </div>
          </Card>
          {/* Vertical splitter between list and details */}
          <div
            onMouseDown={startListDrag}
            style={{
              width: 6,
              cursor: 'col-resize',
              flex: '0 0 auto',
              background: 'transparent',
              position: 'relative',
            }}
            title={t('pages.prompts.layout.dragToResizeList', {
              defaultValue: 'Drag to resize list',
            })}
          >
            <div
              style={{
                position: 'absolute',
                left: '50%',
                top: 8,
                bottom: 8,
                width: 2,
                transform: 'translateX(-50%)',
                background: 'rgba(148,163,184,0.18)',
                borderRadius: 1,
              }}
            />
          </div>
        </>
      )}

      {/* ─── Details column: [editor | preview] on top, chat at bottom ─── */}
      <div
        ref={detailsHostRef}
        style={{
          flex: 1,
          minWidth: 0,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}
      >
        {/* Floating chevron when list is collapsed — re-shows the list. */}
        {listCollapsed && (
          <Tooltip
            title={t('pages.prompts.layout.expandList', {
              defaultValue: 'Show prompt list',
            })}
            placement="bottomRight"
          >
            <Button
              type="primary"
              size="small"
              icon={<MenuUnfoldOutlined />}
              onClick={() => setListCollapsed(false)}
              style={{
                position: 'absolute',
                top: 8,
                left: 8,
                zIndex: 100,
                boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
              }}
            />
          </Tooltip>
        )}

        <Card
          variant="borderless"
          title={detailsTitle}
          style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
          styles={{
            body: {
              flex: '1 1 0',
              minHeight: 0,
              overflow: 'hidden',
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
            },
          }}
        >
          {detailsContent}
        </Card>

        {/* ─── Chat panel (bottom, hide-able) ────────────────────── */}
        {!chatCollapsed ? (
          <>
            {/* Horizontal drag handle. */}
            <div
              onMouseDown={startChatDrag}
              style={{
                height: 6,
                cursor: 'row-resize',
                flex: '0 0 auto',
                background: 'rgba(148, 163, 184, 0.18)',
                position: 'relative',
              }}
              title={t('pages.prompts.layout.dragToResizeChat', {
                defaultValue: 'Drag to resize chat',
              })}
            >
              <div
                style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  width: 40,
                  height: 2,
                  background: 'rgba(148,163,184,0.55)',
                  borderRadius: 1,
                }}
              />
            </div>
            <div
              style={{
                height: chatHeight,
                flex: '0 0 auto',
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
              }}
            >
              {/* Collapse-chevron stuck on the chat header area. */}
              <Tooltip
                title={t('pages.prompts.layout.collapseChat', {
                  defaultValue: 'Hide chat panel',
                })}
                placement="topRight"
              >
                <Button
                  type="text"
                  size="small"
                  icon={<DownOutlined />}
                  onClick={() => setChatCollapsed(true)}
                  style={{
                    position: 'absolute',
                    top: 4,
                    right: 8,
                    zIndex: 5,
                    color: 'rgba(255,255,255,0.7)',
                  }}
                />
              </Tooltip>
              {chatContent}
            </div>
          </>
        ) : (
          /* Collapsed chat → slim bar to re-expand. */
          <div
            onClick={() => setChatCollapsed(false)}
            style={{
              flex: '0 0 auto',
              height: 28,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              borderTop: '1px solid rgba(148, 163, 184, 0.2)',
              background: 'rgba(30, 41, 59, 0.65)',
              color: 'rgba(148,163,184,0.8)',
              fontSize: 12,
            }}
          >
            <MessageOutlined />
            <span>
              {t('pages.prompts.layout.expandChat', {
                defaultValue: 'Show prompt agent chat',
              })}
            </span>
            <UpOutlined style={{ fontSize: 10 }} />
          </div>
        )}
      </div>
    </div>
  );
};

export default PromptsPageLayout;
