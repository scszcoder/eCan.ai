import React, { useMemo, useEffect, useState } from 'react';
import agentGifs, { logVideoSupport } from '@/assets/gifs';
import styled from '@emotion/styled';
import { DynamicAgentAnimation } from '../../../components/DynamicAgentAnimation';
import { useAvatarSceneStore } from '../../../stores/avatarSceneStore';

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
  useDynamicSystem = true 
}) => {
  const [hasDynamicScenes, setHasDynamicScenes] = useState(false);
  
  // Check if agent has dynamic scenes available
  const agentScenes = useAvatarSceneStore(state => 
    agentId ? state.getAgentScenes(agentId) : []
  );
  
  useEffect(() => {
    setHasDynamicScenes(agentScenes.length > 0);
  }, [agentScenes]);

  // Use agent ID as dependency to ensure the same agent always uses the same GIF (fallback)
  const fallbackMediaUrl = useMemo<string>(() => {
    // Use agent ID as seed to generate consistent random number
    if (!agentId) return getRandomGif();
    const seed = agentId.split('').reduce((acc: number, char: string) => acc + char.charCodeAt(0), 0);
    const index = seed % (agentGifs?.length || 1);
    return Array.isArray(agentGifs) && agentGifs.length > 0 ? agentGifs[index] as string : '';
  }, [agentId]);

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
            onError={(error) => console.error('Dynamic animation error:', error)}
          />
        </AnimationWrapper>
      </AnimationContainer>
    );
  }

  // Fallback to original static behavior
  if (!fallbackMediaUrl) {
    return null;
  }

  return (
    <AnimationContainer className={className}>
      <AnimationWrapper>
        {isVideo ? (
          <video
            src={fallbackMediaUrl}
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
            onError={(e) => console.error('Video load error:', fallbackMediaUrl, e)}
          />
        ) : (
          <img 
            src={fallbackMediaUrl} 
            alt="Agent animation"
            style={{ 
              width: '100%', 
              height: '100%', 
              objectFit: 'contain', 
              borderRadius: '12px' 
            }}
            onError={(e) => console.error('Image load error:', fallbackMediaUrl, e)}
          />
        )}
      </AnimationWrapper>
    </AnimationContainer>
  );
};

export default React.memo(AgentAnimation);
