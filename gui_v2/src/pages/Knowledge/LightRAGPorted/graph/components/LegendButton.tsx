import { useCallback } from 'react';
import { BookOpen } from 'lucide-react';
import { Button, Tooltip } from 'antd';
import { useSettingsStore } from '../stores/settings';
import { useTranslation } from 'react-i18next';

/**
 * Component that toggles legend visibility.
 */
const LegendButton = () => {
  const { t } = useTranslation();
  const showLegend = useSettingsStore((s) => s.showLegend);

  const toggleLegend = useCallback(() => {
    useSettingsStore.setState((state) => ({ showLegend: !state.showLegend }));
  }, []);

  return (
    <Tooltip title={t('graphPanel.sideBar.legendControl.toggleLegend', '切换图例显示')}>
      <Button
        type="text"
        icon={<BookOpen size={18} style={{ color: '#ffffff' }} />}
        onClick={toggleLegend}
        style={{ 
          width: 36, 
          height: 36,
          color: '#ffffff',
          backgroundColor: showLegend ? 'rgba(255, 255, 255, 0.1)' : 'transparent'
        }}
      />
    </Tooltip>
  );
};

export default LegendButton;
