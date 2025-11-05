import React, { useState, useEffect, useRef } from 'react';
import { Avatar, Badge } from 'antd';
import { UserOutlined, PlayCircleOutlined } from '@ant-design/icons';
import './AvatarDisplay.css';
import { avatarSceneOrchestrator } from '@/services/avatarSceneOrchestrator';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { logger } from '@/utils/logger';

interface AvatarDisplayProps {
  imageUrl?: string;
  videoUrl?: string;
  size?: 'small' | 'default' | 'large' | number;
  showVideo?: boolean;
  shape?: 'circle' | 'square';
  alt?: string;
  className?: string;
  onClick?: () => void;
  agentId?: string; // If provided, dynamic scenes will render via AgentMedia
}

export function AgentMedia({ agentId }: { agentId: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const currentScene = useAvatarSceneStore(s => s.getCurrentScene(agentId));
  const isPlaying = Boolean(currentScene && (currentScene as any).state === 'playing');
  const [hidden, setHidden] = React.useState(false);
  const watchdogRef = React.useRef<number | null>(null);
  const forceEndOnce = React.useRef(false);
  const playKey = currentScene?.startTime || 0;

  // Bind media events and natural end -> orchestrator
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onEnded = () => {
      logger.info('[AgentMedia] ended', { agentId });
      try { console.log('[AgentMedia] ended', { agentId }); } catch {}
      // Proactively clear media to avoid lingering last frame
      try {
        video.pause();
        video.removeAttribute('src');
        video.load();
        // Hide overlay immediately so base avatar shows
        setHidden(true);
        // Also hide the element visually in case the browser paints the last frame
        (video as any).style.visibility = 'hidden';
        (video as any).style.display = 'none';
      } catch {}
      // Clear watchdog
      if (watchdogRef.current) { clearTimeout(watchdogRef.current); watchdogRef.current = null; }
      forceEndOnce.current = true;
      // Immediately notify and return to default to guarantee revert
      avatarSceneOrchestrator.onMediaEnded(agentId);
      try { avatarSceneOrchestrator.returnToDefault(agentId); } catch {}
    };
    const onLoadedMeta = () => {
      try {
        const duration = video.duration;
        logger.info('[AgentMedia] loadedmetadata', { agentId, duration });
        try { console.log('[AgentMedia] loadedmetadata', { agentId, duration }); } catch {}
        if (isFinite(duration) && duration > 0) {
          // Add small buffer and set watchdog
          if (watchdogRef.current) { clearTimeout(watchdogRef.current); watchdogRef.current = null; }
          watchdogRef.current = window.setTimeout(() => {
            if (!forceEndOnce.current) {
              logger.warn('[AgentMedia] watchdog forcing end', { agentId, duration });
              try { console.warn('[AgentMedia] watchdog forcing end', { agentId, duration }); } catch {}
              onEnded();
            }
          }, Math.ceil((duration + 0.25) * 1000));
        }
      } catch {}
    };
    const onTimeUpdate = () => {
      try {
        if (!video.duration) return;
        if (video.currentTime >= video.duration - 0.05 && !forceEndOnce.current) {
          logger.info('[AgentMedia] timeupdate near end -> forcing end', { agentId });
          onEnded();
        }
      } catch {}
    };
    const onError = () => {
      // HTMLMediaError message may be null; log states as well
      const err: any = (video as any).error;
      logger.error('[AgentMedia] video error', {
        agentId,
        src: video.src,
        error: err?.message || String(err || 'unknown'),
        networkState: video.networkState,
        readyState: video.readyState
      });
    };
    const onLoaded = () => { logger.info('[AgentMedia] loadeddata', { agentId, src: video.src }); try { console.log('[AgentMedia] loadeddata', { agentId, src: video.src }); } catch {} };
    const onCanPlay = () => { logger.info('[AgentMedia] canplay', { agentId }); try { console.log('[AgentMedia] canplay', { agentId }); } catch {} };
    const onPlay = () => { logger.info('[AgentMedia] play', { agentId }); try { console.log('[AgentMedia] play', { agentId }); } catch {} };
    const onPause = () => { logger.info('[AgentMedia] pause', { agentId }); try { console.log('[AgentMedia] pause', { agentId }); } catch {} };

    video.addEventListener('ended', onEnded);
    video.addEventListener('loadedmetadata', onLoadedMeta);
    video.addEventListener('error', onError);
    video.addEventListener('loadeddata', onLoaded);
    video.addEventListener('canplay', onCanPlay);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.addEventListener('timeupdate', onTimeUpdate);

    return () => {
      video.removeEventListener('ended', onEnded);
      video.removeEventListener('loadedmetadata', onLoadedMeta);
      video.removeEventListener('error', onError);
      video.removeEventListener('loadeddata', onLoaded);
      video.removeEventListener('canplay', onCanPlay);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
      video.removeEventListener('timeupdate', onTimeUpdate);
      if (watchdogRef.current) { clearTimeout(watchdogRef.current); watchdogRef.current = null; }
      forceEndOnce.current = false;
    };
  }, [agentId]);

  // Start/restart playback when scene or repeat advances
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !currentScene) return;

    const src = currentScene.clip.clip;
    logger.info('[AgentMedia] set src', { agentId, src, label: currentScene.clip.label });
    try { console.log('[AgentMedia] set src', { agentId, src, label: currentScene.clip.label }); } catch {}
    video.src = src;
    video.currentTime = 0;
    // Reveal overlay when a new play starts
    setHidden(false);
    forceEndOnce.current = false;
    if (watchdogRef.current) { clearTimeout(watchdogRef.current); watchdogRef.current = null; }
    try { (video as any).style.visibility = 'visible'; (video as any).style.display = 'block'; } catch {}
    video.play().catch((e) => {
      logger.warn('[AgentMedia] play() rejected', { agentId, error: e?.message || String(e) });
      try { console.warn('[AgentMedia] play() rejected', { agentId, error: e?.message || String(e) }); } catch {}
    });
  }, [agentId, currentScene?.clip.clip, currentScene?.startTime]);

  if (!isPlaying || hidden) {
    try { console.log('[AgentMedia] not rendered', { agentId, isPlaying, hidden }); } catch {}
    return null;
  }
  return (
    <video
      key={playKey}
      ref={videoRef}
      muted
      playsInline
      preload="auto"
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  );
}

export const AvatarDisplay: React.FC<AvatarDisplayProps> = ({
  imageUrl,
  videoUrl,
  size = 'default',
  showVideo = true,
  shape = 'circle',
  alt = 'avatar',
  className = '',
  onClick,
  agentId
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
  // Show video on hover, or always show if there's no image (video-only upload)
  const showVideoPreview = showVideo && videoUrl && !videoError && (isHovered || !imageUrl);

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
      style={containerStyle}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      {/* Base layer: show chosen avatar video/image if available; otherwise placeholder */}
      {showVideoPreview ? (
        <video
          src={videoUrl}
          poster={imageUrl || undefined}
          autoPlay
          loop
          muted
          playsInline
          onError={handleVideoError}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      ) : imageUrl ? (
        <img
          src={imageUrl}
          alt={alt}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      ) : (
        <Avatar size={sizeInPixels} shape={shape} icon={<UserOutlined />} />
      )}

      {/* Dynamic scene overlay (always on top when agentId provided) */}
      {agentId ? (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}>
          <AgentMedia agentId={agentId} />
        </div>
      ) : null}

      {/* Optional video badge only for explicit video preview (not dynamic scenes) */}
      {!agentId && videoUrl && !videoError && (
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
