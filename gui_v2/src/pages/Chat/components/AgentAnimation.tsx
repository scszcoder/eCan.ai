import React, { useMemo, useEffect, useState, useCallback } from 'react';
import agentGifs, { logVideoSupport } from '@/assets/gifs';
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

function getRandomGif(): string {
  if (!Array.isArray(agentGifs) || agentGifs.length === 0) return '';
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx] as string;
}

// Global flag to ensure video support detection only runs once
let videoSupportChecked = false;

interface AgentAnimationProps {
  agentId?: string;
  className?: string;
  useDynamicSystem?: boolean; // New prop to enable/disable dynamic system
}

const AgentAnimation: React.FC<AgentAnimationProps> = ({ 
  agentId, 
  className, 
  useDynamicSystem = false // Temporarily disabled until store is properly initialized
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

  // Use agent ID as dependency to ensure the same agent always uses the same GIF (fallback)
  const fallbackMediaUrl = useMemo<string>(() => {
    // Use agent ID as seed to generate consistent random number
    if (!agentId) return getRandomGif();
    const seed = agentId.split('').reduce((acc: number, char: string) => acc + char.charCodeAt(0), 0);
    const index = seed % (agentGifs?.length || 1);
    const selectedGif = Array.isArray(agentGifs) && agentGifs.length > 0 ? agentGifs[index] as string : '';
    
    // Return selected GIF or ultimate fallback
    return selectedGif || '/assets/default-avatar.gif';
  }, [agentId]);

  // Define multiple fallback levels for static mode
  const staticFallbackUrls = useMemo(() => [
    fallbackMediaUrl,
    '/assets/default-avatar.gif',
    '/assets/avatars/default.gif',
    '/assets/default.png',
    'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBmMGYwIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkF2YXRhcjwvdGV4dD48L3N2Zz4='
  ].filter(Boolean), [fallbackMediaUrl]);

  const [staticFallbackLevel, setStaticFallbackLevel] = useState(0);

  // Use video if mediaUrl exists and ends with .webm or .mp4
  const isVideo = Boolean(fallbackMediaUrl && typeof fallbackMediaUrl === 'string' && 
    (fallbackMediaUrl.trim().toLowerCase().endsWith('.webm') || fallbackMediaUrl.trim().toLowerCase().endsWith('.mp4')));

  // Check video support on first render
  useEffect(() => {
    if (!videoSupportChecked) {
      videoSupportChecked = true;
      logVideoSupport();
    }
  }, []);

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
            src={currentStaticUrl}
            autoPlay
            loop
            muted
            playsInline
            style={{ 
              width: '100%', 
              height: '100%', 
              objectFit: 'contain', 
              borderRadius: '12px',
              background: 'transparent' 
            }}
            poster="./assets/default-agent-poster.png"
            onError={handleStaticMediaError}
          />
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
            onError={handleStaticMediaError}
          />
        )}
      </AnimationWrapper>
    </AnimationContainer>
  );
};

export default React.memo(AgentAnimation);
