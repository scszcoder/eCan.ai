// Content结构化ProcessTool，供ContentRender等复用

/**
 * Process字符串Content，将附件标记Convert为结构化格式
 * @param content Include附件标记的字符串Content
 * @returns 结构化的Content对象
 */
export function processStringContent(content: string): any {
  if (!content || typeof content !== 'string') {
    return content;
  }

  // Check是否Include附件标记
  const attachmentRegex = /\[(image|file)\|(pyqtfile:\/\/[^|]+|[^|]+)\|([^|]+)\|([^\]]+)\]/g;
  const matches = Array.from(content.matchAll(attachmentRegex));
  
  if (matches.length === 0) {
    return content; // 没有附件标记，返回原字符串
  }

  // 提取文本部分
  let textContent = content;
  const attachments: any[] = [];

  // Process每个附件标记
  matches.forEach((match) => {
    const [fullMatch, type, filePath, fileName, mimeType] = match;
    const isImage = type === 'image';
    
    // 从文本中Remove附件标记
    textContent = textContent.replace(fullMatch, '');
    
    // Create附件对象
    attachments.push({
      type: isImage ? 'image_url' : 'file_url',
      url: filePath,
      name: fileName,
      size: '', // 暂时为空
      fileType: mimeType
    });
  });

  // Cleanup文本Content
  textContent = textContent.trim();

  // If有多个附件，返回复合Content
  if (attachments.length > 1) {
    return {
      type: 'text',
      text: textContent,
      attachments: attachments
    };
  }

  // If只有一个附件，返回对应的ContentType
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

  // 只有文本Content
  return textContent || '';
} 