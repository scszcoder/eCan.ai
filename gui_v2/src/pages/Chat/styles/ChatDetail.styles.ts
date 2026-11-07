import styled from '@emotion/styled';

export const ChatDetailWrapper = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;

    /* Semi-UI theme variables are defined globally in styles/global.css for
       both themes — do not re-declare dark-only values in this scope. */

    /* 强制SemiChatWidth100% */
    .semi-chat, .semi-chat-inner {
        max-width: 100% !important;
        width: 100% !important;
        min-width: 0 !important;
        height: 100% !important;
        min-height: 0 !important;
    }

    /* Semi UI 原生附件文件标题Width调整 */
    .semi-chat-attachment-file-title {
        max-width: 400px !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }

    /* Custom附件样式 */
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

    .custom-attachment-file:hover .attachment-icon,
    .custom-attachment-file:hover .attachment-name {
        color: white !important;
    }

    .custom-attachment .attachment-icon {
        font-size: 16px;
    }

    .custom-attachment-file .attachment-icon {
        font-size: 18px;
    }

    .custom-attachment .attachment-name {
        font-size: 14px;
        word-break: break-all;
    }

    /* 聊天气泡MaximumWidthLimit为70% */
    .semi-chat-chatBox-wrap {
        max-width: 70% !important;
    }

    /* LeftMessage（Receive的Message）：Right留出30%空间 */
    .semi-chat-chatBox-wrap[style*="justify-content: flex-start"],
    .semi-chat-chatBox-wrap[style*="justify-content:flex-start"] {
        margin-right: 30% !important;
    }

    /* RightMessage（Send的Message）：Left留出30%空间 */
    .semi-chat-chatBox-wrap[style*="justify-content: flex-end"],
    .semi-chat-chatBox-wrap[style*="justify-content:flex-end"] {
        margin-left: 30% !important;
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