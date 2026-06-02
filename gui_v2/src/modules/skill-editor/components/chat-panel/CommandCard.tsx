/**
 * CommandCard - Renders a cloud-proposed `ecan` CLI command with confirm/cancel
 * buttons. The cloud helper agent proposes agent/task CRUD as a local command;
 * the client runs it (applying locally + syncing to cloud) and posts the result
 * back to the agent. Mirrors PlanCard's approval pattern.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from 'antd';
import { CheckOutlined, CloseOutlined, CodeOutlined, LoadingOutlined } from '@ant-design/icons';
import styled from 'styled-components';

export interface CommandResult {
  success: boolean;
  returnCode: number;
  stdout: string;
  stderr: string;
  command: string;
}

interface CommandCardProps {
  command: string;
  description?: string;
  /** When false, this is a read-only (no-mutation) command shown for transparency. */
  requiresConfirmation?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  /** If provided, renders read-only showing the action taken. */
  submittedAction?: 'confirmed' | 'cancelled';
  /** If provided, shows the command's run output. */
  result?: CommandResult;
}

const CardContainer = styled.div`
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.35);
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
`;

const CardTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const Description = styled.div`
  font-size: 13px;
  color: #e2e8f0;
  margin-bottom: 12px;
  line-height: 1.5;
`;

const CommandBlock = styled.pre`
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  color: #93c5fd;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px 0;
  white-space: pre-wrap;
  word-break: break-all;
`;

const OutputBlock = styled.pre<{ $error?: boolean }>`
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 11px;
  color: ${props => (props.$error ? '#fca5a5' : 'rgba(203, 213, 225, 0.9)')};
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
  padding: 8px 12px;
  margin: 0 0 8px 0;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
`;

const ButtonContainer = styled.div`
  display: flex;
  gap: 8px;
`;

const FlexButton = styled(Button)`
  flex: 1;
`;

export const CommandCard: React.FC<CommandCardProps> = ({
  command,
  description,
  requiresConfirmation = true,
  onConfirm,
  onCancel,
  isSubmitting = false,
  submittedAction,
  result,
}) => {
  const { t } = useTranslation('skillEditor');
  const isReadOnly = !!submittedAction;

  const headerColor = isReadOnly
    ? (submittedAction === 'confirmed' ? '#22c55e' : '#94a3b8')
    : '#3b82f6';
  const headerText = isReadOnly
    ? (submittedAction === 'confirmed'
        ? t('chatPanel.commandRan', 'Command executed')
        : t('chatPanel.commandCancelled', 'Command cancelled'))
    : t('chatPanel.commandProposed', 'Proposed command');

  return (
    <CardContainer>
      <CardHeader>
        <CardTitle>
          <CodeOutlined style={{ color: headerColor }} />
          {headerText}
        </CardTitle>
      </CardHeader>

      {description && !isReadOnly && <Description>{description}</Description>}

      <CommandBlock>{command}</CommandBlock>

      {result && (
        <>
          {result.stdout?.trim() && <OutputBlock>{result.stdout.trim()}</OutputBlock>}
          {result.stderr?.trim() && <OutputBlock $error>{result.stderr.trim()}</OutputBlock>}
        </>
      )}

      {!isReadOnly && requiresConfirmation && (
        <ButtonContainer>
          <FlexButton
            type="primary"
            icon={isSubmitting ? <LoadingOutlined /> : <CheckOutlined />}
            onClick={onConfirm}
            disabled={isSubmitting}
            loading={isSubmitting}
            style={{ background: '#22c55e', borderColor: '#22c55e' }}
          >
            {t('chatPanel.commandConfirm', 'Run it')}
          </FlexButton>
          <FlexButton
            icon={<CloseOutlined />}
            onClick={onCancel}
            disabled={isSubmitting}
          >
            {t('chatPanel.commandCancel', 'Cancel')}
          </FlexButton>
        </ButtonContainer>
      )}
    </CardContainer>
  );
};

export default CommandCard;
