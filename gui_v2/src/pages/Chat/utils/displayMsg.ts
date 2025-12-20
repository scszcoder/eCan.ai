export function getDisplayMsg(content: any, t: any): string {
    // Handle string content
    if (typeof content === 'string') {
        return content || '';
    }
    
    // Handle array content
    let c = Array.isArray(content) ? content[0] : content;
    
    // Handle object content with type
    if (c && typeof c === 'object' && c !== null && 'type' in c) {
        switch (c.type) {
            case 'text':
                // If text is empty or whitespace only, return empty string
                const text = c.text?.trim();
                return text || '';
            case 'form': return t('pages.chat.lastMsg.form') || '[Form]';
            case 'image_url': return t('pages.chat.lastMsg.image') || '[Image]';
            case 'file_url': return t('pages.chat.lastMsg.file') || '[File]';
            case 'code': return t('pages.chat.lastMsg.code') || '[Code]';
            case 'system': return t('pages.chat.lastMsg.system') || '[System]';
            case 'notification': return t('pages.chat.lastMsg.notification') || '[Notification]';
            case 'card': return t('pages.chat.lastMsg.card') || '[Card]';
            case 'markdown': return t('pages.chat.lastMsg.markdown') || '[Markdown]';
            case 'table': return t('pages.chat.lastMsg.table') || '[Table]';
            default: return '';
        }
    }
    
    // Fallback: return empty string instead of showing unknown type
    return '';
} 