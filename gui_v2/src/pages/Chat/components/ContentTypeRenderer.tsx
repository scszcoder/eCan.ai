import React, { useState, useEffect, useMemo } from 'react';
import { Typography, Banner, Table, Button } from '@douyinfe/semi-ui';
import { IconCode, IconInfoCircle, IconTick, IconAlertTriangle } from '@douyinfe/semi-icons';
import { Content } from '../types/chat';
import DynamicForm from './FormField';
import { processStringContent } from '../utils/contentUtils';
import { useTranslation } from 'react-i18next';


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
  const [Highlighter, setHighlighter] = useState<any>(null);
  const [style, setStyle] = useState<any>(null);
  
  if (!code?.value) return null;
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code.value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  useEffect(() => {
    let mounted = true;
    Promise.all([
      import('react-syntax-highlighter').then(m => m.Light),
      import('react-syntax-highlighter/dist/esm/styles/hljs').then(m => m.docco)
    ]).then(([HighlighterComp, styleObj]) => {
      if (!mounted) return;
      setHighlighter(() => HighlighterComp);
      setStyle(styleObj);
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);
  
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
      {Highlighter && style ? (
        <Highlighter 
          language={code.lang || 'text'} 
          style={style}
          customStyle={{ margin: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}
        >
          {code.value}
        </Highlighter>
      ) : (
        <pre style={{ margin: 0, padding: 12, background: '#0b1020', color: '#f8f8f2', borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
          {code.value}
        </pre>
      )}
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

// 通用渲染函数
const renderGenericContent = (key: string, value: any, t: any): React.ReactNode => {
  if (value === null || value === undefined) return null;
  
  // 处理不同数据类型
  if (typeof value === 'string') {
    // 特殊处理包含统计信息的字符串
    if (value.includes('Statistics:')) {
      const parts = value.split('Statistics:');
      const mainContent = parts[0].trim();
      const statsContent = parts[1]?.trim();
      
      return (
        <div>
          {mainContent && (
            <Typography.Text style={{ lineHeight: 1.6, display: 'block', marginBottom: statsContent ? 16 : 0 }}>
              {mainContent}
            </Typography.Text>
          )}
          {statsContent && (
            <div style={{
              padding: 12,
              backgroundColor: 'var(--semi-color-bg-2)',
              borderRadius: 6,
              border: '1px solid var(--semi-color-border)'
            }}>
              <Typography.Text strong style={{ display: 'block', marginBottom: 8, fontSize: '13px' }}>
                {t('pages.chat.notification.statistics') || 'Statistics'}
              </Typography.Text>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 }}>
                {statsContent.split(',').map((stat, index) => {
                  const [statKey, statValue] = stat.trim().split(':');
                  return statKey && statValue ? (
                    <div key={index} style={{
                      padding: '6px 8px',
                      backgroundColor: 'var(--semi-color-fill-0)',
                      borderRadius: 4,
                      textAlign: 'center'
                    }}>
                      <Typography.Text size="small" type="secondary" style={{ display: 'block' }}>
                        {statKey.trim().replace(/_/g, ' ')}
                      </Typography.Text>
                      <Typography.Text strong style={{ color: 'var(--semi-color-primary)', fontSize: '14px' }}>
                        {statValue.trim()}
                      </Typography.Text>
                    </div>
                  ) : null;
                })}
              </div>
            </div>
          )}
        </div>
      );
    }
    
    // 普通字符串
    return (
      <Typography.Text style={{ lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
        {value}
      </Typography.Text>
    );
  }
  
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <Typography.Text>{String(value)}</Typography.Text>;
  }
  
  if (Array.isArray(value)) {
    if (value.length === 0) return <Typography.Text type="secondary">Empty array</Typography.Text>;
    
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {value.map((item, index) => (
          <div key={index} style={{
            padding: 8,
            backgroundColor: 'var(--semi-color-fill-0)',
            borderRadius: 4,
            marginBottom: 8
          }}>
            {typeof item === 'string' ? (
              <Typography.Text>{item}</Typography.Text>
            ) : (
              renderGenericContent(`${key}_${index}`, item, t)
            )}
          </div>
        ))}
      </div>
    );
  }
  
  if (typeof value === 'object') {
    // 特殊处理已知的对象结构
    if (value.isError && value.content) {
      return (
        <div style={{
          padding: 12,
          backgroundColor: 'var(--semi-color-danger-light-default)',
          border: '1px solid var(--semi-color-danger-light-active)',
          borderRadius: 6,
          borderLeft: '4px solid var(--semi-color-danger)'
        }}>
          <Typography.Text style={{ color: 'var(--semi-color-danger)', lineHeight: 1.5 }}>
            {value.content?.[0]?.text || 'An error occurred'}
          </Typography.Text>
        </div>
      );
    }
    
    // 表格数据处理
    if (Object.keys(value).length > 0 && Object.values(value).every(v => typeof v === 'object' && v !== null)) {
      const firstValue = Object.values(value)[0] as any;
      if (typeof firstValue === 'object' && firstValue !== null) {
        const criteriaKeys = Object.keys(firstValue);
        
        return (
          <Table
            dataSource={Object.entries(value).map(([k, v]) => ({
              key: k,
              ...(typeof v === 'object' && v !== null ? v as Record<string, any> : {})
            }))}
            columns={[
              { title: t('pages.chat.notification.product') || 'Item', dataIndex: 'key', key: 'key' },
              ...criteriaKeys.map(criteria => ({
                title: criteria,
                dataIndex: criteria,
                key: criteria
              }))
            ]}
            pagination={false}
            size="small"
          />
        );
      }
    }
    
    // 统计数据网格处理
    if (Object.values(value).every(v => typeof v === 'number' || typeof v === 'string')) {
      return (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 12
        }}>
          {Object.entries(value).map(([k, v]) => (
            <div key={k} style={{
              padding: '12px 16px',
              backgroundColor: 'var(--semi-color-bg-2)',
              borderRadius: 6,
              border: '1px solid var(--semi-color-border)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center'
            }}>
              <Typography.Text size="small" type="secondary" style={{
                display: 'block',
                marginBottom: 6,
                fontSize: '12px',
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                {k.replace(/_/g, ' ')}
              </Typography.Text>
              <Typography.Title heading={4} style={{
                margin: 0,
                color: 'var(--semi-color-primary)',
                fontWeight: 600,
                fontSize: '20px'
              }}>
                {String(v)}
              </Typography.Title>
            </div>
          ))}
        </div>
      );
    }
    
    // 通用对象渲染
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>
              {k.replace(/_/g, ' ')}:
            </Typography.Text>
            <div style={{ marginLeft: 16 }}>
              {renderGenericContent(k, v, t)}
            </div>
          </div>
        ))}
      </div>
    );
  }
  
  return <Typography.Text>{String(value)}</Typography.Text>;
};

// 通知内容渲染
const NotificationContent: React.FC<{ notification?: any }> = ({ notification }) => {
  const { t } = useTranslation();
  if (!notification) return null;
  
  // 处理新的嵌套结构
  const actualNotification = notification.content?.notification || notification;
  const { title, ...otherFields } = actualNotification;
  
  // 如果只有简单的字符串内容且没有其他字段，使用简单格式
  if (Object.keys(otherFields).length === 1 && typeof otherFields.content === 'string') {
    return (
      <Banner
        type={actualNotification.level as any || 'info'}
        title={t(title) || title}
        description={t(otherFields.content) || otherFields.content}
        closeIcon={null}
        style={{ marginBottom: 16 }}
      />
    );
  }
  
  return (
    <div className="enhanced-notification" style={{ 
      border: '1px solid var(--semi-color-border)',
      borderRadius: 8,
      padding: 16,
      marginBottom: 16,
      backgroundColor: 'var(--semi-color-bg-1)'
    }}>
      {/* 标题 */}
      {title && (
        <Typography.Title heading={4} style={{ marginBottom: 12 }}>
          {t(title) || title}
        </Typography.Title>
      )}
      
      {/* 动态渲染所有其他字段 */}
      {Object.entries(otherFields).map(([key, value]) => (
        <div key={key} style={{ marginBottom: 16 }}>
          <Typography.Title heading={5} style={{ marginBottom: 8, color: 'var(--semi-color-text-1)' }}>
            {t(`pages.chat.notification.${key}`) || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </Typography.Title>
          <div style={{ 
            padding: 16,
            backgroundColor: 'var(--semi-color-fill-0)',
            border: '1px solid var(--semi-color-border)',
            borderRadius: 8
          }}>
            {renderGenericContent(key, value, t)}
          </div>
        </div>
      ))}
      
      {/* 特殊处理链接字段 */}
      {otherFields.behind_the_scene && (
        <div style={{ marginBottom: 16 }}>
          <a href={otherFields.behind_the_scene} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--semi-color-primary)' }}>
            {t('pages.chat.notification.viewDetails') || 'View Details'}
          </a>
        </div>
      )}
      
      {/* 特殊处理反馈选项 */}
      {otherFields.show_feedback_options && (
        <div style={{ 
          display: 'flex', 
          gap: 8, 
          paddingTop: 12, 
          borderTop: '1px solid var(--semi-color-border)' 
        }}>
          <Button size="small" type="tertiary" icon={<IconTick />}>
            {t('pages.chat.notification.helpful') || 'Helpful'}
          </Button>
          <Button size="small" type="tertiary" icon={<IconAlertTriangle />}>
            {t('pages.chat.notification.notHelpful') || 'Not Helpful'}
          </Button>
        </div>
      )}
    </div>
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
  const [MD, setMD] = useState<any>(null);
  if (!markdown) return null;
  useEffect(() => {
    let mounted = true;
    import('react-markdown').then(m => {
      if (mounted) setMD(() => m.default);
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);
  
  return (
    <div className="markdown-container" style={{ marginBottom: 16 }}>
      {MD ? <MD>{markdown}</MD> : <pre style={{ whiteSpace: 'pre-wrap' }}>{markdown}</pre>}
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
  chatId?: string;
  messageId?: string;
  onFormSubmit?: (
    formId: string,
    values: any,
    chatId?: string,
    messageId?: string,
    processedForm?: any
  ) => void;
  onCardAction?: (action: string) => void;
}

const ContentTypeRenderer: React.FC<ContentTypeRendererProps> = ({ content, chatId, messageId, onFormSubmit, onCardAction }) => {
  const { t } = useTranslation();
  // 1. 预处理字符串内容，支持富内容解析
  const parsedContent = useMemo(() => {
    if (typeof content === 'string') return processStringContent(content);
    return content;
  }, [content]);

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
        if (formData && typeof formData === 'object') {
          // 优先用 chatId/messageId 变量
          const chatIdToUse = chatId || (parsedContent as any).chatId || (parsedContent as any).chat_id;
          const messageIdToUse = messageId || (parsedContent as any).messageId || (parsedContent as any).message_id || (parsedContent as any).id;
          return <DynamicForm form={formData} chatId={chatIdToUse} messageId={messageIdToUse} onFormSubmit={onFormSubmit} />;
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

export default React.memo(ContentTypeRenderer); 