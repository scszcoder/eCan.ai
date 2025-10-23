import React, { useState, useCallback, useEffect, useRef } from 'react';
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
  const [isOverflow, setIsOverflow] = useState(false);
  const nameRef = useRef<HTMLDivElement>(null);

  // 检测文本是否溢出（用于添加overflow类名）
  useEffect(() => {
    const checkOverflow = () => {
      if (nameRef.current) {
        const element = nameRef.current;
        const isTextOverflow = element.scrollHeight > element.clientHeight;
        setIsOverflow(isTextOverflow);
      }
    };

    const timer = setTimeout(checkOverflow, 100);
    window.addEventListener('resize', checkOverflow);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', checkOverflow);
    };
  }, [name]);

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

  // 铭牌hover时阻止开门
  const handleNameplateMouseEnter = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setHovered(false);
  }, []);

  const handleNameplateMouseLeave = useCallback((e: React.MouseEvent) => {
    // 检查鼠标是否还在门的区域内
    const doorElement = e.currentTarget.closest('.org-door');
    if (doorElement) {
      const rect = doorElement.getBoundingClientRect();
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      
      // 如果鼠标还在门的区域内，恢复开门状态
      if (mouseX >= rect.left && mouseX <= rect.right && 
          mouseY >= rect.top && mouseY <= rect.bottom) {
        setHovered(true);
      }
    }
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
        count: match[2],
        fullName: match[1].trim() // 完整名称（不含计数）
      };
    }
    return {
      name: displayName,
      count: null,
      fullName: displayName
    };
  }, []);

  const { name: doorName, count, fullName } = parseNameAndCount(name);

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
            {/* 门上的铭牌 */}
            <div 
              className="door-nameplate"
              onMouseEnter={handleNameplateMouseEnter}
              onMouseLeave={handleNameplateMouseLeave}
            >
              <div 
                ref={nameRef}
                className={`nameplate-name ${isOverflow ? 'overflow' : ''}`}
              >
                {doorName}
                {/* 跑马灯容器 */}
                {isOverflow && (
                  <div className="nameplate-name-marquee">
                    <div className="nameplate-name-marquee-text" data-text={fullName}>
                      {fullName}
                    </div>
                  </div>
                )}
              </div>
              {count && (
                <div className="nameplate-count">
                  <TeamOutlined style={{ fontSize: 14, marginRight: 4 }} />
                  <span>{count}</span>
                </div>
              )}
            </div>
            
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
    </div>
  );
};

export default React.memo(OrgDoor);
