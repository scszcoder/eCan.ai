/**
 * Delete Confirmation Modal - Theme-aware component
 * DeleteConfirmDialog - 主题适配Component
 * 
 * A reusable delete confirmation modal that adapts to light/dark themes
 * 可复用的DeleteConfirmDialog，自动适配深色/浅色主题
 */

import React from 'react';
import { Modal, theme } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface DeleteConfirmModalOptions {
  /** Title of the modal / Dialog标题 */
  title?: string;
  /** Main confirmation message / MainConfirmMessage */
  message: string;
  /** Warning text (optional) / Warning文字（Optional） */
  warningText?: string;
  /** OK button text / ConfirmButton文字 */
  okText?: string;
  /** Cancel button text / CancelButton文字 */
  cancelText?: string;
  /** Callback when confirmed / ConfirmCallback */
  onOk: () => void | Promise<void>;
  /** Callback when cancelled / CancelCallback */
  onCancel?: () => void;
}

/**
 * Show a theme-aware delete confirmation modal
 * Display主题适配的DeleteConfirmDialog
 */
export const showDeleteConfirm = (options: DeleteConfirmModalOptions) => {
  const { token } = theme.useToken();
  const { t } = useTranslation();

  const {
    title = t('common.confirm_delete', 'ConfirmDelete'),
    message,
    warningText = t('pages.tasks.deleteWarning', '此Operation无法撤销'),
    okText = t('common.delete', 'Delete'),
    cancelText = t('common.cancel', 'Cancel'),
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
              ⚠️ {t('common.warning', 'Warning')}：{warningText}
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
 * Hook Version，Used forFunctionComponent中
 */
export const useDeleteConfirm = () => {
  const { token } = theme.useToken();
  const { t } = useTranslation();

  return React.useCallback((options: Omit<DeleteConfirmModalOptions, 'onOk'> & { onOk: () => void | Promise<void> }) => {
    const {
      title = t('common.confirm_delete', 'ConfirmDelete'),
      message,
      warningText = t('pages.tasks.deleteWarning', '此Operation无法撤销'),
      okText = t('common.delete', 'Delete'),
      cancelText = t('common.cancel', 'Cancel'),
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
                ⚠️ {t('common.warning', 'Warning')}：{warningText}
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
