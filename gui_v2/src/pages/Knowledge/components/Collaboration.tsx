import React, { useState, useRef, useEffect } from 'react';
import { 
  Card, 
  Input, 
  Button, 
  Avatar, 
  Space, 
  Typography, 
  List, 
  Tag,
  Dropdown,
  Menu,
  Modal,
  Form,
  message,
  Tooltip
} from 'antd';
import { 
  SendOutlined,
  UserOutlined,
  LikeOutlined,
  DislikeOutlined,
  MessageOutlined,
  MoreOutlined,
  UserAddOutlined,
  EditOutlined,
  DeleteOutlined
} from '@ant-design/icons';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface Comment {
  id: string;
  content: string;
  author: {
    id: string;
    name: string;
    avatar?: string;
  };
  createdAt: string;
  likes: number;
  dislikes: number;
  replies: Comment[];
  mentions: string[];
  isEdited: boolean;
}

interface CollaborationProps {
  documentId: number;
  onComment?: (comment: Omit<Comment, 'id' | 'createdAt' | 'likes' | 'dislikes' | 'replies' | 'isEdited'>) => void;
}

const Collaboration: React.FC<CollaborationProps> = ({
  documentId,
  onComment
}) => {
  const [comments, setComments] = useState<Comment[]>([
    {
      id: '1',
      content: '这个文档写得很好，但是建议在API部分添加更多的示例代码。@张三 你觉得呢？',
      author: {
        id: 'user1',
        name: '李四',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=1',
      },
      createdAt: '2024-01-15 14:30',
      likes: 3,
      dislikes: 0,
      replies: [
        {
          id: '1-1',
          content: '同意，我来补充一些示例代码。',
          author: {
            id: 'user2',
            name: '张三',
            avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=2',
          },
          createdAt: '2024-01-15 15:00',
          likes: 1,
          dislikes: 0,
          replies: [],
          mentions: [],
          isEdited: false,
        },
      ],
      mentions: ['张三'],
      isEdited: false,
    },
    {
      id: '2',
      content: '文档结构很清晰，但是权限管理部分可以更详细一些。',
      author: {
        id: 'user3',
        name: '王五',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=3',
      },
      createdAt: '2024-01-15 16:15',
      likes: 2,
      dislikes: 0,
      replies: [],
      mentions: [],
      isEdited: false,
    },
  ]);

  const [newComment, setNewComment] = useState('');
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [editingComment, setEditingComment] = useState<Comment | null>(null);
  const [showMentions, setShowMentions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 模拟用户列表
  const users = [
    { id: 'user1', name: '李四' },
    { id: 'user2', name: '张三' },
    { id: 'user3', name: '王五' },
    { id: 'user4', name: '赵六' },
    { id: 'user5', name: '钱七' },
  ];

  // 处理发送评论
  const handleSendComment = () => {
    if (!newComment.trim()) {
      message.warning('请输入评论内容');
      return;
    }

    const mentions = extractMentions(newComment);
    const commentData = {
      content: newComment.trim(),
      author: {
        id: 'currentUser',
        name: '当前用户',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=current',
      },
      mentions,
    };

    const newCommentObj: Comment = {
      id: Date.now().toString(),
      ...commentData,
      createdAt: new Date().toLocaleString(),
      likes: 0,
      dislikes: 0,
      replies: [],
      isEdited: false,
    };

    if (replyTo) {
      // 添加回复
      setComments(prev => prev.map(comment => 
        comment.id === replyTo.id 
          ? { ...comment, replies: [...comment.replies, newCommentObj] }
          : comment
      ));
      setReplyTo(null);
    } else {
      // 添加新评论
      setComments(prev => [newCommentObj, ...prev]);
    }

    setNewComment('');
    onComment?.(commentData);
    message.success('评论发送成功');
  };

  // 处理回复
  const handleReply = (comment: Comment) => {
    setReplyTo(comment);
    setNewComment(`@${comment.author.name} `);
    textareaRef.current?.focus();
  };

  // 处理编辑评论
  const handleEdit = (comment: Comment) => {
    setEditingComment(comment);
    setNewComment(comment.content);
  };

  // 处理保存编辑
  const handleSaveEdit = () => {
    if (!editingComment) return;

    setComments(prev => prev.map(comment => 
      comment.id === editingComment.id 
        ? { ...comment, content: newComment, isEdited: true }
        : comment
    ));

    setEditingComment(null);
    setNewComment('');
    message.success('评论更新成功');
  };

  // 处理删除评论
  const handleDelete = (comment: Comment) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这条评论吗？',
      onOk: () => {
        setComments(prev => prev.filter(c => c.id !== comment.id));
        message.success('评论删除成功');
      },
    });
  };

  // 处理点赞/踩
  const handleVote = (comment: Comment, type: 'like' | 'dislike') => {
    setComments(prev => prev.map(c => 
      c.id === comment.id 
        ? { 
            ...c, 
            likes: type === 'like' ? c.likes + 1 : c.likes,
            dislikes: type === 'dislike' ? c.dislikes + 1 : c.dislikes,
          }
        : c
    ));
  };

  // 提取@提及
  const extractMentions = (text: string): string[] => {
    const mentionRegex = /@(\w+)/g;
    const mentions: string[] = [];
    let match;
    while ((match = mentionRegex.exec(text)) !== null) {
      mentions.push(match[1]);
    }
    return mentions;
  };

  // 渲染评论内容
  const renderCommentContent = (content: string, mentions: string[]) => {
    let renderedContent = content;
    mentions.forEach(mention => {
      const regex = new RegExp(`@${mention}`, 'g');
      renderedContent = renderedContent.replace(regex, `<span style="color: #1890ff; font-weight: 500;">@${mention}</span>`);
    });
    return <div dangerouslySetInnerHTML={{ __html: renderedContent }} />;
  };

  // 渲染评论操作菜单
  const renderCommentMenu = (comment: Comment) => (
    <Menu>
      <Menu.Item key="reply" icon={<MessageOutlined />} onClick={() => handleReply(comment)}>
        回复
      </Menu.Item>
      <Menu.Item key="edit" icon={<EditOutlined />} onClick={() => handleEdit(comment)}>
        编辑
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="delete" icon={<DeleteOutlined />} danger onClick={() => handleDelete(comment)}>
        删除
      </Menu.Item>
    </Menu>
  );

  // 渲染单个评论
  const renderComment = (comment: Comment, isReply = false) => (
    <div key={comment.id} style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', gap: 12 }}>
        <Avatar 
          src={comment.author.avatar} 
          icon={<UserOutlined />}
          size={isReply ? 32 : 40}
        />
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
            <div>
              <Text strong>{comment.author.name}</Text>
              <Text type="secondary" style={{ marginLeft: 8 }}>
                {comment.createdAt}
                {comment.isEdited && <Text type="secondary"> (已编辑)</Text>}
              </Text>
            </div>
            <Dropdown overlay={renderCommentMenu(comment)} trigger={['click']}>
              <Button type="text" size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </div>

          <div style={{ marginBottom: 8 }}>
            {renderCommentContent(comment.content, comment.mentions)}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Space>
              <Button 
                type="text" 
                size="small" 
                icon={<LikeOutlined />}
                onClick={() => handleVote(comment, 'like')}
              >
                {comment.likes}
              </Button>
              <Button 
                type="text" 
                size="small" 
                icon={<DislikeOutlined />}
                onClick={() => handleVote(comment, 'dislike')}
              >
                {comment.dislikes}
              </Button>
                             <Button 
                 type="text" 
                 size="small" 
                 icon={<MessageOutlined />}
                 onClick={() => handleReply(comment)}
               >
                 回复
               </Button>
            </Space>
          </div>

          {/* 回复列表 */}
          {comment.replies.length > 0 && (
            <div style={{ marginTop: 12, paddingLeft: 16, borderLeft: '2px solid #f0f0f0' }}>
              {comment.replies.map(reply => renderComment(reply, true))}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div>
      {/* 评论输入区 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 12 }}>
          <Text strong>添加评论</Text>
          {replyTo && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">
                回复 @{replyTo.author.name}：
                <Button 
                  type="link" 
                  size="small" 
                  onClick={() => setReplyTo(null)}
                >
                  取消回复
                </Button>
              </Text>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <TextArea
            ref={textareaRef}
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder={editingComment ? '编辑评论...' : '输入评论内容，使用 @用户名 来提及他人...'}
            autoSize={{ minRows: 2, maxRows: 4 }}
            style={{ flex: 1 }}
            onKeyPress={(e) => {
              if (e.key === '@') {
                setShowMentions(true);
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={editingComment ? handleSaveEdit : handleSendComment}
            disabled={!newComment.trim()}
          >
            {editingComment ? '保存' : '发送'}
          </Button>
        </div>

        {/* @提及下拉菜单 */}
        {showMentions && (
          <div style={{ 
            position: 'absolute', 
            top: '100%', 
            left: 0, 
            right: 0,
            backgroundColor: '#fff',
            border: '1px solid #d9d9d9',
            borderRadius: 6,
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            zIndex: 1000,
            maxHeight: 200,
            overflow: 'auto'
          }}>
            {users.map(user => (
              <div
                key={user.id}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #f0f0f0',
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f5f5f5'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#fff'}
                onClick={() => {
                  const beforeAt = newComment.substring(0, newComment.lastIndexOf('@'));
                  setNewComment(beforeAt + `@${user.name} `);
                  setShowMentions(false);
                }}
              >
                <Text>@{user.name}</Text>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 评论列表 */}
      <div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>评论 ({comments.length})</Text>
        </div>
        {comments.map(comment => renderComment(comment))}
      </div>
    </div>
  );
};

export default Collaboration; 