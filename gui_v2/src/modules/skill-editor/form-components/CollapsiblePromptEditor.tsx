import React, { useState } from 'react';
import { Button } from '@douyinfe/semi-ui';
import { IconChevronDown, IconChevronUp } from '@douyinfe/semi-icons';
import { PromptEditorWithVariables } from '@flowgram.ai/form-materials';
import { useTranslation } from 'react-i18next';

interface CollapsiblePromptEditorProps {
  value: any;
  onChange: (value: any) => void;
  readonly: boolean;
  hasError: boolean;
  defaultCollapsed?: boolean;
  collapsedLines?: number;
}

export const CollapsiblePromptEditor: React.FC<CollapsiblePromptEditorProps> = ({
  value,
  onChange,
  readonly,
  hasError,
  defaultCollapsed = true,
  collapsedLines = 3,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const { t } = useTranslation('skillEditor');

  const lineCount = (() => {
    try {
      const content = value?.content || '';
      return typeof content === 'string' ? content.split('\n').length : 0;
    } catch { return 0; }
  })();
  const shouldShowToggle = lineCount > collapsedLines;

  return (
    <div style={{ position: 'relative' }}>
      <div
        style={{
          maxHeight: isCollapsed && shouldShowToggle ? `${collapsedLines * 24}px` : 'none',
          overflow: isCollapsed && shouldShowToggle ? 'hidden' : 'visible',
          position: 'relative',
        }}
      >
        <PromptEditorWithVariables
          value={value}
          onChange={onChange}
          readonly={readonly}
          hasError={hasError}
        />
        {isCollapsed && shouldShowToggle && (
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: '40px',
              background: 'linear-gradient(to bottom, transparent, rgba(255, 255, 255, 0.95))',
              pointerEvents: 'none',
            }}
          />
        )}
      </div>
      {shouldShowToggle && (
        <div style={{ marginTop: '8px', textAlign: 'center' }}>
          <Button
            icon={isCollapsed ? <IconChevronDown /> : <IconChevronUp />}
            size="small"
            theme="borderless"
            onClick={() => setIsCollapsed(!isCollapsed)}
            style={{ fontSize: '12px' }}
          >
            {isCollapsed
              ? t('formComponents.expandPrompt', { defaultValue: '展开查看全部' })
              : t('formComponents.collapsePrompt', { defaultValue: '收起' })
            }
          </Button>
        </div>
      )}
    </div>
  );
};
