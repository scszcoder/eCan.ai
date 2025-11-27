import { useSettingsStore } from '../stores/settings';
import { useTranslation } from 'react-i18next';

/**
 * Component that displays current values of important graph settings
 * Positioned to the right of the toolbar at the bottom-left corner
 */
const SettingsDisplay = () => {
  const { t } = useTranslation();
  const graphQueryMaxDepth = useSettingsStore((s) => s.graphQueryMaxDepth);
  const graphMaxNodes = useSettingsStore((s) => s.graphMaxNodes);

  return (
    <div style={{
      position: 'absolute',
      bottom: 16,
      left: 'calc(1rem + 3rem)',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontSize: 12,
      color: '#999',
      zIndex: 10
    }}>
      <div>{t('graphPanel.sideBar.settings.depth', '深')}: {graphQueryMaxDepth}</div>
      <div>{t('graphPanel.sideBar.settings.max', 'Max')}: {graphMaxNodes}</div>
    </div>
  );
};

export default SettingsDisplay;
