import React, { useState } from 'react';
import { Avatar, Badge } from 'antd';
import { UserOutlined, PlayCircleOutlined } from '@ant-design/icons';
import './AvatarDisplay.css';

interface AvatarDisplayProps {
  imageUrl?: string;
  videoUrl?: string;
  size?: 'small' | 'default' | 'large' | number;
  showVideo?: boolean;
  shape?: 'circle' | 'square';
  alt?: string;
  className?: string;
  onClick?: () => void;
}

export const AvatarDisplay: React.FC<AvatarDisplayProps> = ({
  imageUrl,
  videoUrl,
  size = 'default',
  showVideo = true,
  shape = 'circle',
  alt = 'avatar',
  className = '',
  onClick
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [videoError, setVideoError] = useState(false);

  // Determine size in pixels
  const getSizeInPixels = (): number => {
    if (typeof size === 'number') return size;
    switch (size) {
      case 'small': return 48;
      case 'large': return 128;
      default: return 64;
    }
  };

  const sizeInPixels = getSizeInPixels();
  const showVideoPreview = showVideo && videoUrl && isHovered && !videoError;

  const containerStyle: React.CSSProperties = {
    width: sizeInPixels,
    height: sizeInPixels,
    borderRadius: shape === 'circle' ? '50%' : '8px',
    overflow: 'hidden',
    position: 'relative',
    cursor: onClick ? 'pointer' : 'default'
  };

  const handleVideoError = () => {
    console.warn('[AvatarDisplay] Video failed to load:', videoUrl);
    setVideoError(true);
  };

  return (
    <div
      className={`avatar-display ${className}`}
      style={containerStyle}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      {showVideoPreview ? (
        <video
          src={videoUrl}
          autoPlay
          loop
          muted
          playsInline
          onError={handleVideoError}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover'
          }}
        />
      ) : imageUrl ? (
        <img
          src={imageUrl}
          alt={alt}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover'
          }}
          onError={(e) => {
            // Fallback to default avatar icon on error
            e.currentTarget.style.display = 'none';
          }}
        />
      ) : (
        <Avatar
          size={sizeInPixels}
          shape={shape}
          icon={<UserOutlined />}
        />
      )}
      
      {videoUrl && !videoError && (
        <Badge
          count={<PlayCircleOutlined style={{ fontSize: 12, color: '#1890ff' }} />}
          style={{
            position: 'absolute',
            bottom: 0,
            right: 0,
            background: 'rgba(255, 255, 255, 0.9)',
            borderRadius: '50%',
            padding: 2
          }}
        />
      )}
    </div>
  );
};

export default AvatarDisplay;
