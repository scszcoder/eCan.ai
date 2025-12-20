/**
 * Help Panel: side overlay with search and documentation
 */
import React, { useMemo, useState } from 'react';
import { SideSheet, Input, Nav, Button } from '@douyinfe/semi-ui';
import { IconSearch, IconClose } from '@douyinfe/semi-icons';

interface HelpPanelProps {
  visible: boolean;
  onCancel: () => void;
}

const DOC_TOC = [
  { key: 'intro', text: 'Introduction' },
  { key: 'nodes', text: 'Nodes' },
  { key: 'editor', text: 'Editor Basics' },
  { key: 'debug', text: 'Debugger' },
  { key: 'testrun', text: 'Test Run' },
  { key: 'shortcuts', text: 'Shortcuts' },
  { key: 'faq', text: 'FAQ' },
];

const DOC_SECTIONS: Record<string, React.ReactNode> = {
  intro: (
    <div>
      <h2>Introduction</h2>
      <p>Welcome to the Skill Editor. This guide will help you build and run flows.</p>
    </div>
  ),
  nodes: (
    <div>
      <h2>Nodes</h2>
      <p>Each node performs a unit of work. Connect nodes to build flows.</p>
    </div>
  ),
  editor: (
    <div>
      <h2>Editor Basics</h2>
      <p>Use the toolbar to add nodes, set zoom, and manage layout.</p>
    </div>
  ),
  debug: (
    <div>
      <h2>Debugger</h2>
      <p>Set breakpoints and use pause/step/resume buttons to control execution.</p>
    </div>
  ),
  testrun: (
    <div>
      <h2>Test Run</h2>
      <p>Open the Test Run panel to supply inputs and simulate a flow run.</p>
    </div>
  ),
  shortcuts: (
    <div>
      <h2>Shortcuts</h2>
      <h3>Canvas Navigation</h3>
      <ul>
        <li><strong>Space + Drag</strong>: Pan canvas (hold Space, then drag with mouse)</li>
        <li><strong>Mouse wheel</strong>: Zoom in/out</li>
        <li><strong>Ctrl/Cmd + +</strong>: Zoom in</li>
        <li><strong>Ctrl/Cmd + -</strong>: Zoom out</li>
      </ul>
      <h3>Editing</h3>
      <ul>
        <li><strong>Ctrl/Cmd + Z</strong>: Undo</li>
        <li><strong>Ctrl/Cmd + Y</strong>: Redo</li>
        <li><strong>Ctrl/Cmd + C</strong>: Copy selected nodes</li>
        <li><strong>Ctrl/Cmd + V</strong>: Paste nodes</li>
        <li><strong>Ctrl/Cmd + A</strong>: Select all nodes</li>
        <li><strong>Delete / Backspace</strong>: Delete selected nodes</li>
      </ul>
      <h3>Node Operations</h3>
      <ul>
        <li><strong>Click node</strong>: Select node</li>
        <li><strong>Double-click node</strong>: Open node editor</li>
        <li><strong>Drag node</strong>: Move node</li>
        <li><strong>Shift + Click</strong>: Add to selection</li>
      </ul>
    </div>
  ),
  faq: (
    <div>
      <h2>FAQ</h2>
      <p>Common issues and troubleshooting tips.</p>
    </div>
  ),
};

export const HelpPanel: React.FC<HelpPanelProps> = ({ visible, onCancel }) => {
  const [selectedKey, setSelectedKey] = useState<string>('intro');
  const [query, setQuery] = useState<string>('');

  const filteredToc = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return DOC_TOC;
    return DOC_TOC.filter(item => item.text.toLowerCase().includes(q));
  }, [query]);

  const content = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return DOC_SECTIONS[selectedKey] || null;
    // Basic search: if current panel doesn't match, show Intro with note
    return (
      <div>
        <div style={{ marginBottom: 12, color: 'var(--semi-color-text-2)' }}>
          Showing results for: <strong>{query}</strong>
        </div>
        {DOC_SECTIONS[selectedKey]}
      </div>
    );
  }, [selectedKey, query]);

  return (
    <SideSheet
      visible={visible}
      onCancel={onCancel}
      closable={false}
      mask={true}
      width={800}
      headerStyle={{ display: 'none' }}
      bodyStyle={{ padding: 0 }}
      style={{ background: 'var(--semi-color-bg-1)', color: 'var(--semi-color-text-0)' }}
    >
      {/* Header with search and close */}
      <div style={{ display: 'flex', alignItems: 'center', padding: 12, gap: 8, borderBottom: '1px solid var(--semi-color-border)', background: 'var(--semi-color-bg-1)' }}>
        <Input
          prefix={<IconSearch />}
          placeholder="Search in help..."
          value={query}
          onChange={setQuery}
        />
        <Button icon={<IconClose />} type="tertiary" theme="borderless" onClick={onCancel} />
      </div>

      {/* Content area split: left TOC, right doc */}
      <div style={{ display: 'flex', minHeight: 520 }}>
        <div style={{ width: 240, borderRight: '1px solid var(--semi-color-border)', padding: 12, color: 'var(--semi-color-text-0)' }}>
          <Nav
            selectedKeys={[selectedKey]}
            items={filteredToc.map(item => ({ itemKey: item.key, text: item.text }))}
            onSelect={data => setSelectedKey(String(data.itemKey))}
            style={{ width: '100%' }}
          />
        </div>
        <div style={{ flex: 1, padding: 16, overflow: 'auto', color: 'var(--semi-color-text-0)', lineHeight: 1.6 }}>
          <div style={{ maxWidth: 860 }}>
            {content}
          </div>
        </div>
      </div>
    </SideSheet>
  );
};
