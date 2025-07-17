export function getDisplayMsg(content: any, t: any): string {
    if (typeof content === 'string') return content;
    let c = Array.isArray(content) ? content[0] : content;
    if (c && typeof c === 'object' && c !== null && 'type' in c) {
        switch (c.type) {
            case 'text': return c.text || t('pages.chat.noMessages');
            case 'form': return t('pages.chat.form');
            case 'image_url': return t('pages.chat.image');
            case 'file_url': return t('pages.chat.file');
            case 'code': return t('pages.chat.code');
            case 'system': return t('pages.chat.system');
            case 'notification': return t('pages.chat.notification');
            case 'card': return t('pages.chat.card');
            case 'markdown': return t('pages.chat.markdown');
            case 'table': return t('pages.chat.table');
            default: return t('pages.chat.unknownType');
        }
    }
    return t('pages.chat.unknownType');
} 