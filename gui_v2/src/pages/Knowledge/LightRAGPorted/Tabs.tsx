import React, { useEffect, useState, useRef } from 'react';
import { theme } from 'antd';
import { FileTextOutlined, ShareAltOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import { useTranslation } from 'react-i18next';
import WorkspacePicker from './WorkspacePicker';
import StatusIndicator from './StatusIndicator';
import { useWorkspace } from './useWorkspace';

// Minimal tabs component for the ported LightRAG UI.
// Does not depend on Radix or Tailwind; no routing changes.

export type TabKey = 'documents' | 'knowledge-graph' | 'retrieval' | 'settings' | 'api';

interface TabsProps {
  defaultActive?: TabKey;
  /**
   * Optional controlled active tab. When provided, the Tabs component becomes
   * controlled and mirrors this value into its internal state on every render.
   * Used by external flows (e.g. configuration warning modal) that need to
   * programmatically switch tabs without going through user click events.
   */
  active?: TabKey;
  onChange?: (key: TabKey) => void;
  renderTab: (key: TabKey) => React.ReactNode;
}

const Tabs: React.FC<TabsProps> = ({ defaultActive = 'documents', active: controlledActive, onChange, renderTab }) => {
  const storagePrefix = 'lightrag-ported:tabs';
  const [workspace, setWorkspace] = useWorkspace();

  const readActiveFromStorage = (): TabKey => {
    const raw = sessionStorage.getItem(`${storagePrefix}:active`);
    const key = raw as TabKey | null;
    if (key === 'documents' || key === 'knowledge-graph' || key === 'retrieval' || key === 'settings' || key === 'api') {
      return key;
    }
    return defaultActive;
  };

  const readVisitedFromStorage = (activeKey: TabKey): Set<TabKey> => {
    try {
      const raw = sessionStorage.getItem(`${storagePrefix}:visited`);
      if (!raw) return new Set([activeKey]);
      const arr = JSON.parse(raw) as TabKey[];
      const valid = arr.filter((k) => k === 'documents' || k === 'knowledge-graph' || k === 'retrieval' || k === 'settings' || k === 'api');
      const set = new Set<TabKey>(valid);
      set.add(activeKey);
      return set;
    } catch {
      return new Set([activeKey]);
    }
  };

  const [internalActive, setInternalActive] = useState<TabKey>(() => readActiveFromStorage());
  // When controlledActive is provided, mirror it into internal state. This lets
  // external flows (modal "前往设置" button, etc.) switch tabs programmatically
  // without breaking the existing uncontrolled click handler.
  const active = controlledActive !== undefined ? controlledActive : internalActive;
  const setActive = (key: TabKey) => {
    if (controlledActive === undefined) {
      setInternalActive(key);
    }
    sessionStorage.setItem(`${storagePrefix}:active`, key);
  };
  // Keep track of visited tabs to lazy-load them but keep them alive afterwards
  const [visited, setVisited] = useState<Set<TabKey>>(() => readVisitedFromStorage(readActiveFromStorage()));
  
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const scrollPositions = useRef<Map<TabKey, number>>(new Map());
  const tabRefs = useRef<Map<TabKey, HTMLDivElement>>(new Map());

  const isOuterScrollable = (key: TabKey) => {
    return key === 'documents' || key === 'knowledge-graph' || key === 'api';
  };

  const saveScrollPosition = (key: TabKey, scrollTop: number) => {
    scrollPositions.current.set(key, scrollTop);
    sessionStorage.setItem(`${storagePrefix}:scroll:${key}`, String(scrollTop));
  };

  const readScrollPosition = (key: TabKey): number => {
    const inMemory = scrollPositions.current.get(key);
    if (typeof inMemory === 'number') return inMemory;
    const raw = sessionStorage.getItem(`${storagePrefix}:scroll:${key}`);
    const num = raw ? Number(raw) : 0;
    return Number.isFinite(num) ? num : 0;
  };

  const emitTabEvent = (type: 'activate' | 'deactivate', key: TabKey) => {
    window.dispatchEvent(new CustomEvent(`lightrag-tab-${type}`, { detail: { key } }));
  };

  const restoreScrollWithRetry = (key: TabKey, attempts = 0) => {
    if (!isOuterScrollable(key)) return;
    const el = tabRefs.current.get(key);
    const saved = readScrollPosition(key);
    if (!el || saved <= 0) return;

    if (el.scrollHeight <= el.clientHeight && attempts < 12) {
      setTimeout(() => restoreScrollWithRetry(key, attempts + 1), 50);
      return;
    }

    el.scrollTop = saved;
  };

  useEffect(() => {
    sessionStorage.setItem(`${storagePrefix}:active`, active);
    sessionStorage.setItem(`${storagePrefix}:visited`, JSON.stringify(Array.from(visited)));
  }, [active, visited]);

  // 使用 ref 保存最新的 active 值，避免闭包问题
  const activeRef = useRef(active);
  activeRef.current = active;

  // 组件挂载时恢复滚动位置，卸载时保存滚动位置
  useEffect(() => {
    // 延迟执行，确保 DOM 已经渲染完成
    const timer = setTimeout(() => {
      emitTabEvent('activate', activeRef.current);
      restoreScrollWithRetry(activeRef.current);
    }, 100);
    
    // 组件卸载时保存滚动位置
    return () => {
      clearTimeout(timer);
      // 使用 ref 获取最新的 active 值
      const currentActive = activeRef.current;
      if (isOuterScrollable(currentActive)) {
        const el = tabRefs.current.get(currentActive);
        if (el) {
          saveScrollPosition(currentActive, el.scrollTop);
        }
      }
      emitTabEvent('deactivate', currentActive);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    emitTabEvent('activate', active);
    requestAnimationFrame(() => restoreScrollWithRetry(active));
    // Mark the tab as visited so it renders (covers programmatic switches,
    // e.g. when the configuration warning modal "goToSettings" callback fires
    // and the user hasn't clicked the Settings tab manually yet).
    setVisited(prev => {
      if (prev.has(active)) return prev;
      const next = new Set(prev);
      next.add(active);
      return next;
    });
    return () => {
      emitTabEvent('deactivate', active);
    };
  }, [active]);

  const handleClick = (key: TabKey) => {
    // 保存当前标签页的滚动位置
    if (isOuterScrollable(active)) {
      const currentTabElement = tabRefs.current.get(active);
      if (currentTabElement) {
        saveScrollPosition(active, currentTabElement.scrollTop);
      }
    }
    
    setActive(key);
    setVisited(prev => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    onChange?.(key);
  };
  
  // 设置 tab ref
  const setTabRef = (key: TabKey) => (el: HTMLDivElement | null) => {
    if (el) {
      tabRefs.current.set(key, el);
      if (key === active) {
        requestAnimationFrame(() => restoreScrollWithRetry(key));
      }
    } else {
      tabRefs.current.delete(key);
    }
  };

  // 使用主题 token 的背景色
  const tabBarBg = token.colorBgContainer;
  const contentBg = token.colorBgLayout;
  
  const tabKeys: TabKey[] = ['documents', 'knowledge-graph', 'retrieval', 'settings', 'api'];

  return (
    <div data-ec-scope="lightrag-ported" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        padding: '4px 24px 0',
        background: tabBarBg,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        position: 'relative',
        borderBottom: `1px solid ${token.colorBorderSecondary}`
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1, minWidth: 0, overflowX: 'auto' }}>
          <button className={`ec-tab ${active === 'documents' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('documents')}>
            <FileTextOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.tabs.documents')}
          </button>
          <button className={`ec-tab ${active === 'knowledge-graph' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('knowledge-graph')}>
            <ShareAltOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.tabs.knowledgeGraph')}
          </button>
          <button className={`ec-tab ${active === 'retrieval' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('retrieval')}>
            <SearchOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.tabs.retrieval')}
          </button>
          <button className={`ec-tab ${active === 'settings' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('settings')}>
            <SettingOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.tabs.settings')}
          </button>
          {/* API tab is present but invisible per requirement */}
          <button className={`ec-tab ${active === 'api' ? 'ec-tab-active' : ''}`} onClick={() => handleClick('api')} style={{ visibility: 'hidden' }}>API</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <WorkspacePicker
            value={workspace}
            onChange={setWorkspace}
            placeholder={t('pages.knowledge.lightrag.workspacePicker.serverDefault')}
          />
          <div
            style={{
              width: 1,
              height: 18,
              background: token.colorBorderSecondary,
              flexShrink: 0,
            }}
          />
          <StatusIndicator />
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', background: contentBg, position: 'relative' }}>
        {tabKeys.map(key => {
          if (!visited.has(key)) return null;
          return (
            <div 
              key={key}
              ref={setTabRef(key)}
              onScroll={(e) => {
                if (active === key && isOuterScrollable(key)) {
                  saveScrollPosition(key, e.currentTarget.scrollTop);
                }
              }}
              style={{ 
                position: 'absolute',
                top: 0,
                left: 0,
                height: '100%', 
                width: '100%', 
                visibility: active === key ? 'visible' : 'hidden',
                overflow: isOuterScrollable(key) ? 'auto' : 'hidden',
                pointerEvents: active === key ? 'auto' : 'none'
              }}
            >
              {renderTab(key)}
            </div>
          );
        })}
      </div>
      <style>{`
        @import url('./styles/lightragTheme.css');

        [data-ec-scope="lightrag-ported"] .ec-tab {
          background: transparent;
          border: none;
          cursor: pointer;
          padding: 10px 14px;
          font-size: 14px;
          font-weight: 500;
          color: ${token.colorTextSecondary};
          border-radius: 0;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          border-bottom: 3px solid transparent;
          letter-spacing: 0.3px;
          white-space: nowrap;
          flex-shrink: 0;
        }
        [data-ec-scope="lightrag-ported"] .ec-tab:hover {
          color: ${token.colorPrimary};
          background: ${isDark ? 'rgba(59, 130, 246, 0.1)' : 'rgba(59, 130, 246, 0.06)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-tab-active {
          color: ${token.colorPrimary};
          font-weight: 600;
          border-bottom-color: ${token.colorPrimary};
          background: transparent;
        }

        /* ===== Unified editable input styling across all tabs =====
           Goal: every editable control in any LightRAGPorted tab looks
           identical (same border, padding, radius, font-size, height)
           regardless of:
             - which tab (Documents / Retrieval / Settings)
             - which antd flavour (Input/TextArea/Password/Search/Number
               /Select/Cascader/TreeSelect/AutoComplete/DatePicker)
             - which antd variant (outlined/filled/borderless/underlined)
             - which size prop ('small' or default)

           antd v5.13+ adds the 'variant' API and emits suffix classes
           like ant-input-outlined, ant-input-number-handler-wrap,
           ant-select-selector-filled. A parent Form / ConfigProvider
           can flip the variant, which is what produced the original
           "some bordered, some not" inconsistency. We pin the box at
           the antd component-token level so every variant ends up
           looking the same.

           We deliberately keep the data-ec-scope guard so this never
           bleeds into Login / Onboarding / other pages. ===== */
        /* --- 1. Single source of truth: every editable wrapper gets the
              same border, radius, font-size, background. ---
              We list the base class AND every variant suffix. The list
              is long on purpose — better to over-include than to miss
              one and have a stray input render in the wrong style. */
        [data-ec-scope="lightrag-ported"] .ant-input,
        [data-ec-scope="lightrag-ported"] .ant-input-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-underlined,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea-underlined,
        [data-ec-scope="lightrag-ported"] .ant-input-password,
        [data-ec-scope="lightrag-ported"] .ant-input-password-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-password-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-password-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-search,
        [data-ec-scope="lightrag-ported"] .ant-input-search-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-search-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-search-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-otp,
        [data-ec-scope="lightrag-ported"] .ant-input-otp-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-otp-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-otp-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-number,
        [data-ec-scope="lightrag-ported"] .ant-input-number-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-number-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-number-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-number-underlined,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-borderless,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-underlined,
        [data-ec-scope="lightrag-ported"] .ant-input-group-wrapper,
        [data-ec-scope="lightrag-ported"] .ant-input-group-wrapper-outlined,
        [data-ec-scope="lightrag-ported"] .ant-input-group-wrapper-filled,
        [data-ec-scope="lightrag-ported"] .ant-input-group-wrapper-borderless,
        [data-ec-scope="lightrag-ported"] .ant-select,
        [data-ec-scope="lightrag-ported"] .ant-cascader-picker,
        [data-ec-scope="lightrag-ported"] .ant-tree-select,
        [data-ec-scope="lightrag-ported"] .ant-picker,
        [data-ec-scope="lightrag-ported"] .ant-picker-outlined,
        [data-ec-scope="lightrag-ported"] .ant-picker-filled,
        [data-ec-scope="lightrag-ported"] .ant-picker-borderless,
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer} !important;
          color: ${token.colorText} !important;
          border: 1px solid ${token.colorBorder} !important;
          border-radius: 8px !important;
          font-size: 13px !important;
          box-shadow: none !important;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
          box-sizing: border-box !important;
        }
        /* --- 2. Same height for every editable control. ---
              30px matches the visual baseline of a size="small" antd
              control; we override the size="default" controls too so a
              row of mixed-size fields aligns. */
        [data-ec-scope="lightrag-ported"] .ant-input,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper,
        [data-ec-scope="lightrag-ported"] .ant-input-password,
        [data-ec-scope="lightrag-ported"] .ant-input-number,
        [data-ec-scope="lightrag-ported"] .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker,
        [data-ec-scope="lightrag-ported"] .ec-input {
          /* height (not min-height) is needed: antd's default
             .ant-select-selector sets height: 40px which would
             inflate every control when min-height alone is used. */
          height: 30px !important;
          min-height: 30px !important;
          padding: 0 10px !important;
          line-height: 28px !important;
          box-sizing: border-box !important;
        }
        /* Input.Password has an extra native input nested inside the
           affix-wrapper; the nested input inherits the wrapper's
           padding which can stack. Reset to 0 so the wrapper's padding
           controls the layout, not double. */
        [data-ec-scope="lightrag-ported"] .ant-input-password > input.ant-input,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper > input.ant-input {
          padding: 0 !important;
          min-height: 0 !important;
          line-height: 22px !important;
          height: auto !important;
          background: transparent !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-input-number {
          width: 100% !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-input-number-input {
          height: 22px !important;
          padding: 0 10px !important;
          font-size: 13px !important;
        }
        /* TextArea is intentionally taller and has different padding
           than single-line inputs. Match antd's size="small" default
           so it stays consistent with surrounding rows. */
        [data-ec-scope="lightrag-ported"] .ant-input-textarea,
        [data-ec-scope="lightrag-ported"] textarea.ant-input {
          padding: 6px 10px !important;
          font-size: 13px !important;
          line-height: 20px !important;
          resize: vertical !important;
        }
        /* size="large" overrides — keep them taller (40px) so they
           remain visually distinct from regular fields when designers
           want emphasis. */
        [data-ec-scope="lightrag-ported"] .ant-input-lg,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-lg,
        [data-ec-scope="lightrag-ported"] .ant-input-number-lg,
        [data-ec-scope="lightrag-ported"] .ant-select-lg .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker.ant-picker-lg {
          min-height: 40px !important;
          padding: 6px 12px !important;
          font-size: 14px !important;
        }
        /* size="small" overrides — slightly shorter (24px) so they
           stay compact in dense rows like the workspace picker. */
        [data-ec-scope="lightrag-ported"] .ant-input-sm,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-sm,
        [data-ec-scope="lightrag-ported"] .ant-input-number-sm,
        [data-ec-scope="lightrag-ported"] .ant-select-sm .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker.ant-picker-sm {
          height: 24px !important;
          min-height: 24px !important;
          padding: 0 8px !important;
          font-size: 12px !important;
          line-height: 22px !important;
        }
        /* --- 3. Select: the wrapper IS the bordered box.
              The selector inside is borderless + transparent and fills
              the wrapper; the arrow sits at the right edge inside the
              same border. This makes the arrow visually part of the
              control instead of a separate floating chevron. */
        [data-ec-scope="lightrag-ported"] .ant-select {
          font-size: 13px !important;
          display: flex !important;
          align-items: stretch !important;
          height: 30px !important;
          min-height: 30px !important;
          padding: 0 !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-select-sm {
          height: 24px !important;
          min-height: 24px !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-select-lg {
          height: 40px !important;
          min-height: 40px !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-select .ant-select-selector {
          /* Fills the wrapper; no own border, no own background. */
          border: none !important;
          background: transparent !important;
          box-shadow: none !important;
          display: flex !important;
          align-items: center !important;
          flex: 1 !important;
          min-width: 0 !important;
          height: 100% !important;
          min-height: 0 !important;
          padding: 0 8px 0 10px !important;
        }
        /* Placeholder / selected item: vertically centered, truncated */
        [data-ec-scope="lightrag-ported"] .ant-select-single .ant-select-selector .ant-select-selection-item,
        [data-ec-scope="lightrag-ported"] .ant-select-single .ant-select-selector .ant-select-selection-placeholder {
          line-height: 22px !important;
          height: 22px !important;
          padding: 0 !important;
          margin: 0 !important;
          display: flex !important;
          align-items: center !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
          white-space: nowrap !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-select-single .ant-select-selector .ant-select-selection-search,
        [data-ec-scope="lightrag-ported"] .ant-select-single .ant-select-selector .ant-select-selection-search-input {
          height: 22px !important;
          line-height: 22px !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-select-multiple .ant-select-selection-item {
          line-height: 18px !important;
          height: 20px !important;
          align-self: center !important;
        }
        /* Arrow: a flex child of the wrapper, sitting at the right edge
           INSIDE the same border as the selector. */
        [data-ec-scope="lightrag-ported"] .ant-select .ant-select-arrow {
          align-self: center !important;
          position: static !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
          transform: none !important;
          margin: 0 !important;
          padding: 0 10px 0 4px !important;
          height: auto !important;
          line-height: 1 !important;
        }
        /* --- 4. Hover / focus affordance: same for every input type. --- */
        [data-ec-scope="lightrag-ported"] .ant-input:not([disabled]):hover,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper:not(.ant-input-affix-wrapper-disabled):hover,
        [data-ec-scope="lightrag-ported"] .ant-input-password:not([disabled]):hover,
        [data-ec-scope="lightrag-ported"] .ant-input-number:not(.ant-input-number-disabled):hover,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea:hover,
        [data-ec-scope="lightrag-ported"] .ant-input-search .ant-input:hover,
        [data-ec-scope="lightrag-ported"] .ant-select:not(.ant-select-disabled):hover .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker:hover,
        [data-ec-scope="lightrag-ported"] .ec-input:not([disabled]):hover {
          border-color: ${token.colorPrimary} !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-input:focus,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-focused,
        [data-ec-scope="lightrag-ported"] .ant-input-password:focus,
        [data-ec-scope="lightrag-ported"] .ant-input-number-focused,
        [data-ec-scope="lightrag-ported"] .ant-input-textarea:focus,
        [data-ec-scope="lightrag-ported"] .ant-input-search .ant-input:focus,
        [data-ec-scope="lightrag-ported"] .ant-select-focused .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker-focused,
        [data-ec-scope="lightrag-ported"] .ec-input:focus {
          border-color: ${token.colorPrimary} !important;
          box-shadow: 0 0 0 2px ${token.colorPrimaryBg} !important;
          outline: none !important;
        }
        /* --- 5. Disabled: same look across every input type. --- */
        [data-ec-scope="lightrag-ported"] .ant-input[disabled],
        [data-ec-scope="lightrag-ported"] .ant-input-number-disabled,
        [data-ec-scope="lightrag-ported"] .ant-input-affix-wrapper-disabled,
        [data-ec-scope="lightrag-ported"] .ant-select-disabled .ant-select-selector,
        [data-ec-scope="lightrag-ported"] .ant-picker-disabled {
          background: ${isDark ? 'rgba(255,255,255,0.04)' : token.colorFillTertiary} !important;
          color: ${token.colorTextSecondary} !important;
          border-color: ${token.colorBorderSecondary} !important;
          cursor: not-allowed !important;
        }
        /* --- 6. InputNumber handler column: same border colour as the box. ---
              The +/- step buttons sit in a separate wrapper with its own
              border-inline-start. Without an explicit override the column
              looks "split" from the rest of the field. */
        [data-ec-scope="lightrag-ported"] .ant-input-number .ant-input-number-handler-wrap {
          border-inline-start: 1px solid ${token.colorBorder} !important;
          background: ${token.colorBgContainer} !important;
          border-radius: 0 7px 7px 0 !important;
        }
        [data-ec-scope="lightrag-ported"] .ant-input-number .ant-input-number-handler {
          border-color: ${token.colorBorder} !important;
        }
        /* --- 7. Input.Search addon: search button shares the box border. --- */
        [data-ec-scope="lightrag-ported"] .ant-input-search .ant-input-group-addon {
          background: ${token.colorBgContainer} !important;
          border-color: ${token.colorBorder} !important;
        }
        /* --- 8. Picker (DatePicker / TimePicker) prefix/suffix icons. --- */
        [data-ec-scope="lightrag-ported"] .ant-picker .ant-picker-suffix,
        [data-ec-scope="lightrag-ported"] .ant-picker .ant-picker-prefix {
          color: ${token.colorTextSecondary} !important;
        }
        /* --- 9. Cascader / TreeSelect arrow. --- */
        [data-ec-scope="lightrag-ported"] .ant-cascader-picker .ant-cascader-picker-arrow,
        [data-ec-scope="lightrag-ported"] .ant-tree-select .ant-select-arrow {
          color: ${token.colorTextSecondary} !important;
        }
        /* --- 10. Form.Item error text colour: tone with theme. ---
              antd defaults to a fixed red which can clash with custom
              dark backgrounds. Re-pin to the theme error token. */
        [data-ec-scope="lightrag-ported"] .ant-form-item .ant-form-item-explain-error {
          color: ${token.colorError} !important;
          font-size: 12px !important;
        }
        /* --- 11. Switch: align vertical baseline with input/select. --- */
        [data-ec-scope="lightrag-ported"] .ant-switch {
          margin: 0 !important;
        }
      `}</style>
    </div>
  );
};

export default Tabs;
