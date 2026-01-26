import { useCallback, useMemo } from 'react';
import { Button, Space, Typography } from '@douyinfe/semi-ui';

import { SafeCodeEditor } from '../../../components/SafeCodeEditor';
import { useSkillInfoStore } from '../../../stores/skill-info-store';

const { Text } = Typography;

export function DataMappingEditor() {
  const dataMappingJson = useSkillInfoStore((s) => s.dataMappingJson) || '';
  const setDataMappingJson = useSkillInfoStore((s) => s.setDataMappingJson);
  const setDataMappingDirty = useSkillInfoStore((s) => s.setDataMappingDirty);

  const parseError = useMemo(() => {
    if (!dataMappingJson.trim()) {
      return null;
    }
    try {
      JSON.parse(dataMappingJson);
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'Invalid JSON';
    }
  }, [dataMappingJson]);

  const handleChange = useCallback((value: string) => {
    setDataMappingJson(value, true);
    setDataMappingDirty(true);
  }, [setDataMappingDirty, setDataMappingJson]);

  const handleFormat = useCallback(() => {
    try {
      const parsed = dataMappingJson.trim() ? JSON.parse(dataMappingJson) : {};
      const pretty = JSON.stringify(parsed, null, 2);
      setDataMappingJson(pretty, true);
      setDataMappingDirty(true);
    } catch {
      setDataMappingDirty(true);
    }
  }, [dataMappingJson, setDataMappingDirty, setDataMappingJson]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Space style={{ justifyContent: 'space-between' }}>
        <Text type="tertiary" size="small">
          Edit data_mapping.json (skill-level and node transfer mappings).
        </Text>
        <Button size="small" onClick={handleFormat}>Format</Button>
      </Space>
      {parseError && (
        <Text type="danger" size="small">Invalid JSON: {parseError}</Text>
      )}
      <SafeCodeEditor
        languageId="json"
        value={dataMappingJson}
        onChange={handleChange}
        style={{ height: 300 }}
      />
    </div>
  );
}
