import React, { useState, useEffect } from 'react';
import AgentCardComponent from '../pages/Agents/components/AgentCard';
import { DynamicAgentAnimation } from './DynamicAgentAnimation';
import { AgentMedia } from '@/components/Avatar/AvatarDisplay';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { Agent, type AgentCard } from '../pages/Agents/types';

interface EnhancedAgentCardProps {
  agent: Agent | AgentCard;
  onChat?: () => void;
  useDynamicSystem?: boolean;
  width?: number;
  height?: number;
}

/**
 * Enhanced AgentCard component that integrates with the dynamic avatar scene system.
 * Falls back to the original AgentCard component when dynamic scenes are not available.
 */
const EnhancedAgentCard: React.FC<EnhancedAgentCardProps> = ({
  agent,
  onChat,
  useDynamicSystem = true,
  width = 300,
  height = 169 // 16:9 aspect ratio
}) => {
  const [hasDynamicScenes, setHasDynamicScenes] = useState(false);
  
  // Get agent ID (compatible with both Agent and AgentCard)
  const agentId = (agent as any).id || (agent as any).card?.id;
  
  // Check if agent has dynamic scenes available
  const agentScenes = useAvatarSceneStore(state => 
    agentId ? state.getAgentScenes(agentId) : []
  );
  
  useEffect(() => {
    setHasDynamicScenes(agentScenes.length > 0);
  }, [agentScenes]);

  // If dynamic system is enabled and agent has scenes, render with dynamic animation
  if (useDynamicSystem && agentId && hasDynamicScenes) {
    // Get agent info for display
    const rawName = (agent as any).name ?? (agent as any).card?.name;
    const rawDesc = (agent as any).description ?? (agent as any).card?.description;
    const safeName = typeof rawName === 'string' ? rawName : '';
    const safeDesc = typeof rawDesc === 'string' ? rawDesc : '';

    return (
      <div className="enhanced-agent-card" style={{ position: 'relative' }}>
        <div
          className="agent-gif-video-wrapper"
          style={{ 
            width, 
            height, 
            marginBottom: 26, 
            borderRadius: 28, 
            background: '#222c', 
            border: '4px solid var(--primary-color, #3b82f6)', 
            boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            overflow: 'hidden' 
          }}
        >
          <DynamicAgentAnimation
            agentId={agentId}
            fallbackUrl="/assets/default-avatar.gif"
            width={width}
            height={height}
            autoPlay={true}
            loop={true}
            muted={true}
            style={{ 
              width: '100%', 
              height: '100%', 
              borderRadius: 28 
            }}
            onError={(error) => {
              console.error('Enhanced avatar animation error:', error);
              // Could add additional fallback logic here if needed
            }}
          />
          {/* Dynamic scene overlay */}
          {agentId && (
            <div style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}>
              <AgentMedia agentId={agentId} />
            </div>
          )}
        </div>
        
        {/* Agent info and controls - simplified version */}
        <div className="agent-info-row" style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          gap: 12 
        }}>
          <div className="agent-name" style={{ 
            flex: 1, 
            textAlign: 'center',
            fontSize: '16px',
            fontWeight: 'bold'
          }}>
            {safeName}
          </div>
        </div>

        {safeDesc && (
          <div className="agent-desc" style={{ 
            textAlign: 'center',
            fontSize: '14px',
            color: '#666',
            marginTop: '8px'
          }}>
            {safeDesc}
          </div>
        )}
      </div>
    );
  }

  // Fallback to original AgentAvatar component
  return <AgentCardComponent agent={agent} onChat={onChat} />;
};

export default EnhancedAgentCard;
