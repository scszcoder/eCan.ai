import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Button } from 'antd';
import { useSettingsStore } from '../stores/settings'; // Ensure this import path is correct relative to the file location

interface MergeDialogProps {
  mergeDialogOpen: boolean;
  mergeDialogInfo: {
    targetEntity: string;
    sourceEntity: string;
  } | null;
  onOpenChange: (open: boolean) => void;
  onRefresh: (useMergedStart: boolean) => void;
}

const MergeDialog: React.FC<MergeDialogProps> = ({
  mergeDialogOpen,
  mergeDialogInfo,
  onOpenChange,
  onRefresh
}) => {
  const { t } = useTranslation();
  const queryLabel = useSettingsStore(s => s.queryLabel);

  return (
    <Modal
      title={t('graphPanel.propertiesView.mergeDialog.title', 'Entity Merged')}
      open={mergeDialogOpen}
      onCancel={() => onOpenChange(false)}
      footer={[
        // Only show 'Keep Current Start' if we are not currently focused on the source entity that disappeared
        queryLabel !== mergeDialogInfo?.sourceEntity && (
          <Button key="keep" onClick={() => onRefresh(false)}>
            {t('graphPanel.propertiesView.mergeDialog.keepCurrentStart', 'Keep Current View')}
          </Button>
        ),
        <Button key="use" type="primary" onClick={() => onRefresh(true)}>
          {t('graphPanel.propertiesView.mergeDialog.useMergedStart', 'Switch to Merged Entity')}
        </Button>
      ].filter(Boolean)}
    >
      <p>
        {t('graphPanel.propertiesView.mergeDialog.description', {
          source: mergeDialogInfo?.sourceEntity ?? '',
          target: mergeDialogInfo?.targetEntity ?? '',
          defaultValue: `Entity "${mergeDialogInfo?.sourceEntity}" has been merged into "${mergeDialogInfo?.targetEntity}".`
        })}
      </p>
      <p style={{ fontSize: 12, color: '#888', marginTop: 8 }}>
        {t('graphPanel.propertiesView.mergeDialog.refreshHint', 'The graph needs to be refreshed to reflect changes.')}
      </p>
    </Modal>
  );
};

export default MergeDialog;
