/**
 * Delete Confirmation Modal - Theme-aware component
 * 删除确认对话框 - 主题适配组件
 * 
 * A reusable delete confirmation modal that adapts to light/dark themes
 * 可复用的删除确认对话框，自动适配深色/浅色主题
 */

import React from 'react';
import { Modal, theme } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface DeleteConfirmModalOptions {
  /** Title of the modal / 对话框标题 */
  title?: string;
  /** Main confirmation message / 主要确认消息 */
  message: string;
  /** Warning text (optional) / 警告文字（可选） */
  warningText?: string;
  /** OK button text / 确认按钮文字 */
  okText?: string;
  /** Cancel button text / 取消按钮文字 */
  cancelText?: string;
  /** Callback when confirmed / 确认回调 */
  onOk: () => void | Promise<void>;
  /** Callback when cancelled / 取消回调 */
  onCancel?: () => void;
}

/**
 * Show a theme-aware delete confirmation modal
 * 显示主题适配的删除确认对话框
 */
export const showDeleteConfirm = (options: DeleteConfirmModalOptions) => {
  const { token } = theme.useToken();
  const { t } = useTranslation();

  const {
    title = t('common.confirm_delete', '确认删除'),
    message,
    warningText = t('pages.tasks.deleteWarning', '此操作无法撤销'),
    okText = t('common.delete', '删除'),
    cancelText = t('common.cancel', '取消'),
    onOk,
    onCancel,
  } = options;

  Modal.confirm({
    title: (
      <span style={{ fontSize: '16px', fontWeight: 600, color: token.colorText }}>
        {title}
      </span>
    ),
    icon: <ExclamationCircleOutlined style={{ color: token.colorError, fontSize: '22px' }} />,
    content: (
      <div style={{ marginTop: '12px' }}>
        <p style={{ 
          fontSize: '14px', 
          lineHeight: '1.6', 
          marginBottom: '12px',
          color: token.colorText
        }}>
          {message}
        </p>
        {warningText && (
          <div style={{ 
            padding: '12px', 
            background: token.colorErrorBg,
            borderRadius: '8px',
            border: `1px solid ${token.colorErrorBorder}`
          }}>
            <span style={{ fontSize: '13px', color: token.colorError }}>
              ⚠️ {t('common.warning', '警告')}：{warningText}
            </span>
          </div>
        )}
      </div>
    ),
    okText,
    okType: 'danger',
    cancelText,
    width: 480,
    centered: true,
    maskClosable: true,
    okButtonProps: {
      style: { 
        borderRadius: '6px',
        height: '36px',
        fontSize: '14px',
        fontWeight: 500
      }
    },
    cancelButtonProps: {
      style: { 
        borderRadius: '6px',
        height: '36px',
        fontSize: '14px'
      }
    },
    onOk,
    onCancel,
  });
};

/**
 * Hook version for use in functional components
 * Hook 版本，用于函数组件中
 */
export const useDeleteConfirm = () => {
  const { token } = theme.useToken();
  const { t } = useTranslation();

  return React.useCallback((options: Omit<DeleteConfirmModalOptions, 'onOk'> & { onOk: () => void | Promise<void> }) => {
    const {
      title = t('common.confirm_delete', '确认删除'),
      message,
      warningText = t('pages.tasks.deleteWarning', '此操作无法撤销'),
      okText = t('common.delete', '删除'),
      cancelText = t('common.cancel', '取消'),
      onOk,
      onCancel,
    } = options;

    Modal.confirm({
      title: (
        <span style={{ fontSize: '16px', fontWeight: 600, color: token.colorText }}>
          {title}
        </span>
      ),
      icon: <ExclamationCircleOutlined style={{ color: token.colorError, fontSize: '22px' }} />,
      content: (
        <div style={{ marginTop: '12px' }}>
          <p style={{ 
            fontSize: '14px', 
            lineHeight: '1.6', 
            marginBottom: '12px',
            color: token.colorText
          }}>
            {message}
          </p>
          {warningText && (
            <div style={{ 
              padding: '12px', 
              background: token.colorErrorBg,
              borderRadius: '8px',
              border: `1px solid ${token.colorErrorBorder}`
            }}>
              <span style={{ fontSize: '13px', color: token.colorError }}>
                ⚠️ {t('common.warning', '警告')}：{warningText}
              </span>
            </div>
          )}
        </div>
      ),
      okText,
      okType: 'danger',
      cancelText,
      width: 480,
      centered: true,
      maskClosable: true,
      okButtonProps: {
        style: { 
          borderRadius: '6px',
          height: '36px',
          fontSize: '14px',
          fontWeight: 500
        }
      },
      cancelButtonProps: {
        style: { 
          borderRadius: '6px',
          height: '36px',
          fontSize: '14px'
        }
      },
      onOk,
      onCancel,
    });
  }, [token, t]);
};

export default useDeleteConfirm;
