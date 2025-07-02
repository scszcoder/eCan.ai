import styled from '@emotion/styled';

export const ChatDetailWrapper = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    /* 保证撑满父容器 */

    /* Semi UI 深色主题变量覆盖 */
    --semi-color-bg-0: #0f172a;
    --semi-color-bg-1: #1e293b;
    --semi-color-border: #334155;
    --semi-color-text-0: #f8fafc;
    --semi-color-text-1: #cbd5e1;
    --semi-color-text-2: #cbd5e1; /* placeholder增强 */
    --semi-color-primary: #4e40e5;
    --semi-color-primary-hover: #a5b4fc;
    --semi-color-icon-hover: #a5b4fc;
    --semi-color-fill-0: #334155;
    --semi-color-disabled-text: #64748b;
    --semi-color-link: #8b5cf6;

    /* 强制SemiChat宽度100% */
    .semi-chat, .semi-chat-inner {
        max-width: 100% !important;
        width: 100% !important;
        min-width: 0 !important;
        height: 100% !important;
        min-height: 0 !important;
    }

    /* Semi UI 原生附件文件标题宽度调整 */
    .semi-chat-attachment-file-title {
        max-width: 400px !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }

    /* 自定义附件样式 */
    .custom-attachment {
        display: inline-block;
        margin: 4px 8px 4px 0;
        padding: 8px 12px;
        background-color: var(--semi-color-fill-0);
        border-radius: 8px;
        border: 1px solid var(--semi-color-border);
        cursor: pointer;
        transition: all 0.2s ease;
        max-width: 100% !important;
        overflow: hidden !important;
    }

    .custom-attachment:hover {
        background-color: var(--semi-color-fill-1);
        border-color: var(--semi-color-primary);
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .custom-attachment-image {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--semi-color-link);
    }

    .custom-attachment-file {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--semi-color-text-1);
    }

    .custom-attachment-file:hover {
        background-color: var(--semi-color-primary);
        color: white;
    }

    .custom-attachment-file:hover .attachment-icon {
        color: white !important;
    }

    .custom-attachment-file:hover .attachment-name {
        color: white !important;
    }

    /* 只针对自定义附件中的图标和名称 */
    .custom-attachment .attachment-icon {
        font-size: 16px;
    }

    .custom-attachment .attachment-name {
        font-size: 14px;
        word-break: break-all;
    }

    /* 文件类型图标样式 */
    .custom-attachment-file .attachment-icon {
        font-size: 18px;
    }
`;

export const commonOuterStyle = {
    border: '1px solid var(--semi-color-border)',
    borderRadius: '16px',
    height: '100%',
    width: '100%',
    display: 'flex',
    flexDirection: 'column' as 'column',
    overflow: 'hidden'
}; 