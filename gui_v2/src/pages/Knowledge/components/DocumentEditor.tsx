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
    
    // 设置光标位置
    setTimeout(() => {
      if (textareaRef.current) {
        const newCursorPos = start + insertText.length;
        textareaRef.current.setSelectionRange(newCursorPos, newCursorPos);
        textareaRef.current.focus();
      }
    }, 0);
  };

  // 工具栏按钮配置
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
      tooltip: '无序列表',
      action: () => insertMarkdown('- {text}', '列表项'),
    },
    {
      icon: <OrderedListOutlined />,
      tooltip: '有序列表',
      action: () => insertMarkdown('1. {text}', '列表项'),
    },
    { divider: true },
    {
      icon: <LinkOutlined />,
      tooltip: '链接',
      action: () => insertMarkdown('[{text}](url)', '链接文本'),
    },
    {
      icon: <PictureOutlined />,
      tooltip: '图片',
      action: () => insertMarkdown('![{text}](url)', '图片描述'),
    },
    {
      icon: <CodeOutlined />,
      tooltip: '代码块',
      action: () => insertMarkdown('```\n{text}\n```', '代码内容'),
    },
    {
      icon: <TableOutlined />,
      tooltip: '表格',
      action: () => insertMarkdown('| 列1 | 列2 | 列3 |\n|-----|-----|-----|\n| 内容1 | 内容2 | 内容3 |', ''),
    },
  ];

  // 处理保存
  const handleSave = async () => {
    if (!title.trim()) {
      message.error('请输入文档标题');
      return;
    }
    if (!content.trim()) {
      message.error('请输入文档内容');
      return;
    }
    if (!category) {
      message.error('请选择分类');
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
      message.success('文档保存成功');
    } catch (error) {
      console.error('保存失败:', error);
    }
  };

  // 处理快捷键
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

  // 渲染Markdown预览
  const renderMarkdownPreview = () => {
    // 简单的Markdown渲染（实际项目中可以使用marked.js等库）
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
      {/* 工具栏 */}
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

      {/* 编辑区域 */}
      <div style={{ display: 'flex', gap: 16 }}>
        {/* 左侧编辑区 */}
        <div style={{ flex: 1 }}>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Input
              placeholder="文档标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ fontSize: 16, fontWeight: 500 }}
            />
          </Card>

          <Card size="small" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Select
                placeholder="选择分类"
                value={category}
                onChange={setCategory}
                style={{ width: 150 }}
              >
                <Option value="tech">技术文档</Option>
                <Option value="product">产品文档</Option>
                <Option value="management">管理文档</Option>
              </Select>
              
              <Select
                mode="tags"
                placeholder="添加标签"
                value={tags}
                onChange={setTags}
                style={{ flex: 1 }}
              >
                <Option value="入门">入门</Option>
                <Option value="指南">指南</Option>
                <Option value="API">API</Option>
                <Option value="开发">开发</Option>
              </Select>
            </div>
          </Card>

          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 14, color: '#666' }}>
                {isPreview ? '预览模式' : '编辑模式'}
              </span>
              <Space>
                <Button 
                  type={isPreview ? 'default' : 'primary'}
                  icon={<EditOutlined />}
                  onClick={() => setIsPreview(false)}
                  size="small"
                >
                  编辑
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
                placeholder="在这里输入文档内容，支持Markdown语法..."
                autoSize={{ minRows: 20, maxRows: 30 }}
                style={{ fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace' }}
              />
            )}
          </Card>
        </div>

        {/* 右侧预览区（仅在编辑模式下显示） */}
        {!isPreview && (
          <div style={{ width: '40%' }}>
            <Card title="实时预览" size="small">
              {renderMarkdownPreview()}
            </Card>
          </div>
        )}
      </div>

      {/* 底部操作栏 */}
      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Space>
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>
            保存文档
          </Button>
        </Space>
      </div>

      {/* 保存确认弹窗 */}
      <Modal
        title="保存文档"
        open={isModalVisible}
        onOk={handleSave}
        onCancel={() => setIsModalVisible(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="文档标题"
            rules={[{ required: true, message: '请输入文档标题' }]}
          >
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DocumentEditor; 