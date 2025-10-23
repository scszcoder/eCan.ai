import React, { useState, useCallback, useEffect } from 'react';
import { TeamOutlined } from '@ant-design/icons';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';
import './OrgDoor.css';

interface OrgDoorProps {
  name: string;
  hasChildren?: boolean;
  isActive?: boolean;
}

// 全局缓存：系统视频列表（页面生命周期内永久有效）
let systemVideosCache: string[] | null = null;

// 获取随机系统视频（带永久缓存）
const getRandomSystemVideo = async (): Promise<string | null> => {
  try {
    // 检查缓存是否存在
    if (systemVideosCache && systemVideosCache.length > 0) {
      // 从缓存中随机选择
      const randomIndex = Math.floor(Math.random() * systemVideosCache.length);
      const videoPath = systemVideosCache[randomIndex];
      console.log('[OrgDoor] Using cached video:', videoPath);
      return videoPath;
    }
    
    // 缓存不存在，通过 IPC 获取系统视频列表
    console.log('[OrgDoor] Fetching system avatars from IPC...');
    const response: any = await IPCWCClient.getInstance().sendRequest('avatar.get_system_avatars', {
      username: 'system'
    });
    
    if (response?.status === 'success' && response.result && Array.isArray(response.result)) {
      // 提取所有有视频的 avatar
      const videos: string[] = [];
      response.result.forEach((avatar: any) => {
        // 优先使用 webm 格式
        if (avatar.videoWebmPath) {
          videos.push(avatar.videoWebmPath);
        } else if (avatar.videoUrl) {
          videos.push(avatar.videoUrl);
        }
      });
      
      if (videos.length > 0) {
        // 永久缓存（直到页面重新加载）
        systemVideosCache = videos;
        
        // 随机选择一个
        const randomIndex = Math.floor(Math.random() * videos.length);
        const selectedVideo = videos[randomIndex];
        console.log('[OrgDoor] Cached', videos.length, 'videos, selected:', selectedVideo);
        return selectedVideo;
      } else {
        console.warn('[OrgDoor] No videos found in system avatars');
        return null;
      }
    } else {
      console.warn('[OrgDoor] Failed to get system avatars:', response?.error);
      return null;
    }
  } catch (error) {
    console.error('[OrgDoor] Error fetching system videos:', error);
    return null;
  }
};

const OrgDoor: React.FC<OrgDoorProps> = ({ name, isActive = false }) => {
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [sceneType] = useState(() => Math.floor(Math.random() * 4)); // 随机选择场景类型
  const [videoLoaded, setVideoLoaded] = useState(false);

  // 开门后才加载视频（懒加载优化）
  useEffect(() => {
    // 只在门打开（hovered 或 clicked）且视频未加载时才请求
    if ((hovered || clicked) && !videoLoaded) {
      const loadVideo = async () => {
        const video = await getRandomSystemVideo();
        if (video) {
          setVideoUrl(video);
          setVideoLoaded(true);
          console.log('[OrgDoor] Video loaded on demand:', video);
        }
      };

      loadVideo();
    }
  }, [hovered, clicked, videoLoaded]);

  const handleMouseEnter = useCallback(() => {
    setHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
  }, []);

  const handleClick = useCallback(() => {
    setClicked(true);
    setTimeout(() => setClicked(false), 300);
  }, []);

  // 解析名称和计数
  const parseNameAndCount = useCallback((displayName: string) => {
    // 匹配形如 "Name (count)" 的格式
    const match = displayName.match(/^(.+?)\s*\((\d+)\)$/);
    if (match) {
      return {
        name: match[1].trim(),
        count: match[2]
      };
    }
    return {
      name: displayName,
      count: null
    };
  }, []);

  const { name: doorName, count } = parseNameAndCount(name);

  return (
    <div
      className={`org-door custom-door${hovered ? ' opening' : ''}${clicked ? ' clicked' : ''}${isActive ? ' active' : ''}`}
      style={{ position: 'static', zIndex: 2 }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {/* 悬停光晕效果 */}
      {hovered && <div className="door-glow" />}
      
      {/* 状态指示器 */}
      {isActive && (
        <div className="door-status-indicator">
          <div className="status-dot" />
        </div>
      )}
      
      {/* CSS 门设计 */}
      <div className="css-door-container">
        {/* 门框 */}
        <div className="door-frame">
          {/* 门后场景 - 员工工作 */}
          <div className={`door-background-scene ${videoUrl ? 'video-scene' : `scene-${sceneType}`} ${hovered ? 'visible' : ''}`}>
            {videoUrl ? (
              <video
                className="scene-video"
                src={videoUrl}
                autoPlay
                loop
                muted
                playsInline
              />
            ) : (
              <div className="scene-content">
                {/* 场景会通过 CSS 绘制 */}
              </div>
            )}
          </div>
          
          {/* 门板 */}
          <div className={`door-panel ${hovered ? 'open' : ''}`}>
            {/* 门板装饰线 */}
            <div className="door-decoration">
              <div className="door-line door-line-1" />
              <div className="door-line door-line-2" />
            </div>
            
            {/* 门把手 */}
            <div className="door-handle" />
          </div>
        </div>
      </div>
      
      <div className="org-door-label">
        <div className="org-door-label-name">{doorName}</div>
        {count && (
          <div className="org-door-label-count">
            <TeamOutlined style={{ fontSize: 12, marginRight: 4 }} />
            {count}
          </div>
        )}
      </div>
    </div>
  );
};

export default React.memo(OrgDoor);
