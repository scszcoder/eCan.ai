import { useState } from 'react';
import { Settings } from 'lucide-react';
import { Button, Popover, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import SettingsPanel from './SettingsPanel';

/**
 * Settings button that shows the settings panel in a popover
 */
const SettingsButton = () => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <Popover
      content={<SettingsPanel />}
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="rightBottom"
    >
      <Tooltip title={t('graphPanel.sideBar.settings.settings', '设置')} placement="right">
        <Button
          type="text"
          icon={<Settings size={18} style={{ color: 'var(--text-secondary)' }} />}
          style={{ 
            width: 36, 
            height: 36,
            color: 'var(--text-secondary)',
            backgroundColor: open ? 'var(--surface-subtle-hover)' : 'transparent'
          }}
        />
      </Tooltip>
    </Popover>
  );
};

export default SettingsButton;
