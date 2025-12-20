import React, { useMemo } from 'react';
import { Avatar } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const StyledAvatar = styled(Avatar)`
    border: 2px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
    flex-shrink: 0;
`;

interface UserAvatarProps {
    name?: string;
    picture?: string;
    size?: number | 'large' | 'small' | 'default';
    className?: string;
    style?: React.CSSProperties;
}

// 辅助函数：获取头像显示文本（首字母）
const getAvatarText = (name: string) => {
    if (!name) return '';
    // 如果是中文，取最后一个字
    if (/[\u4e00-\u9fa5]/.test(name)) {
        return name.slice(-1);
    }
    // 如果是英文，取首字母，如果有空格取前两个单词的首字母
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
};

// 辅助函数：根据名称获取头像背景色
const getAvatarColor = (name: string) => {
    const colors = [
        'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)', // Blue-Purple
        'linear-gradient(135deg, #10b981 0%, #3b82f6 100%)', // Green-Blue
        'linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)', // Orange-Red
        'linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)', // Pink-Purple
        'linear-gradient(135deg, #6366f1 0%, #ec4899 100%)', // Indigo-Pink
    ];
    if (!name) return colors[0];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
};

export const UserAvatar: React.FC<UserAvatarProps> = ({ name = '', picture, size = 32, className, style }) => {
    const avatarText = useMemo(() => getAvatarText(name), [name]);
    const avatarBackground = useMemo(() => getAvatarColor(name), [name]);

    if (picture) {
        return (
            <StyledAvatar 
                src={picture} 
                size={size} 
                className={className} 
                style={style}
            />
        );
    }

    if (avatarText) {
        return (
            <StyledAvatar 
                size={size} 
                className={className} 
                style={{ ...style, background: avatarBackground }}
            >
                {avatarText}
            </StyledAvatar>
        );
    }

    return (
        <StyledAvatar 
            icon={<UserOutlined />} 
            size={size} 
            className={className} 
            style={{ ...style, background: avatarBackground }} 
        />
    );
};
