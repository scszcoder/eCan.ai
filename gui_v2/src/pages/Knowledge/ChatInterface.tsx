import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Avatar, Space, Card, Typography, Divider } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, LikeOutlined, DislikeOutlined, MessageOutlined, ShareAltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  relatedDocs?: Array<{
    title: string;
    url: string;
  }>;
}

const ChatInterface: React.FC = () => {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'assistant',
      content: 'Hello! I am your intelligent assistant, providing help based on the enterprise knowledge base. You can ask me any questions about products, technology, or processes.',
      timestamp: new Date(),
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动Scroll到Bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // SendMessage
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    // Simulate AI response
    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: `Based on the knowledge base, the answer to "${inputValue}":\n\nThis is an example response. In production, relevant content should be retrieved from the knowledge base.`,
        timestamp: new Date(),
        relatedDocs: [
          { title: 'Related Document 1', url: '#' },
          { title: 'Related Document 2', url: '#' },
        ],
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1000);
  };

  // Process回车Send
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // RenderMessage气泡
  const renderMessage = (message: Message) => {
    const isUser = message.type === 'user';
    
    return (
      <div
        key={message.id}
        style={{
          display: 'flex',
          justifyContent: isUser ? 'flex-end' : 'flex-start',
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', maxWidth: '70%' }}>
          {!isUser && (
            <Avatar 
              icon={<RobotOutlined />} 
              style={{ backgroundColor: '#1890ff', marginRight: 8 }}
            />
          )}
          
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <Card
              size="small"
              style={{
                backgroundColor: isUser ? '#1890ff' : '#f5f5f5',
                color: isUser ? '#fff' : '#000',
                borderRadius: 12,
                border: 'none',
              }}
            >
              <Paragraph 
                style={{ 
                  margin: 0, 
                  color: isUser ? '#fff' : '#000',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {message.content}
              </Paragraph>
            </Card>

            {/* Related Documents */}
            {message.relatedDocs && message.relatedDocs.length > 0 && (
              <Card size="small" style={{ marginTop: 8, backgroundColor: '#f8f9fa' }}>
                <Text strong style={{ fontSize: 12 }}>📚 Related Documents:</Text>
                <div style={{ marginTop: 4 }}>
                  {message.relatedDocs.map((doc, index) => (
                    <div key={doc.title + '-' + index}>
                      <Text 
                        style={{ fontSize: 12, cursor: 'pointer', color: '#1890ff' }}
                        onClick={() => console.log('Open document:', doc.title)}
                      >
                        • {doc.title}
                      </Text>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* OperationButton */}
            {!isUser && (
              <Space style={{ marginTop: 8 }}>
                <Button 
                  type="text" 
                  size="small" 
                  icon={<LikeOutlined />}
                  onClick={() => console.log('有Help')}
                >
                  有Help
                </Button>
                <Button 
                  type="text" 
                  size="small" 
                  icon={<DislikeOutlined />}
                  onClick={() => console.log('没Help')}
                >
                  没Help
                </Button>
                <Button 
                  type="text" 
                  size="small" 
                  icon={<MessageOutlined />}
                  onClick={() => console.log('反馈')}
                >
                  反馈
                </Button>
                <Button 
                  type="text" 
                  size="small" 
                  icon={<ShareAltOutlined />}
                  onClick={() => console.log('分享')}
                >
                  分享
                </Button>
              </Space>
            )}
          </div>

          {isUser && (
            <Avatar 
              icon={<UserOutlined />} 
              style={{ backgroundColor: '#52c41a', marginLeft: 8 }}
            />
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={{ height: 'calc(100vh - 200px)', display: 'flex', flexDirection: 'column' }}>
      {/* 聊天区域 */}
      <div 
        style={{ 
          flex: 1, 
          overflowY: 'auto', 
          padding: '16px 0',
          borderBottom: '1px solid #f0f0f0'
        }}
      >
        {messages.map(renderMessage)}
        
        {/* LoadStatus */}
        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
            <Avatar 
              icon={<RobotOutlined />} 
              style={{ backgroundColor: '#1890ff', marginRight: 8 }}
            />
            <Card size="small" style={{ backgroundColor: '#f5f5f5', borderRadius: 12 }}>
              <Text>正在思考中...</Text>
            </Card>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input区域 */}
      <div style={{ padding: '16px 0' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Input你的问题..."
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ flex: 1 }}
            disabled={isLoading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            style={{ height: 'auto' }}
          >
            Send
          </Button>
        </div>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            按 Enter Send，Shift + Enter 换行
          </Text>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface; 