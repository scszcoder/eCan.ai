import React, { useState } from 'react';
import { Typography, Banner, Table, Button } from '@douyinfe/semi-ui';
import { IconCode, IconInfoCircle, IconTick, IconAlertTriangle } from '@douyinfe/semi-icons';
import ReactMarkdown from 'react-markdown';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { docco } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { Content } from '../types/chat';
import { DynamicForm } from './FormField';
import { processStringContent } from '../utils/contentUtils';
import { useTranslation } from 'react-i18next';

// 移除 parseAttachment、AttachmentRenderer、AttachmentsContent 相关逻辑

// 基础的文本内容渲染
const TextContent: React.FC<{ text?: string }> = ({ text }) => {
  const { t } = useTranslation();
  if (!text?.trim()) return null;
  return (
    <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
      {text}
    </Typography.Paragraph>
  );
};

// 代码块渲染
const CodeContent: React.FC<{ code?: { lang: string; value: string } }> = ({ code }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  
  if (!code?.value) return null;
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code.value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="code-block" style={{ position: 'relative', marginBottom: 16 }}>
      <div style={{ 
        padding: '8px 16px', 
        backgroundColor: '#282a36', 
        color: '#f8f8f2', 
        borderTopLeftRadius: 4, 
        borderTopRightRadius: 4,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <IconCode />
          <span>{code.lang || t('pages.chat.codeText')}</span>
        </div>
        <Button 
          size="small" 
          theme="borderless" 
          type={copied ? "tertiary" : "primary"}
          onClick={handleCopy}
        >
          {copied ? t('pages.chat.copied') : t('pages.chat.copy')}
        </Button>
      </div>
      <SyntaxHighlighter 
        language={code.lang || 'text'} 
        style={docco}
        customStyle={{ margin: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}
      >
        {code.value}
      </SyntaxHighlighter>
    </div>
  );
};

// 系统消息渲染
const SystemContent: React.FC<{ system?: { text: string; level: string } }> = ({ system }) => {
  const { t } = useTranslation();
  if (!system?.text) return null;
  
  const getIcon = (level: string) => {
    switch (level) {
      case 'info': return <IconInfoCircle size="large" style={{ color: 'var(--semi-color-info)' }} />;
      case 'success': return <IconTick size="large" style={{ color: 'var(--semi-color-success)' }} />;
      case 'warning': return <IconAlertTriangle size="large" style={{ color: 'var(--semi-color-warning)' }} />;
      case 'error': return <IconAlertTriangle size="large" style={{ color: 'var(--semi-color-danger)' }} />;
      default: return <IconInfoCircle size="large" style={{ color: 'var(--semi-color-info)' }} />;
    }
  };
  
  return (
    <div className={`system-message system-${system.level}`} style={{ 
      display: 'flex', 
      gap: 12, 
      padding: 12, 
      backgroundColor: `var(--semi-color-${system.level}-light)`,
      borderRadius: 4,
      marginBottom: 16
    }}>
      {getIcon(system.level)}
      <Typography.Text>{t(system.text) || system.text}</Typography.Text>
    </div>
  );
};

// 通知内容渲染
const NotificationContent: React.FC<{ notification?: { title: string; content: string; level: string } }> = ({ notification }) => {
  const { t } = useTranslation();
  if (!notification) return null;
  
  return (
    <Banner
      type={notification.level as any}
      title={t(notification.title) || notification.title}
      description={t(notification.content) || notification.content}
      closeIcon={null}
      style={{ marginBottom: 16 }}
    />
  );
};

// 卡片内容渲染
const CardContent: React.FC<{ 
  card?: { title: string; content: string; actions: Array<{ text: string; type: string; action: string }> };
  onCardAction?: (action: string) => void;
}> = ({ card, onCardAction }) => {
  const { t } = useTranslation();
  if (!card) return null;
  
  return (
    <div className="card-container" style={{ 
      border: '1px solid var(--semi-color-border)',
      borderRadius: 4,
      padding: 16,
      marginBottom: 16
    }}>
      <Typography.Title heading={5}>{t(card.title) || card.title}</Typography.Title>
      <Typography.Paragraph style={{ marginBottom: 16 }}>{t(card.content) || card.content}</Typography.Paragraph>
      
      {card.actions?.length > 0 && (
        <div className="card-actions" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          {card.actions.map((action, index) => (
            <Button
              key={index}
              type={action.type as any}
              onClick={() => onCardAction?.(action.action)}
            >
              {t(action.text) || action.text}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};

// Markdown内容渲染
const MarkdownContent: React.FC<{ markdown?: string }> = ({ markdown }) => {
  const { t } = useTranslation();
  if (!markdown) return null;
  
  return (
    <div className="markdown-container" style={{ marginBottom: 16 }}>
      <ReactMarkdown>{markdown}</ReactMarkdown>
    </div>
  );
};

// 表格内容渲染
const TableContent: React.FC<{ table?: { headers: string[]; rows: any[][] } }> = ({ table }) => {
  const { t } = useTranslation();
  if (!table?.headers?.length || !table.rows?.length) return null;
  
  // 构建Semi UI Table需要的columns和dataSource
  const columns = table.headers.map((header, index) => ({
    title: t(header) || header,
    dataIndex: `col${index}`,
    key: `col${index}`
  }));
  
  const dataSource = table.rows.map((row, rowIndex) => {
    const rowData: any = { key: `row${rowIndex}` };
    
    row.forEach((cell, cellIndex) => {
      rowData[`col${cellIndex}`] = cell;
    });
    
    return rowData;
  });
  
  return (
    <Table
      columns={columns}
      dataSource={dataSource}
      size="small"
      pagination={false}
      style={{ marginBottom: 16 }}
    />
  );
};

// 附件渲染组件，之后引入原来的附件处理组件
const ImageUrlContent: React.FC<{ image_url?: { url: string } }> = ({ image_url }) => {
  const { t } = useTranslation();
  if (!image_url?.url) return null;
  
  return (
    <div style={{ marginBottom: 16, maxWidth: '100%' }}>
      <img 
        src={image_url.url} 
        alt={t('pages.chat.imageAttachmentAlt')}
        style={{ maxWidth: '100%', borderRadius: 4 }} 
      />
    </div>
  );
};

const FileUrlContent: React.FC<{ file_url?: { url: string; name: string; size: string; type: string } }> = ({ file_url }) => {
  const { t } = useTranslation();
  if (!file_url?.url) return null;
  
  return (
    <div 
      className="file-attachment" 
      style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: 8,
        padding: '8px 12px',
        border: '1px solid var(--semi-color-border)',
        borderRadius: 4,
        marginBottom: 16,
        maxWidth: 300,
        cursor: 'pointer'
      }}
      onClick={() => window.open(file_url.url, '_blank')}
    >
      <IconInfoCircle />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Typography.Text ellipsis>{file_url.name}</Typography.Text>
        <Typography.Text size="small" type="tertiary">{file_url.size}</Typography.Text>
      </div>
    </div>
  );
};

// 主内容类型渲染器组件
interface ContentTypeRendererProps {
  content: Content | string;
  onFormSubmit?: (formId: string, values: any) => void;
  onCardAction?: (action: string) => void;
}

const ContentTypeRenderer: React.FC<ContentTypeRendererProps> = ({ content, onFormSubmit, onCardAction }) => {
  const { t } = useTranslation();
  // 1. 预处理字符串内容，支持富内容解析
  let parsedContent = content;
  if (typeof content === 'string') {
    parsedContent = processStringContent(content);
  }

  // 2. 根据结构化内容类型分支渲染
  if (typeof parsedContent === 'string') {
    return <TextContent text={parsedContent} />;
  }
  if (parsedContent && typeof parsedContent === 'object') {
    // 支持 text+attachments 混合内容
    if (
      parsedContent.type === 'text' &&
      Array.isArray((parsedContent as any).attachments)
    ) {
      const attachments = (parsedContent as any).attachments;
      return (
        <div>
          <TextContent text={(parsedContent as any).text} />
          {attachments.map((att: any, idx: number) =>
            att.type === 'image_url' && att.url
              ? <ImageUrlContent key={idx} image_url={{ url: att.url }} />
              : att.type === 'file_url' && att.url
                ? <FileUrlContent key={idx} file_url={{ url: att.url, name: att.name, size: att.size, type: att.fileType }} />
                : null
          )}
        </div>
      );
    }
    // 支持单一 image_url/file_url 结构
    if (
      parsedContent.type === 'image_url' &&
      ((parsedContent as any).image_url || (parsedContent as any).url)
    ) {
      const url = (parsedContent as any).image_url?.url || (parsedContent as any).url;
      return <ImageUrlContent image_url={{ url }} />;
    }
    if (
      parsedContent.type === 'file_url' &&
      ((parsedContent as any).file_url || (parsedContent as any).url)
    ) {
      const file = (parsedContent as any).file_url || parsedContent;
      // file 需有 url、name、size、type
      return <FileUrlContent file_url={{
        url: file.url,
        name: file.name || '',
        size: file.size || '',
        type: file.type || file.fileType || ''
      }} />;
    }
    // 其它类型走原有 switch
    switch (parsedContent.type) {
      case 'text':
        return (
          <div>
            <TextContent text={(parsedContent as any).text} />
          </div>
        );
      case 'code':
        return <CodeContent code={parsedContent.code} />;
      case 'system':
        return <SystemContent system={parsedContent.system} />;
      case 'notification':
        return <NotificationContent notification={parsedContent.notification} />;
      case 'form': {
        const formData = (parsedContent as any).form || parsedContent;
        if (formData && typeof formData === 'object' && Array.isArray((formData as any).fields)) {
          return <DynamicForm form={formData} onFormSubmit={onFormSubmit} />;
        }
        return <div>{t('pages.chat.noFormContent')}</div>;
      }
      case 'card':
        return <CardContent card={parsedContent.card} onCardAction={onCardAction} />;
      case 'markdown':
        return <MarkdownContent markdown={parsedContent.markdown} />;
      case 'table':
        return <TableContent table={parsedContent.table} />;
      case 'image_url':
        return <ImageUrlContent image_url={parsedContent.image_url} />;
      case 'file_url':
        return <FileUrlContent file_url={parsedContent.file_url} />;
      default:
        return <TextContent text={JSON.stringify(parsedContent)} />;
    }
  }
  // fallback
  return <TextContent text={JSON.stringify(content)} />;
};

export default ContentTypeRenderer; 