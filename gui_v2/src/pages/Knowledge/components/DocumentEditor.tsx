import React, { useState, useRef, useEffect } from 'react';
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
      tooltip: '粗体 (Ctrl+B)',
      action: () => insertMarkdown('**{text}**', '粗体文本'),
    },
    {
      icon: <ItalicOutlined />,
      tooltip: '斜体 (Ctrl+I)',
      action: () => insertMarkdown('*{text}*', '斜体文本'),
    },
    {
      icon: <UnderlineOutlined />,
      tooltip: '下划线',
      action: () => insertMarkdown('<u>{text}</u>', '下划线文本'),
    },
    { divider: true },
    {
      icon: <UnorderedListOutlined />,
      tooltip: '无序List',
      action: () => insertMarkdown('- {text}', 'List项'),
    },
    {
      icon: <OrderedListOutlined />,
      tooltip: '有序List',
      action: () => insertMarkdown('1. {text}', 'List项'),
    },
    { divider: true },
    {
      icon: <LinkOutlined />,
      tooltip: 'Link',
      action: () => insertMarkdown('[{text}](url)', 'Link文本'),
    },
    {
      icon: <PictureOutlined />,
      tooltip: '图片',
      action: () => insertMarkdown('![{text}](url)', '图片Description'),
    },
    {
      icon: <CodeOutlined />,
      tooltip: 'Code块',
      action: () => insertMarkdown('```\n{text}\n```', 'CodeContent'),
    },
    {
      icon: <TableOutlined />,
      tooltip: 'Table',
      action: () => insertMarkdown('| 列1 | 列2 | 列3 |\n|-----|-----|-----|\n| Content1 | Content2 | Content3 |', ''),
    },
  ];

  // ProcessSave
  const handleSave = async () => {
    if (!title.trim()) {
      message.error('请InputDocumentation标题');
      return;
    }
    if (!content.trim()) {
      message.error('请InputDocumentationContent');
      return;
    }
    if (!category) {
      message.error('请SelectCategory');
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
      message.success('DocumentationSaveSuccess');
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
          insertMarkdown('**{text}**', '粗体文本');
          break;
        case 'i':
          e.preventDefault();
          insertMarkdown('*{text}*', '斜体文本');
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
          border: '1px solid #d9d9d9', 
          borderRadius: '6px',
          minHeight: '400px',
          backgroundColor: '#fafafa'
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
              placeholder="Documentation标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ fontSize: 16, fontWeight: 500 }}
            />
          </Card>

          <Card size="small" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Select
                placeholder="SelectCategory"
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
                placeholder="AddTag"
                value={tags}
                onChange={setTags}
                style={{ flex: 1 }}
              >
                <Option value="入门">入门</Option>
                <Option value="指南">指南</Option>
                <Option value="API">API</Option>
                <Option value="Development">Development</Option>
              </Select>
            </div>
          </Card>

          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 14, color: '#666' }}>
                {isPreview ? '预览模式' : 'Edit模式'}
              </span>
              <Space>
                <Button 
                  type={isPreview ? 'default' : 'primary'}
                  icon={<EditOutlined />}
                  onClick={() => setIsPreview(false)}
                  size="small"
                >
                  Edit
                </Button>
                <Button 
                  type={isPreview ? 'primary' : 'default'}
                  icon={<EyeOutlined />}
                  onClick={() => setIsPreview(true)}
                  size="small"
                >
                  预览
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
                placeholder="在这里InputDocumentationContent，SupportMarkdown语法..."
                autoSize={{ minRows: 20, maxRows: 30 }}
                style={{ fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace' }}
              />
            )}
          </Card>
        </div>

        {/* Right预览区（仅在Edit模式下Display） */}
        {!isPreview && (
          <div style={{ width: '40%' }}>
            <Card title="实时预览" size="small">
              {renderMarkdownPreview()}
            </Card>
          </div>
        )}
      </div>

      {/* BottomOperation栏 */}
      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Space>
          <Button onClick={onCancel}>Cancel</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>
            SaveDocumentation
          </Button>
        </Space>
      </div>

      {/* SaveConfirmModal */}
      <Modal
        title="SaveDocumentation"
        open={isModalVisible}
        onOk={handleSave}
        onCancel={() => setIsModalVisible(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="Documentation标题"
            rules={[{ required: true, message: '请InputDocumentation标题' }]}
          >
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DocumentEditor; 