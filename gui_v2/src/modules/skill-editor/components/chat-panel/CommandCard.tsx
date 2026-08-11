/**
 * CommandCard - Renders a cloud-proposed `ecan` CLI command as a form with
 * copy buttons and a Proceed / Cancel / Other choice menu (Claude-Code style).
 * The client runs the command locally (applies + syncs) and posts the result
 * back to the agent. Mirrors PlanCard's approval pattern.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Radio } from 'antd';
import {
  CodeOutlined, LoadingOutlined, CopyOutlined, SendOutlined,
} from '@ant-design/icons';
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
  /** Optional payload (e.g. a prompt body) shown in its own copyable block. */
  content?: string;
  description?: string;
  /** When false, this is a read-only (no-mutation) command shown for transparency. */
  requiresConfirmation?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
  /** User wants something different — receives their freeform instruction. */
  onOther?: (text: string) => void;
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

const BlockLabel = styled.div`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
`;

const Block = styled.div`
  position: relative;
`;

const CopyBtn = styled.button`
  position: absolute;
  top: 6px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: #93c5fd;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  cursor: pointer;
  &:hover { background: rgba(30, 41, 59, 0.95); }
`;

const Description = styled.div`
  font-size: 13px;
  color: #e2e8f0;
  margin-bottom: 12px;
  line-height: 1.5;
`;

const CodePre = styled.pre`
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

const ContentPre = styled.pre`
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 11px;
  color: rgba(203, 213, 225, 0.95);
  background: rgba(15, 23, 42, 0.55);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
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

const ActionGroup = styled(Radio.Group)`
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  .ant-radio-wrapper {
    color: #e2e8f0;
    font-size: 13px;
    margin-inline-end: 0;
  }
`;

const SubmitHint = styled.div`
  margin-top: 8px;
  font-size: 12px;
  color: #93c5fd;
`;

const OtherRow = styled.div`
  display: flex;
  gap: 8px;
  margin-top: 8px;
`;

const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const { t } = useTranslation('skillEditor');
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable */
    }
  };
  return (
    <CopyBtn type="button" onClick={copy}>
      <CopyOutlined />
      {copied ? t('chatPanel.copied', 'Copied') : t('chatPanel.copy', 'Copy')}
    </CopyBtn>
  );
};

export const CommandCard: React.FC<CommandCardProps> = ({
  command,
  content,
  description,
  requiresConfirmation = true,
  onConfirm,
  onCancel,
  onOther,
  isSubmitting = false,
  submittedAction,
  result,
}) => {
  const { t } = useTranslation('skillEditor');
  const isReadOnly = !!submittedAction;
  const [choice, setChoice] = useState<'confirm' | 'cancel' | 'other' | ''>('');
  const [otherText, setOtherText] = useState('');

  const headerColor = isReadOnly
    ? (submittedAction === 'confirmed' ? '#22c55e' : '#94a3b8')
    : '#3b82f6';
  const headerText = isReadOnly
    ? (submittedAction === 'confirmed'
        ? t('chatPanel.commandRan', 'Command executed')
        : t('chatPanel.commandCancelled', 'Command cancelled'))
    : t('chatPanel.commandProposed', 'Proposed command');

  const submitOther = () => {
    const txt = otherText.trim();
    if (!txt || !onOther) return;
    onOther(txt);
    setOtherText('');
    setChoice('');
  };

  return (
    <CardContainer>
      <CardHeader>
        <CardTitle>
          <CodeOutlined style={{ color: headerColor }} />
          {headerText}
        </CardTitle>
      </CardHeader>

      {description && !isReadOnly && <Description>{description}</Description>}

      <Block>
        <CopyButton text={command} />
        <CodePre>{command}</CodePre>
      </Block>

      {content && content.trim() && (
        <>
          <BlockLabel>{t('chatPanel.commandContent', 'Content')}</BlockLabel>
          <Block>
            <CopyButton text={content} />
            <ContentPre>{content}</ContentPre>
          </Block>
        </>
      )}

      {result && (
        <>
          {result.stdout?.trim() && <OutputBlock>{result.stdout.trim()}</OutputBlock>}
          {result.stderr?.trim() && <OutputBlock $error>{result.stderr.trim()}</OutputBlock>}
        </>
      )}

      {!isReadOnly && requiresConfirmation && (
        <>
          <ActionGroup
            value={choice}
            disabled={isSubmitting}
            onChange={e => {
              const v = e.target.value as 'confirm' | 'cancel' | 'other';
              setChoice(v);
              if (v === 'confirm') onConfirm?.();
              else if (v === 'cancel') onCancel?.();
            }}
          >
            <Radio value="confirm">{t('chatPanel.commandProceed', 'Proceed — run it locally')}</Radio>
            <Radio value="cancel">{t('chatPanel.commandCancel', 'Cancel')}</Radio>
            {onOther && (
              <Radio value="other">{t('chatPanel.commandOther', 'Something else…')}</Radio>
            )}
          </ActionGroup>

          {choice === 'other' && onOther && (
            <OtherRow>
              <Input
                autoFocus
                value={otherText}
                onChange={e => setOtherText(e.target.value)}
                onPressEnter={submitOther}
                placeholder={t('chatPanel.commandOtherPlaceholder', 'e.g. make it shorter, change the name to…')}
                disabled={isSubmitting}
              />
              <Button type="primary" icon={<SendOutlined />} onClick={submitOther} disabled={isSubmitting || !otherText.trim()}>
                {t('chatPanel.send', 'Send')}
              </Button>
            </OtherRow>
          )}

          {isSubmitting && (
            <SubmitHint>
              <LoadingOutlined /> {t('chatPanel.commandRunning', 'Running…')}
            </SubmitHint>
          )}
        </>
      )}
    </CardContainer>
  );
};

export default CommandCard;
