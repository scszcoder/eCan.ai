import React, { useMemo, useEffect, useState, useCallback, useRef } from 'react';
import styled from '@emotion/styled';
import { DynamicAgentAnimation } from '../../../components/DynamicAgentAnimation';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';

const AnimationContainer = styled.div`
  width: 100%;
  padding: 8px 12px;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 8px;
`;

const AnimationWrapper = styled.div`
  width: 100%;
  max-width: 200px;
  aspect-ratio: 16/9;
  border-radius: 12px;
  background: rgba(34, 34, 34, 0.8);
  border: 2px solid var(--primary-color, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
`;

interface AgentAnimationProps {
  agentId?: string;
  className?: string;
  useDynamicSystem?: boolean; // New prop to enable/disable dynamic system
  agentAvatar?: {
    id?: string;
    videoPath?: string;
    imageUrl?: string;
    videoExists?: boolean;
  }; // Agent avatar from backend
}

const AgentAnimation: React.FC<AgentAnimationProps> = ({ 
  agentId, 
  className, 
  useDynamicSystem = false, // Temporarily disabled until store is properly initialized
  agentAvatar // Avatar data from backend
}) => {
  const [hasDynamicScenes, setHasDynamicScenes] = useState(false);
  
  // Check if agent has dynamic scenes available (with error handling)
  const agentScenes = useMemo(() => {
    if (!agentId || !useDynamicSystem) return [];
    
    try {
      const store = useAvatarSceneStore.getState();
      return store.getAgentScenes ? store.getAgentScenes(agentId) : [];
    } catch (error) {
      console.warn('Avatar scene store not available, falling back to static mode:', error);
      return [];
    }
  }, [agentId, useDynamicSystem]);
  
  useEffect(() => {
    setHasDynamicScenes(agentScenes.length > 0);
  }, [agentScenes]);

  // Use backend avatar (video preferred, then image)
  const mediaUrl = useMemo<string>(() => {
    // Use backend avatar video if available
    if (agentAvatar?.videoExists && agentAvatar.videoPath) {
      return agentAvatar.videoPath;
    }
    
    // Use backend avatar image if available
    if (agentAvatar?.imageUrl) {
      return agentAvatar.imageUrl;
    }
    
    // No avatar available
    return '';
  }, [agentAvatar?.id, agentAvatar?.videoPath, agentAvatar?.imageUrl, agentAvatar?.videoExists]);

  // Fallback URLs if media fails to load
  const staticFallbackUrls = useMemo(() => {
    if (!mediaUrl) {
      // No avatar, show placeholder
      return ['data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBmMGYwIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkF2YXRhcjwvdGV4dD48L3N2Zz4='];
    }
    return [mediaUrl];
  }, [mediaUrl]);

  const [staticFallbackLevel, setStaticFallbackLevel] = useState(0);
  const loadedRef = useRef(false);

  // Reset loaded flag whenever URL changes
  useEffect(() => {
    loadedRef.current = false;
  }, [mediaUrl, staticFallbackLevel]);

  // Use video if mediaUrl exists and ends with .webm or .mp4
  const isVideo = Boolean(mediaUrl && typeof mediaUrl === 'string' && 
    (mediaUrl.trim().toLowerCase().endsWith('.webm') || mediaUrl.trim().toLowerCase().endsWith('.mp4') ||
     mediaUrl.includes('.webm') || mediaUrl.includes('.mp4')));

  // If dynamic system is enabled and agent has scenes, use DynamicAgentAnimation
  if (useDynamicSystem && agentId && hasDynamicScenes) {
    try {
      return (
        <AnimationContainer className={className}>
          <AnimationWrapper>
            <DynamicAgentAnimation
              agentId={agentId}
              fallbackUrl={fallbackMediaUrl}
              width={200}
              height={112} // 16:9 aspect ratio
              autoPlay={true}
              loop={true}
              muted={true}
              style={{ 
                width: '100%', 
                height: '100%', 
                borderRadius: '12px' 
              }}
              onError={(error) => {
                console.error('Dynamic animation error:', error);
                // Fall back to static mode on error
                setHasDynamicScenes(false);
              }}
            />
          </AnimationWrapper>
        </AnimationContainer>
      );
    } catch (error) {
      console.error('Failed to render dynamic animation, falling back to static:', error);
      // Continue to fallback static rendering below
    }
  }

  // Progressive fallback error handler for static mode
  const handleStaticMediaError = useCallback(() => {
    // If media already reported load/playable, ignore spurious errors
    if (loadedRef.current) return;
    if (staticFallbackLevel < staticFallbackUrls.length - 1) {
      const nextLevel = staticFallbackLevel + 1;
      setStaticFallbackLevel(nextLevel);
      console.warn(`Static media failed, trying fallback ${nextLevel}: ${staticFallbackUrls[nextLevel]}`);
    } else {
      console.error('All static media fallbacks failed for agent:', agentId);
    }
  }, [staticFallbackLevel, staticFallbackUrls, agentId]);

  // Get current static media URL
  const currentStaticUrl = staticFallbackUrls[staticFallbackLevel] || staticFallbackUrls[staticFallbackUrls.length - 1];

  // Fallback to original static behavior
  if (!currentStaticUrl) {
    return (
      <AnimationContainer className={className}>
        <AnimationWrapper>
          <div style={{ 
            width: '100%', 
            height: '100%', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            background: '#f0f0f0',
            borderRadius: '12px',
            color: '#999',
            fontSize: '14px'
          }}>
            Avatar
          </div>
        </AnimationWrapper>
      </AnimationContainer>
    );
  }

  const currentIsVideo = Boolean(currentStaticUrl && typeof currentStaticUrl === 'string' && 
    (currentStaticUrl.trim().toLowerCase().endsWith('.webm') || currentStaticUrl.trim().toLowerCase().endsWith('.mp4')));


  return (
    <AnimationContainer className={className}>
      <AnimationWrapper>
        {currentIsVideo ? (
          <video
            autoPlay
            loop
            muted
            playsInline
            preload="auto"
            style={{ 
              width: '100%', 
              height: '100%', 
              objectFit: 'contain', 
              borderRadius: '12px',
              background: 'transparent' 
            }}
            poster=""
            onLoadedData={() => { loadedRef.current = true; }}
            onCanPlay={() => { loadedRef.current = true; }}
            onError={handleStaticMediaError}
          >
            <source src={currentStaticUrl} type="video/webm" />
          </video>
        ) : (
          <img 
            src={currentStaticUrl} 
            alt="Agent animation"
            style={{ 
              width: '100%', 
              height: '100%', 
              objectFit: 'contain', 
              borderRadius: '12px' 
            }}
            onLoad={() => { loadedRef.current = true; }}
            onError={handleStaticMediaError}
          />
        )}
      </AnimationWrapper>
    </AnimationContainer>
  );
};

export default React.memo(AgentAnimation);
