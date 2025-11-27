import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { App } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import { useGraphStore } from '../stores/graph';
import { useSettingsStore } from '../stores/settings';
import { PropertyName, EditIcon, PropertyValue } from './PropertyRowComponents';
import PropertyEditDialog from './PropertyEditDialog';
import MergeDialog from './MergeDialog';

interface EditablePropertyRowProps {
  name: string;
  value: any;
  onClick?: () => void;
  nodeId?: string;
  entityId?: string;
  edgeId?: string;
  dynamicId?: string;
  entityType?: 'node' | 'edge';
  sourceId?: string;
  targetId?: string;
  onValueChange?: (newValue: any) => void;
  isEditable?: boolean;
  tooltip?: string;
}

const EditablePropertyRow: React.FC<EditablePropertyRowProps> = ({
  name,
  value: initialValue,
  onClick,
  nodeId,
  edgeId,
  entityId,
  dynamicId,
  entityType,
  sourceId,
  targetId,
  onValueChange,
  isEditable = false,
  tooltip
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [isEditing, setIsEditing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentValue, setCurrentValue] = useState(initialValue);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [mergeDialogOpen, setMergeDialogOpen] = useState(false);
  const [mergeDialogInfo, setMergeDialogInfo] = useState<{
    targetEntity: string;
    sourceEntity: string;
  } | null>(null);

  useEffect(() => {
    setCurrentValue(initialValue);
  }, [initialValue]);

  const handleEditClick = () => {
    if (isEditable && !isEditing) {
      setIsEditing(true);
      setErrorMessage(null);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    setErrorMessage(null);
  };

  const handleSave = async (value: string, options?: { allowMerge?: boolean }) => {
    if (isSubmitting || value === String(currentValue)) {
      setIsEditing(false);
      setErrorMessage(null);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      if (entityType === 'node' && entityId && nodeId) {
        let updatedData = { [name]: value };
        const allowMerge = options?.allowMerge ?? false;

        if (name === 'entity_id') {
          // Check if entity name already exists (unless merge is allowed)
          if (!allowMerge) {
            try {
              const existsResponse = await get_ipc_api().lightragApi.checkEntityNameExists({ name: value });
              if (existsResponse.success && existsResponse.data?.exists) {
                const errorMsg = t('graphPanel.propertiesView.errors.duplicateName', 'An entity with this name already exists');
                setErrorMessage(errorMsg);
                message.error(errorMsg);
                return;
              }
            } catch (err) {
              console.warn('Failed to check entity name existence:', err);
              // Continue with update even if check fails
            }
          }
          updatedData = { 'entity_name': value };
        }

        const response = await get_ipc_api().lightragApi.updateEntity({
            entity_name: entityId,
            updated_data: updatedData,
            allow_rename: true,
            allow_merge: allowMerge
        });

        if (!response.success) {
            throw new Error(response.error?.message || 'Update failed');
        }
        
        const result = response.data as any;
        const operationSummary = result.operation_summary;
        const operationStatus = operationSummary?.operation_status || 'complete_success';
        const finalValue = operationSummary?.final_entity ?? value;

        if (operationStatus === 'success' || operationStatus === 'complete_success') {
          if (operationSummary?.merged) {
            setMergeDialogInfo({
              targetEntity: finalValue,
              sourceEntity: entityId,
            });
            setMergeDialogOpen(true);
            message.success(t('graphPanel.propertiesView.success.entityMerged', 'Entity merged successfully'));
          } else {
            // Node updated
             const graphValue = name === 'entity_id' ? finalValue : value;
             
             // Call store update if method exists
             const store = useGraphStore.getState();
             if ((store as any).updateNodeAndSelect) {
                 await (store as any).updateNodeAndSelect(nodeId, entityId, name, graphValue);
             }

             message.success(t('graphPanel.propertiesView.success.entityUpdated', 'Entity updated successfully'));
          }

          const valueToSet = name === 'entity_id' ? finalValue : value;
          setCurrentValue(valueToSet);
          onValueChange?.(valueToSet);

        } else if (operationStatus === 'partial_success') {
            const mergeError = operationSummary?.merge_error || 'Unknown error';
            setErrorMessage(`Update success but merge failed: ${mergeError}`);
            return;
        } else {
             // Failed
             const mergeError = operationSummary?.merge_error || 'Unknown error';
             setErrorMessage(`Operation failed: ${mergeError}`);
             return;
        }

      } else if (entityType === 'edge' && sourceId && targetId && edgeId && dynamicId) {
        const updatedData = { [name]: value };
        const response = await get_ipc_api().lightragApi.updateRelation({
            source_id: sourceId,
            target_id: targetId,
            updated_data: updatedData
        });
        
        if (!response.success) {
            throw new Error(response.error?.message || 'Update failed');
        }
        
        const result = response.data as any;
        if (result.status === 'error') {
             throw new Error(result.message || 'Update failed');
        }

        // Call store update if method exists
        const store = useGraphStore.getState();
        if ((store as any).updateEdgeAndSelect) {
            await (store as any).updateEdgeAndSelect(edgeId, dynamicId, sourceId, targetId, name, value);
        }

        message.success(t('graphPanel.propertiesView.success.relationUpdated', 'Relation updated successfully'));
        setCurrentValue(value);
        onValueChange?.(value);
      }

      setIsEditing(false);
    } catch (error: any) {
      console.error('Error updating property:', error);
      setErrorMessage(error.message || 'Update failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMergeRefresh = (useMergedStart: boolean) => {
    const info = mergeDialogInfo;
    const graphState = useGraphStore.getState();
    const settingsState = useSettingsStore.getState();
    const currentLabel = settingsState.queryLabel;

    // Clear graph state
    graphState.clearSelection();
    graphState.setGraphDataFetchAttempted(false);
    graphState.setLastSuccessfulQueryLabel('');

    if (useMergedStart && info?.targetEntity) {
      // Use merged entity as new start point
      settingsState.setQueryLabel(info.targetEntity);
    } else {
      // Keep current start point - refresh by resetting and restoring label
      settingsState.setQueryLabel('');
      setTimeout(() => {
        settingsState.setQueryLabel(currentLabel);
      }, 50);
    }

    // Force graph re-render
    graphState.incrementGraphDataVersion();

    setMergeDialogOpen(false);
    setMergeDialogInfo(null);
    message.info(t('graphPanel.propertiesView.mergeDialog.refreshing', 'Refreshing graph...'));
  };

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, overflow: 'hidden' }}>
      <PropertyName name={name} />
      <EditIcon onClick={handleEditClick} />
      <span style={{ color: 'rgba(0,0,0,0.45)' }}>:</span>
      <PropertyValue
        value={currentValue}
        onClick={onClick}
        tooltip={tooltip}
      />
      <PropertyEditDialog
        isOpen={isEditing}
        onClose={handleCancel}
        onSave={handleSave}
        propertyName={name}
        initialValue={String(currentValue)}
        isSubmitting={isSubmitting}
        errorMessage={errorMessage}
      />

      <MergeDialog
        mergeDialogOpen={mergeDialogOpen}
        mergeDialogInfo={mergeDialogInfo}
        onOpenChange={(open) => {
            setMergeDialogOpen(open);
            if (!open) setMergeDialogInfo(null);
        }}
        onRefresh={handleMergeRefresh}
      />
    </div>
  );
};

export default EditablePropertyRow;
