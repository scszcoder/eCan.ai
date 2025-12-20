import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { AvatarSceneOrchestrator } from '../services/avatarSceneOrchestrator';
import { AvatarEventManager } from '../services/avatarEventManager';
import { SceneClip, AgentSceneState } from '../types/avatarScene';
import { logger } from '../utils/logger';

interface DynamicAgentAnimationProps {
  agentId: string;
  className?: string;
  style?: React.CSSProperties;
  fallbackUrl?: string;
  width?: number;
  height?: number;
  autoPlay?: boolean;
  loop?: boolean;
  muted?: boolean;
  onSceneStart?: (clip: SceneClip) => void;
  onSceneEnd?: (clip: SceneClip) => void;
  onError?: (error: Error) => void;
}

export const DynamicAgentAnimation: React.FC<DynamicAgentAnimationProps> = ({
  agentId,
  className = '',
  style = {},
  fallbackUrl = '/assets/default-avatar.gif',
  width = 200,
  height = 200,
  autoPlay = true,
  loop = true,
  muted = true,
  onSceneStart,
  onSceneEnd,
  onError
}) => {
  const [currentClip, setCurrentClip] = useState<SceneClip | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mediaType, setMediaType] = useState<'gif' | 'video' | null>(null);
  const [currentMediaUrl, setCurrentMediaUrl] = useState<string>(fallbackUrl);
  const [fallbackLevel, setFallbackLevel] = useState<number>(0);
  
  const mediaRef = useRef<HTMLImageElement | HTMLVideoElement>(null);
  const orchestratorRef = useRef<AvatarSceneOrchestrator | null>(null);
  const eventManagerRef = useRef<AvatarEventManager | null>(null);
  
  // Get scene state from store
  const agentSceneState = useAvatarSceneStore(state => state.getAgentState(agentId));
  const currentScene = useAvatarSceneStore(state => state.getCurrentScene(agentId));

  // Initialize orchestrator and event manager
  useEffect(() => {
    try {
      orchestratorRef.current = AvatarSceneOrchestrator.getInstance();
      eventManagerRef.current = AvatarEventManager.getInstance();
      
      // Initialize agent in orchestrator if not already done
      orchestratorRef.current.initializeAgent(agentId);
      
      logger.info(`DynamicAgentAnimation initialized for agent: ${agentId}`);
    } catch (err) {
      const errorMsg = `Failed to initialize avatar system for agent ${agentId}`;
      logger.error(errorMsg, err);
      setError(errorMsg);
      onError?.(err instanceof Error ? err : new Error(errorMsg));
    }
  }, [agentId, onError]);

  // Subscribe to scene state changes
  useEffect(() => {
    if (!orchestratorRef.current) return;

    const unsubscribe = orchestratorRef.current.subscribeToAgent(agentId, (state: AgentSceneState) => {
      const { currentClip, isPlaying } = state;
      
      setCurrentClip(currentClip);
      setIsPlaying(isPlaying);
      
      if (currentClip) {
        // Reset fallback level when clip changes
        setFallbackLevel(0);
        setError(null);
        
        // Determine media type from URL
        const url = currentClip.mediaUrl.toLowerCase();
        if (url.endsWith('.gif') || url.endsWith('.png') || url.endsWith('.jpg') || url.endsWith('.jpeg')) {
          setMediaType('gif');
        } else if (url.endsWith('.mp4') || url.endsWith('.webm') || url.endsWith('.mov')) {
          setMediaType('video');
        } else {
          setMediaType('gif'); // Default fallback
        }
        
        onSceneStart?.(currentClip);
      }
    });

    return unsubscribe;
  }, [agentId, onSceneStart]);

  // Handle media load events
  const handleMediaLoad = useCallback(() => {
    setError(null);
    if (currentClip && autoPlay) {
      setIsPlaying(true);
    }
  }, [currentClip, autoPlay]);

  const handleMediaError = useCallback((e: Event) => {
    const currentUrl = getMediaUrl();
    logger.warn(`Failed to load media: ${currentUrl} for agent ${agentId}`);
    
    // Try next fallback if available
    if (fallbackLevel < fallbackUrls.length - 1) {
      const nextLevel = fallbackLevel + 1;
      setFallbackLevel(nextLevel);
      setError(null); // Clear error since we're trying a fallback
      logger.info(`Trying fallback ${nextLevel}: ${fallbackUrls[nextLevel]}`);
    } else {
      // All fallbacks exhausted
      const errorMsg = `All media fallbacks failed for agent ${agentId}`;
      logger.error(errorMsg, e);
      setError(errorMsg);
      onError?.(new Error(errorMsg));
    }
  }, [agentId, onError, fallbackLevel, fallbackUrls, getMediaUrl]);

  const handleMediaEnd = useCallback(() => {
    if (currentClip) {
      onSceneEnd?.(currentClip);
      
      // Notify orchestrator that scene ended
      orchestratorRef.current?.handleSceneEnd(agentId);
    }
  }, [agentId, currentClip, onSceneEnd]);

  // Define fallback hierarchy
  const fallbackUrls = useMemo(() => [
    currentClip?.mediaUrl,
    fallbackUrl,
    '/assets/default-avatar.gif',
    '/assets/avatars/default.gif',
    '/assets/default.png',
    'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBmMGYwIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkF2YXRhcjwvdGV4dD48L3N2Zz4=' // SVG fallback
  ].filter(Boolean), [currentClip?.mediaUrl, fallbackUrl]);

  // Get current media URL with progressive fallback
  const getMediaUrl = useCallback(() => {
    return fallbackUrls[fallbackLevel] || fallbackUrls[fallbackUrls.length - 1];
  }, [fallbackUrls, fallbackLevel]);

  // Get current caption
  const getCaption = useCallback(() => {
    return currentClip?.caption || '';
  }, [currentClip]);

  // Render media element based on type
  const renderMedia = () => {
    const mediaUrl = getMediaUrl();
    const caption = getCaption();
    
    if (error) {
      return (
        <div 
          className={`flex items-center justify-center bg-gray-200 text-gray-500 ${className}`}
          style={{ width, height, ...style }}
        >
          <div className="text-center">
            <div className="text-sm">Avatar Error</div>
            <div className="text-xs mt-1">{error}</div>
          </div>
        </div>
      );
    }

    if (mediaType === 'video') {
      return (
        <div className={`relative ${className}`} style={style}>
          <video
            ref={mediaRef as React.RefObject<HTMLVideoElement>}
            src={mediaUrl}
            width={width}
            height={height}
            autoPlay={autoPlay && isPlaying}
            loop={loop}
            muted={muted}
            onLoadedData={handleMediaLoad}
            onError={handleMediaError}
            onEnded={handleMediaEnd}
            className="object-cover"
          />
          {caption && (
            <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs p-1 text-center">
              {caption}
            </div>
          )}
        </div>
      );
    }

    // Default to image/GIF
    return (
      <div className={`relative ${className}`} style={style}>
        <img
          ref={mediaRef as React.RefObject<HTMLImageElement>}
          src={mediaUrl}
          alt={`Avatar for ${agentId}`}
          width={width}
          height={height}
          onLoad={handleMediaLoad}
          onError={handleMediaError}
          className="object-cover"
        />
        {caption && (
          <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs p-1 text-center">
            {caption}
          </div>
        )}
      </div>
    );
  };

  return renderMedia();
};

export default DynamicAgentAnimation;
