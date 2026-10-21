import React from 'react';
import { Button, Input, Rate, Space, Tag, Tooltip, App } from 'antd';
import { LikeOutlined, DislikeOutlined, LikeFilled, DislikeFilled, CheckOutlined, RedoOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { eventBus } from '@/utils/eventBus';
import { notificationManager } from '../managers/NotificationManager';

export type ItemFeedbackValue = {
  thumb?: 'up' | 'down' | null;
  stars?: number;
  comment?: string;
  accepted?: boolean;
};

/**
 * Rating + comment for one result item (e.g. a generated image). Saved on the
 * notification; "Revise" / "Accept" also post a chat message to the agent that
 * produced the result, so the follow-up happens in the conversation.
 */
const ResultFeedback: React.FC<{
  chatId: string;
  notifUid: string;
  itemKey: string;
  initial?: ItemFeedbackValue;
}> = ({ chatId, notifUid, itemKey, initial }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [fb, setFb] = React.useState<ItemFeedbackValue>(initial || {});
  const [comment, setComment] = React.useState<string>(initial?.comment || '');

  const save = async (patch: ItemFeedbackValue) => {
    const next = { ...fb, ...patch };
    setFb(next);
    try {
      const res: any = await get_ipc_api().chatApi.setChatNotificationFeedback(notifUid, itemKey, patch);
      if (!res?.success) throw new Error(res?.error?.message || 'save failed');
      notificationManager.setItemFeedback(chatId, notifUid, itemKey, patch);
    } catch (e) {
      message.error(t('agentnotify.feedback_save_failed', '保存评价失败'));
    }
  };

  const rating = () => {
    const parts: string[] = [];
    if (fb.stars) parts.push(`${fb.stars}★`);
    if (fb.thumb === 'up') parts.push('👍');
    if (fb.thumb === 'down') parts.push('👎');
    return parts.length ? `（${parts.join(' ')}）` : '';
  };

  const send = (text: string) => eventBus.emit('chat:sendUserMessage', { chatId, text });

  const revise = async () => {
    const c = comment.trim();
    if (!c) return;
    await save({ comment: c, accepted: false });
    send(`【修改】${itemKey}${rating()}：${c}`);
  };

  const accept = async () => {
    const c = comment.trim();
    await save({ accepted: true, ...(c ? { comment: c } : {}) });
    send(`【采用】${itemKey}${rating()}${c ? `：${c}` : ''}`);
  };

  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px dashed rgba(255,255,255,0.15)' }}>
      <Space wrap size={10} align="center">
        <Tooltip title={t('agentnotify.thumb_up', '满意')}>
          <Button size="small" type="text" aria-label="thumb-up"
            icon={fb.thumb === 'up' ? <LikeFilled style={{ color: '#52c41a' }} /> : <LikeOutlined />}
            onClick={() => save({ thumb: fb.thumb === 'up' ? null : 'up' })} />
        </Tooltip>
        <Tooltip title={t('agentnotify.thumb_down', '不满意')}>
          <Button size="small" type="text" aria-label="thumb-down"
            icon={fb.thumb === 'down' ? <DislikeFilled style={{ color: '#ff4d4f' }} /> : <DislikeOutlined />}
            onClick={() => save({ thumb: fb.thumb === 'down' ? null : 'down' })} />
        </Tooltip>
        <Rate value={fb.stars || 0} onChange={(v) => save({ stars: v })} style={{ fontSize: 16 }} />
        {fb.accepted && <Tag color="green">{t('agentnotify.accepted', '已采用')}</Tag>}
      </Space>
      <Input.TextArea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        onBlur={() => { if (comment.trim() !== (fb.comment || '')) save({ comment: comment.trim() }); }}
        placeholder={t('agentnotify.comment_placeholder', '对这张图的意见，例如：背景再亮一些，瓶子再大一点')}
        autoSize={{ minRows: 1, maxRows: 4 }}
        style={{ marginTop: 8 }}
      />
      <Space style={{ marginTop: 8 }}>
        <Button size="small" icon={<RedoOutlined />} disabled={!comment.trim()} onClick={revise}>
          {t('agentnotify.revise', '按意见修改')}
        </Button>
        <Button size="small" type="primary" icon={<CheckOutlined />} onClick={accept}>
          {t('agentnotify.accept', '采用')}
        </Button>
      </Space>
    </div>
  );
};

export default ResultFeedback;
