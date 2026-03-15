/**
 * TextareaAutoComplete
 *
 * Attaches to all textareas inside a container ref and provides:
 * 1. Variable snippet dropdown when typing "{{" — instant, local
 * 2. LLM ghost text overlay — async, shown as greyed-out text after cursor, accept with Tab
 *
 * Usage: <TextareaAutoComplete containerRef={containerRef} promptName="my-prompt" />
 * Place this component inside the same container that holds the textareas.
 */

import React, { useEffect, useRef, useReducer } from 'react';
import ReactDOM from 'react-dom';
import {
  getVariableSnippets,
  requestPromptCompletion,
  cancelPromptCompletion,
  type SnippetItem,
} from '../../../services/promptCompletionService';

interface TextareaAutoCompleteProps {
  containerRef: React.RefObject<HTMLElement | null>;
  promptName?: string;
  disableGhostText?: boolean;
  ghostTextDelay?: number;
}

// ─── Styles ───

const DROPDOWN_STYLE: React.CSSProperties = {
  position: 'fixed',
  zIndex: 9999,
  background: 'rgba(30, 41, 59, 0.98)',
  border: '1px solid rgba(255, 255, 255, 0.15)',
  borderRadius: 8,
  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
  maxHeight: 220,
  overflowY: 'auto',
  minWidth: 220,
  padding: '4px 0',
};

const ITEM_STYLE: React.CSSProperties = {
  padding: '6px 12px',
  cursor: 'pointer',
  fontSize: 13,
  color: 'rgba(226, 232, 240, 0.9)',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
};

const ITEM_ACTIVE_BG = 'rgba(59, 130, 246, 0.25)';

const GHOST_STYLE: React.CSSProperties = {
  position: 'fixed',
  pointerEvents: 'none',
  zIndex: 9998,
  color: 'rgba(120, 160, 220, 0.85)',
  whiteSpace: 'pre-wrap',
  wordWrap: 'break-word',
  overflow: 'hidden',
  fontStyle: 'italic',
};

const GHOST_HINT_STYLE: React.CSSProperties = {
  position: 'fixed',
  zIndex: 9999,
  fontSize: 10,
  color: 'rgba(180, 200, 230, 0.9)',
  background: 'rgba(30, 41, 59, 0.9)',
  borderRadius: 4,
  padding: '1px 6px',
  pointerEvents: 'none',
};

// ─── Caret position measurement ───

function getCaretCoords(ta: HTMLTextAreaElement, pos: number): { top: number; left: number } {
  const mirror = document.createElement('div');
  const cs = window.getComputedStyle(ta);
  const props = [
    'position:absolute', 'visibility:hidden', 'white-space:pre-wrap', 'word-wrap:break-word',
    `width:${ta.clientWidth}px`,
    `font:${cs.font}`, `font-size:${cs.fontSize}`, `line-height:${cs.lineHeight}`,
    `padding:${cs.padding}`, `border:${cs.border}`, `letter-spacing:${cs.letterSpacing}`,
    `tab-size:${cs.tabSize || '8'}`,
  ];
  mirror.style.cssText = props.join(';');

  // Use createTextNode so special chars are escaped properly
  const textNode = document.createTextNode(ta.value.substring(0, pos));
  mirror.appendChild(textNode);
  const span = document.createElement('span');
  span.textContent = '\u200b'; // zero-width space for measurement
  mirror.appendChild(span);
  document.body.appendChild(mirror);

  const rect = ta.getBoundingClientRect();
  const top = span.offsetTop - ta.scrollTop + rect.top;
  const left = span.offsetLeft - ta.scrollLeft + rect.left;
  document.body.removeChild(mirror);
  return { top, left };
}

// ─── Insert text into a React-controlled textarea ───

function insertIntoTextarea(ta: HTMLTextAreaElement, start: number, end: number, text: string) {
  const before = ta.value.substring(0, start);
  const after = ta.value.substring(end);
  const newValue = before + text + after;
  const newPos = start + text.length;

  // Use the native setter so React sees the change
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (nativeSetter) {
    nativeSetter.call(ta, newValue);
  }
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  ta.dispatchEvent(new Event('change', { bubbles: true }));

  requestAnimationFrame(() => {
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(newPos, newPos);
  });
}

// ─── Component ───

const TextareaAutoComplete: React.FC<TextareaAutoCompleteProps> = ({
  containerRef,
  promptName,
  disableGhostText = false,
  ghostTextDelay = 800,
}) => {
  // Force re-render helper — all mutable state is in refs to avoid stale closures
  const [, forceUpdate] = useReducer((c: number) => c + 1, 0);

  // Refs holding all mutable state (never stale in event handlers)
  const stateRef = useRef({
    snippets: [] as SnippetItem[],
    dropdownPos: null as { top: number; left: number } | null,
    activeIdx: 0,
    triggerTA: null as HTMLTextAreaElement | null,
    triggerStart: 0,
    ghostText: '',
    ghostPos: null as { top: number; left: number } | null,
    ghostTA: null as HTMLTextAreaElement | null,
    lastGhostPrefix: '',
  });

  const ghostTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const promptNameRef = useRef(promptName);
  promptNameRef.current = promptName;

  const disableGhostRef = useRef(disableGhostText);
  disableGhostRef.current = disableGhostText;

  const ghostDelayRef = useRef(ghostTextDelay);
  ghostDelayRef.current = ghostTextDelay;

  // Helper to update ref + re-render
  const updateState = (patch: Partial<typeof stateRef.current>) => {
    Object.assign(stateRef.current, patch);
    forceUpdate();
  };

  const dismissGhost = () => {
    cancelPromptCompletion();
    if (ghostTimerRef.current) { clearTimeout(ghostTimerRef.current); ghostTimerRef.current = null; }
    updateState({ ghostText: '', ghostPos: null, ghostTA: null });
  };

  const closeDropdown = () => {
    updateState({ snippets: [], dropdownPos: null, triggerTA: null, triggerStart: 0 });
  };

  // ─── Attach listeners once ───
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Use 'keyup' instead of 'input' for the {{ detection — fires after React has
    // reconciled the controlled value, so ta.value is always up to date.
    const handleKeyUp = (e: KeyboardEvent) => {
      const ta = e.target as HTMLElement;
      if (ta.tagName !== 'TEXTAREA') return;
      const textarea = ta as HTMLTextAreaElement;

      // Schedule a microtask so React has fully flushed the controlled value
      setTimeout(() => processInput(textarea), 0);
    };

    const processInput = (ta: HTMLTextAreaElement) => {
      const s = stateRef.current;
      const pos = ta.selectionStart;
      const text = ta.value;

      // Check for "{{" trigger
      const lookback = text.substring(Math.max(0, pos - 30), pos);
      const braceIdx = lookback.lastIndexOf('{{');
      if (braceIdx >= 0) {
        const filterStart = Math.max(0, pos - 30) + braceIdx + 2;
        const filter = text.substring(filterStart, pos);
        if (!filter.includes('}}') && !filter.includes('\n')) {
          const items = getVariableSnippets(filter);
          if (items.length > 0) {
            const coords = getCaretCoords(ta, pos);
            updateState({
              snippets: items,
              dropdownPos: { top: coords.top + 22, left: coords.left },
              activeIdx: 0,
              triggerTA: ta,
              triggerStart: filterStart - 2,
            });
            // Dismiss ghost while snippet dropdown is open
            if (s.ghostText) dismissGhost();
            return;
          }
        }
      }

      // No snippet trigger — close dropdown if open
      if (s.snippets.length > 0) closeDropdown();

      // Request ghost text (debounced LLM call)
      if (!disableGhostRef.current) {
        const prefix = text.substring(0, pos);
        const suffix = text.substring(pos);
        if (prefix === s.lastGhostPrefix) return;
        stateRef.current.lastGhostPrefix = prefix;

        if (prefix.trim().length < 10) { dismissGhost(); return; }

        if (ghostTimerRef.current) clearTimeout(ghostTimerRef.current);
        ghostTimerRef.current = setTimeout(async () => {
          const completion = await requestPromptCompletion({
            prefix: prefix.slice(-2000),
            suffix: suffix.slice(0, 500),
            prompt_name: promptNameRef.current,
            max_tokens: 80,
            temperature: 0.3,
          });
          // Only show if cursor hasn't moved since request
          if (completion && ta.selectionStart === pos && ta.value.substring(0, pos) === prefix) {
            const coords = getCaretCoords(ta, pos);
            updateState({ ghostText: completion, ghostPos: coords, ghostTA: ta });
          }
        }, ghostDelayRef.current);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName !== 'TEXTAREA') return;
      const s = stateRef.current;

      // ─── Snippet dropdown keyboard ───
      if (s.snippets.length > 0 && s.dropdownPos) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          updateState({ activeIdx: (s.activeIdx + 1) % s.snippets.length });
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          updateState({ activeIdx: (s.activeIdx - 1 + s.snippets.length) % s.snippets.length });
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          const snippet = s.snippets[s.activeIdx];
          if (snippet && s.triggerTA) {
            const cursorPos = s.triggerTA.selectionStart;
            insertIntoTextarea(s.triggerTA, s.triggerStart, cursorPos, snippet.insertText);
          }
          closeDropdown();
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          closeDropdown();
          return;
        }
      }

      // ─── Ghost text keyboard ───
      if (s.ghostText && s.ghostPos && s.ghostTA) {
        if (e.key === 'Tab') {
          e.preventDefault();
          const pos = s.ghostTA.selectionStart;
          insertIntoTextarea(s.ghostTA, pos, pos, s.ghostText);
          dismissGhost();
          return;
        }
        if (e.key === 'Escape') {
          dismissGhost();
          return;
        }
        // Any typing dismisses ghost (will re-request after debounce)
        if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') {
          dismissGhost();
        }
      }
    };

    const handleBlur = (e: Event) => {
      if ((e.target as HTMLElement).tagName !== 'TEXTAREA') return;
      setTimeout(() => {
        closeDropdown();
        dismissGhost();
      }, 250);
    };

    // Use capture phase so we get the event before Ant Design's handlers
    container.addEventListener('keyup', handleKeyUp, true);
    container.addEventListener('keydown', handleKeyDown, true);
    container.addEventListener('focusout', handleBlur, true);

    return () => {
      container.removeEventListener('keyup', handleKeyUp, true);
      container.removeEventListener('keydown', handleKeyDown, true);
      container.removeEventListener('focusout', handleBlur, true);
      if (ghostTimerRef.current) clearTimeout(ghostTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef]); // Only re-attach if containerRef changes

  // ─── Render overlays via portal (so they escape any overflow:hidden) ───
  const s = stateRef.current;

  const overlay = (
    <>
      {/* Variable snippet dropdown */}
      {s.dropdownPos && s.snippets.length > 0 && (
        <div style={{ ...DROPDOWN_STYLE, top: s.dropdownPos.top, left: s.dropdownPos.left }}>
          {s.snippets.map((item, i) => (
            <div
              key={item.label}
              style={{
                ...ITEM_STYLE,
                background: i === s.activeIdx ? ITEM_ACTIVE_BG : 'transparent',
              }}
              onMouseEnter={() => updateState({ activeIdx: i })}
              onMouseDown={(e) => {
                e.preventDefault();
                if (s.triggerTA) {
                  const cursorPos = s.triggerTA.selectionStart;
                  insertIntoTextarea(s.triggerTA, s.triggerStart, cursorPos, item.insertText);
                }
                closeDropdown();
              }}
            >
              <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                {'{{'}
                {item.label}
                {'}}'}
              </span>
              {item.description && (
                <span style={{ fontSize: 11, color: 'rgba(148, 163, 184, 0.7)' }}>
                  {item.description}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Ghost text overlay */}
      {s.ghostPos && s.ghostText && s.ghostTA && (
        <>
          <span
            style={{
              ...GHOST_STYLE,
              top: s.ghostPos.top,
              left: s.ghostPos.left,
              font: window.getComputedStyle(s.ghostTA).font,
              fontSize: window.getComputedStyle(s.ghostTA).fontSize,
              lineHeight: window.getComputedStyle(s.ghostTA).lineHeight,
              maxWidth: Math.max(100, s.ghostTA.clientWidth - (s.ghostPos.left - s.ghostTA.getBoundingClientRect().left)),
            }}
          >
            {s.ghostText}
          </span>
          <span
            style={{
              ...GHOST_HINT_STYLE,
              top: s.ghostPos.top - 16,
              left: s.ghostPos.left,
            }}
          >
            Tab ⇥ accept
          </span>
        </>
      )}
    </>
  );

  return ReactDOM.createPortal(overlay, document.body);
};

export default TextareaAutoComplete;
