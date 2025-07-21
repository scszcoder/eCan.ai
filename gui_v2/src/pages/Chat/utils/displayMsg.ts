export function getDisplayMsg(content: any, t: any): string {
    if (typeof content === 'string') return content;
    let c = Array.isArray(content) ? content[0] : content;
    if (c && typeof c === 'object' && c !== null && 'type' in c) {
        switch (c.type) {
            case 'text': return c.text || t('pages.chat.noMessages');
            case 'form': return t('pages.chat.lastMsg.text');
            case 'image_url': return t('pages.chat.lastMsg.image');
            case 'file_url': return t('pages.chat.lastMsg.file');
            case 'code': return t('pages.chat.lastMsg.code');
            case 'system': return t('pages.chat.lastMsg.system');
            case 'notification': return t('pages.chat.lastMsg.notification');
            case 'card': return t('pages.chat.lastMsg.card');
            case 'markdown': return t('pages.chat.lastMsg.markdown');
            case 'table': return t('pages.chat.lastMsg.table');
            default: return t('pages.chat.lastMsg.unknownType');
        }
    }
    return t('pages.chat.lastMsg.unknownType');
} 