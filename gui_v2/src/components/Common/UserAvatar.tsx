import React, { useMemo } from 'react';
import { Avatar } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const StyledAvatar = styled(Avatar)`
    border: 2px solid var(--border-color-hover);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
    flex-shrink: 0;
    // The gradient fills below are fixed dark colours in BOTH themes, so the
    // initials must stay white; inheriting --text-primary turns them
    // near-black in light theme (3.26:1 on #047857).
    color: var(--text-on-primary) !important;
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
        // Every stop must clear 4.5:1 against the white initials text.
        'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)', // Blue-Purple
        'linear-gradient(135deg, #047857 0%, #2563eb 100%)', // Green-Blue
        'linear-gradient(135deg, #b45309 0%, #b91c1c 100%)', // Orange-Red
        'linear-gradient(135deg, #be185d 0%, #7c3aed 100%)', // Pink-Purple
        'linear-gradient(135deg, #4f46e5 0%, #be185d 100%)', // Indigo-Pink
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
