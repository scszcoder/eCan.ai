import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Card, 
  Button, 
  Space, 
  Input, 
  Select, 
  Form, 
  message,
  Modal,
  Tooltip,
  Divider
} from 'antd';
import { 
  SaveOutlined,
  EyeOutlined,
  EditOutlined,
  UndoOutlined,
  RedoOutlined,
  BoldOutlined,
  ItalicOutlined,
  UnderlineOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
  LinkOutlined,
  PictureOutlined,
  CodeOutlined,
  TableOutlined
} from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;

interface DocumentEditorProps {
  initialData?: {
    title: string;
    content: string;
    category: string;
    tags: string[];
  };
  onSave: (data: any) => void;
  onCancel: () => void;
}

const DocumentEditor: React.FC<DocumentEditorProps> = ({
  initialData,
  onSave,
  onCancel
}) => {
  const [isPreview, setIsPreview] = useState(false);
  const [title, setTitle] = useState(initialData?.title || '');
  const [content, setContent] = useState(initialData?.content || '');
  const [category, setCategory] = useState(initialData?.category || '');
  const [tags, setTags] = useState<string[]>(initialData?.tags || []);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [form] = Form.useForm();
  const { t } = useTranslation();

  // 插入Markdown语法
  const insertMarkdown = (syntax: string, placeholder?: string) => {
    if (!textareaRef.current) return;
    
    const textarea = textareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = content.substring(start, end);
    
    let insertText = syntax;
    if (placeholder && !selectedText) {
      insertText = syntax.replace('{text}', placeholder);
    } else if (selectedText) {
      insertText = syntax.replace('{text}', selectedText);
    }
    
    const newContent = content.substring(0, start) + insertText + content.substring(end);
    setContent(newContent);
    
    // Settings光标Position
    setTimeout(() => {
      if (textareaRef.current) {
        const newCursorPos = start + insertText.length;
        textareaRef.current.setSelectionRange(newCursorPos, newCursorPos);
        textareaRef.current.focus();
      }
    }, 0);
  };

  // Tool栏ButtonConfiguration
  const toolbarButtons = [
    {
      icon: <BoldOutlined />,
      tooltip: t('pages.knowledge.documentEditor.bold'),
      action: () => insertMarkdown('**{text}**', t('pages.knowledge.documentEditor.boldText')),
    },
    {
      icon: <ItalicOutlined />,
      tooltip: t('pages.knowledge.documentEditor.italic'),
      action: () => insertMarkdown('*{text}*', t('pages.knowledge.documentEditor.italicText')),
    },
    {
      icon: <UnderlineOutlined />,
      tooltip: t('pages.knowledge.documentEditor.underline'),
      action: () => insertMarkdown('<u>{text}</u>', t('pages.knowledge.documentEditor.underlineText')),
    },
    { divider: true },
    {
      icon: <UnorderedListOutlined />,
      tooltip: t('pages.knowledge.documentEditor.unorderedList'),
      action: () => insertMarkdown('- {text}', t('pages.knowledge.documentEditor.listItem')),
    },
    {
      icon: <OrderedListOutlined />,
      tooltip: t('pages.knowledge.documentEditor.orderedList'),
      action: () => insertMarkdown('1. {text}', t('pages.knowledge.documentEditor.listItem')),
    },
    { divider: true },
    {
      icon: <LinkOutlined />,
      tooltip: t('pages.knowledge.documentEditor.link'),
      action: () => insertMarkdown('[{text}](url)', t('pages.knowledge.documentEditor.linkText')),
    },
    {
      icon: <PictureOutlined />,
      tooltip: t('pages.knowledge.documentEditor.image'),
      action: () => insertMarkdown('![{text}](url)', t('pages.knowledge.documentEditor.imageDescription')),
    },
    {
      icon: <CodeOutlined />,
      tooltip: t('pages.knowledge.documentEditor.codeBlock'),
      action: () => insertMarkdown('```\n{text}\n```', t('pages.knowledge.documentEditor.codeContent')),
    },
    {
      icon: <TableOutlined />,
      tooltip: t('pages.knowledge.documentEditor.table'),
      action: () => insertMarkdown(t('pages.knowledge.documentEditor.tableSnippet'), ''),
    },
  ];

  // ProcessSave
  const handleSave = async () => {
    if (!title.trim()) {
      message.error(t('pages.knowledge.documentEditor.titleRequired'));
      return;
    }
    if (!content.trim()) {
      message.error(t('pages.knowledge.documentEditor.contentRequired'));
      return;
    }
    if (!category) {
      message.error(t('pages.knowledge.documentEditor.categoryRequired'));
      return;
    }

    try {
      await form.validateFields();
      const data = {
        title: title.trim(),
        content: content.trim(),
        category,
        tags,
        updatedAt: new Date().toISOString(),
      };
      onSave(data);
      message.success(t('pages.knowledge.documentEditor.saveSuccess'));
    } catch (error) {
      console.error('SaveFailed:', error);
    }
  };

  // Process快捷键
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey) {
      switch (e.key) {
        case 's':
          e.preventDefault();
          handleSave();
          break;
        case 'b':
          e.preventDefault();
          insertMarkdown('**{text}**', t('pages.knowledge.documentEditor.boldText'));
          break;
        case 'i':
          e.preventDefault();
          insertMarkdown('*{text}*', t('pages.knowledge.documentEditor.italicText'));
          break;
      }
    }
  };

  // RenderMarkdown预览
  const renderMarkdownPreview = () => {
    // Simple的MarkdownRender（实际项目中Can使用marked.js等库）
    const renderContent = content
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/^- (.*$)/gim, '<li>$1</li>')
      .replace(/^1\. (.*$)/gim, '<li>$1</li>')
      .replace(/\n/g, '<br>');

    return (
      <div 
        style={{ 
          padding: '16px', 
          border: '1px solid var(--border-color)', 
          borderRadius: '6px',
          minHeight: '400px',
          backgroundColor: 'var(--bg-sunken)'
        }}
        dangerouslySetInnerHTML={{ __html: renderContent }}
      />
    );
  };

  return (
    <div>
      {/* Tool栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          {toolbarButtons.map((button, index) => 
            button.divider ? (
              <Divider key={index} type="vertical" />
            ) : (
              <Tooltip key={index} title={button.tooltip}>
                <Button 
                  type="text" 
                  icon={button.icon} 
                  onClick={button.action}
                  size="small"
                />
              </Tooltip>
            )
          )}
        </Space>
      </Card>

      {/* Edit区域 */}
      <div style={{ display: 'flex', gap: 16 }}>
        {/* LeftEdit区 */}
        <div style={{ flex: 1 }}>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Input
              placeholder={t('pages.knowledge.documentEditor.titlePlaceholder')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ fontSize: 'var(--font-size-md)', fontWeight: 500 }}
            />
          </Card>

          <Card size="small" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Select
                placeholder={t('pages.knowledge.documentEditor.selectCategory')}
                value={category}
                onChange={setCategory}
                style={{ width: 150 }}
              >
                <Option value="tech">{t('pages.knowledge.technicalDocumentation')}</Option>
                <Option value="product">{t('pages.knowledge.productDocumentation')}</Option>
                <Option value="management">{t('pages.knowledge.managementDocumentation')}</Option>
              </Select>
              
              <Select
                mode="tags"
                placeholder={t('pages.knowledge.documentEditor.addTag')}
                value={tags}
                onChange={setTags}
                style={{ flex: 1 }}
              >
                <Option value="入门">{t('pages.knowledge.documentEditor.tagGettingStarted')}</Option>
                <Option value="指南">{t('pages.knowledge.documentEditor.tagGuide')}</Option>
                <Option value="API">{t('pages.knowledge.documentEditor.tagApi')}</Option>
                <Option value="Development">{t('pages.knowledge.documentEditor.tagDevelopment')}</Option>
              </Select>
            </div>
          </Card>

          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 'var(--font-size-base)', color: 'var(--text-secondary)' }}>
                {isPreview ? t('pages.knowledge.documentEditor.previewMode') : t('pages.knowledge.documentEditor.editMode')}
              </span>
              <Space>
                <Button 
                  type={isPreview ? 'default' : 'primary'}
                  icon={<EditOutlined />}
                  onClick={() => setIsPreview(false)}
                  size="small"
                >
                  {t('common.edit')}
                </Button>
                <Button 
                  type={isPreview ? 'primary' : 'default'}
                  icon={<EyeOutlined />}
                  onClick={() => setIsPreview(true)}
                  size="small"
                >
                  {t('pages.knowledge.documentEditor.preview')}
                </Button>
              </Space>
            </div>

            {isPreview ? (
              renderMarkdownPreview()
            ) : (
              <TextArea
                ref={textareaRef}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('pages.knowledge.documentEditor.contentPlaceholder')}
                autoSize={{ minRows: 20, maxRows: 30 }}
                style={{ fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace' }}
              />
            )}
          </Card>
        </div>

        {/* Right预览区（仅在Edit模式下Display） */}
        {!isPreview && (
          <div style={{ width: '40%' }}>
            <Card title={t('pages.knowledge.documentEditor.livePreview')} size="small">
              {renderMarkdownPreview()}
            </Card>
          </div>
        )}
      </div>

      {/* BottomOperation栏 */}
      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Space>
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>
            {t('pages.knowledge.documentEditor.saveDocument')}
          </Button>
        </Space>
      </div>

      {/* SaveConfirmModal */}
      <Modal
        title={t('pages.knowledge.documentEditor.saveDocument')}
        open={isModalVisible}
        onOk={handleSave}
        onCancel={() => setIsModalVisible(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label={t('pages.knowledge.documentEditor.titlePlaceholder')}
            rules={[{ required: true, message: t('pages.knowledge.documentEditor.titleRequired') }]}
          >
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DocumentEditor; 