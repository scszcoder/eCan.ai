import React, { useState, useCallback } from 'react';
import { Dropdown, Button, Toast } from '@douyinfe/semi-ui';
import { IconGitColored } from './colored-icons';

export const GitMenu: React.FC = () => {
  const [visible, setVisible] = useState(false);

  const click = (label: string) => () => {
    // Defer toast to avoid nested update warnings
    setTimeout(() => { try { Toast.info({ content: `[Git] ${label} (placeholder)` }); } catch {} }, 0);
    setVisible(false);
  };

  const onVisibleChange = useCallback((v: boolean) => setVisible(v), []);

  const menu = (
    <Dropdown.Menu>
      <Dropdown.Item onClick={click('Commit')}>Commit</Dropdown.Item>
      <Dropdown.Item onClick={click('Push')}>Push</Dropdown.Item>
      <Dropdown.Item onClick={click('Pull')}>Pull</Dropdown.Item>
      <Dropdown.Divider />
      <Dropdown.Item onClick={click('Update')}>Update</Dropdown.Item>
      <Dropdown.Item onClick={click('Branch')}>Branch</Dropdown.Item>
      <Dropdown.Item onClick={click('Merge')}>Merge</Dropdown.Item>
      <Dropdown.Item onClick={click('Tag')}>Tag</Dropdown.Item>
      <Dropdown.Divider />
      <Dropdown.Item onClick={click('Reset HEAD')}>Reset HEAD</Dropdown.Item>
      <Dropdown.Item onClick={click('Patch')}>Patch</Dropdown.Item>
      <Dropdown.Item onClick={click('History')}>History</Dropdown.Item>
      <Dropdown.Item onClick={click('Remote')}>Remote</Dropdown.Item>
    </Dropdown.Menu>
  );

  return (
    <Dropdown
      trigger={'custom'}
      position="bottomLeft"
      zIndex={3000}
      visible={visible}
      onVisibleChange={onVisibleChange}
      getPopupContainer={() => document.body}
      render={menu}
    >
      <Button
        type="tertiary"
        theme="borderless"
        icon={<IconGitColored size={18} />}
        aria-label="Git"
        title="Git"
        onMouseDown={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setVisible((v) => !v);
        }}
        onClick={(e) => {
          // prevent second toggle from click after mousedown
          e.preventDefault();
          e.stopPropagation();
        }}
      />
    </Dropdown>
  );
};
