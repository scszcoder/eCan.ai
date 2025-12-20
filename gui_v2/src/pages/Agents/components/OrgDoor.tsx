import React, { useState, useCallback, useEffect, useRef } from 'react';
import { TeamOutlined } from '@ant-design/icons';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';
import './OrgDoor.css';

interface OrgDoorProps {
  name: string;
  hasChildren?: boolean;
  isActive?: boolean;
  agentCount?: number; // Total agent count in this org and its children
}

// 全局Cache：System视频List（PageLifecycle内永久有效）
let systemVideosCache: string[] | null = null;

// Get随机System视频（带永久Cache）
const getRandomSystemVideo = async (): Promise<string | null> => {
  try {
    // CheckCache是否存在
    if (systemVideosCache && systemVideosCache.length > 0) {
      // 从Cache中随机Select
      const randomIndex = Math.floor(Math.random() * systemVideosCache.length);
      const videoPath = systemVideosCache[randomIndex];
      console.log('[OrgDoor] Using cached video:', videoPath);
      return videoPath;
    }
    
    // Cache不存在，通过 IPC GetSystem视频List
    console.log('[OrgDoor] Fetching system avatars from IPC...');
    const response: any = await IPCWCClient.getInstance().sendRequest('avatar.get_system_avatars', {
      username: 'system'
    });
    
    if (response?.status === 'success' && response.result && Array.isArray(response.result)) {
      // 提取All有视频的 avatar
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
        // 永久Cache（直到Page重新Load）
        systemVideosCache = videos;
        
        // 随机Select一个
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

const OrgDoor: React.FC<OrgDoorProps> = ({ name, isActive = false, agentCount = 0 }) => {
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [sceneType] = useState(() => Math.floor(Math.random() * 4)); // Random scene type
  const [videoLoaded, setVideoLoaded] = useState(false);
  const [isOverflow, setIsOverflow] = useState(false);
  const nameRef = useRef<HTMLDivElement>(null);
  
  // Determine if video should be shown: only when agentCount > 0
  const shouldShowVideo = agentCount > 0;

  // 检测文本是否溢出（Used forAddoverflow类名）
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

  // Load video after door opens (lazy loading optimization)
  // Only load video when agentCount > 0
  useEffect(() => {
    // Only load when door is open (hovered or clicked), video not loaded, and should show video
    if ((hovered || clicked) && !videoLoaded && shouldShowVideo) {
      const loadVideo = async () => {
        const video = await getRandomSystemVideo();
        if (video) {
          setVideoUrl(video);
          setVideoLoaded(true);
          console.log('[OrgDoor] Video loaded on demand (agentCount:', agentCount, '):', video);
        }
      };

      loadVideo();
    }
  }, [hovered, clicked, videoLoaded, shouldShowVideo, agentCount]);

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
    // Check鼠标是否还在门的区域内
    const doorElement = e.currentTarget.closest('.org-door');
    if (doorElement) {
      const rect = doorElement.getBoundingClientRect();
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      
      // If鼠标还在门的区域内，Restore开门Status
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

  // ParseName和计数
  const parseNameAndCount = useCallback((displayName: string) => {
    // 匹配形如 "Name (count)" 的格式
    const match = displayName.match(/^(.+?)\s*\((\d+)\)$/);
    if (match) {
      return {
        name: match[1].trim(),
        count: match[2],
        fullName: match[1].trim() // 完整Name（不含计数）
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
      style={{ position: 'relative', zIndex: 6, cursor: 'pointer' }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {/* 悬停光晕效果 */}
      {hovered && <div className="door-glow" />}
      
      {/* Status指示器 */}
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
                {/* 跑马灯Container */}
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
