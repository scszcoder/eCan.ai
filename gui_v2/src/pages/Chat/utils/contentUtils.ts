// 内容结构化处理工具，供内容渲染等复用

/**
 * 处理字符串内容，将附件标记转换为结构化格式
 * @param content 包含附件标记的字符串内容
 * @returns 结构化的内容对象
 */
export function processStringContent(content: string): any {
  if (!content || typeof content !== 'string') {
    return content;
  }

  // 检查是否包含附件标记
  const attachmentRegex = /\[(image|file)\|(pyqtfile:\/\/[^|]+|[^|]+)\|([^|]+)\|([^\]]+)\]/g;
  const matches = Array.from(content.matchAll(attachmentRegex));
  
  if (matches.length === 0) {
    return content; // 没有附件标记，返回原字符串
  }

  // 提取文本部分
  let textContent = content;
  const attachments: any[] = [];

  // 处理每个附件标记
  matches.forEach((match) => {
    const [fullMatch, type, filePath, fileName, mimeType] = match;
    const isImage = type === 'image';
    
    // 从文本中移除附件标记
    textContent = textContent.replace(fullMatch, '');
    
    // 创建附件对象
    attachments.push({
      type: isImage ? 'image_url' : 'file_url',
      url: filePath,
      name: fileName,
      size: '', // 暂时为空
      fileType: mimeType
    });
  });

  // 清理文本内容
  textContent = textContent.trim();

  // 如果有多个附件，返回复合内容
  if (attachments.length > 1) {
    return {
      type: 'text',
      text: textContent,
      attachments: attachments
    };
  }

  // 如果只有一个附件，返回对应的内容类型
  if (attachments.length === 1) {
    const attachment = attachments[0];
    if (attachment.type === 'image_url') {
      return {
        type: 'image_url',
        image_url: {
          url: attachment.url
        }
      };
    } else {
      return {
        type: 'file_url',
        file_url: {
          url: attachment.url,
          name: attachment.name,
          size: attachment.size,
          type: attachment.fileType
        }
      };
    }
  }

  // 只有文本内容
  return textContent || '';
} 