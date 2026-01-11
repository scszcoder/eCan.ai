/**
 * PlanCard - Renders an implementation plan with approval buttons
 */

import React from 'react';
import { Button, Tag, Space } from 'antd';
import { CheckOutlined, CloseOutlined, RocketOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import type { ImplementationPlan } from '../../types/skill-editor-chat.types';

interface PlanCardProps {
  plan: ImplementationPlan;
  onApprove?: () => void;
  onReject?: () => void;
  isSubmitting?: boolean;
  /** If provided, renders in read-only mode showing this action was taken */
  submittedAction?: 'approved' | 'revised';
}

const CardContainer = styled.div`
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
`;

const CardTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const ComplexityBadge = styled(Tag)<{ $complexity: string }>`
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  background: ${props => {
    switch (props.$complexity) {
      case 'simple': return 'rgba(34, 197, 94, 0.2)';
      case 'medium': return 'rgba(234, 179, 8, 0.2)';
      case 'complex': return 'rgba(239, 68, 68, 0.2)';
      default: return 'rgba(148, 163, 184, 0.2)';
    }
  }};
  color: ${props => {
    switch (props.$complexity) {
      case 'simple': return '#22c55e';
      case 'medium': return '#eab308';
      case 'complex': return '#ef4444';
      default: return '#94a3b8';
    }
  }};
  border: 1px solid ${props => {
    switch (props.$complexity) {
      case 'simple': return 'rgba(34, 197, 94, 0.4)';
      case 'medium': return 'rgba(234, 179, 8, 0.4)';
      case 'complex': return 'rgba(239, 68, 68, 0.4)';
      default: return 'rgba(148, 163, 184, 0.4)';
    }
  }};
`;

const Summary = styled.div`
  font-size: 13px;
  color: #e2e8f0;
  margin-bottom: 16px;
  line-height: 1.5;
`;

const StepsContainer = styled.div`
  margin-bottom: 16px;
`;

const StepsTitle = styled.div`
  font-size: 12px;
  font-weight: 600;
  color: rgba(148, 163, 184, 0.8);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const StepItem = styled.div`
  display: flex;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  
  &:last-child {
    border-bottom: none;
  }
`;

const StepNumber = styled.div`
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.2);
  border: 1px solid rgba(59, 130, 246, 0.4);
  color: #3b82f6;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const StepContent = styled.div`
  flex: 1;
`;

const StepTitle = styled.div`
  font-size: 13px;
  font-weight: 500;
  color: #e2e8f0;
  margin-bottom: 4px;
`;

const StepDescription = styled.div`
  font-size: 12px;
  color: rgba(148, 163, 184, 0.8);
  line-height: 1.4;
`;

const NodeTags = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
`;

const NodeTag = styled(Tag)`
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(139, 92, 246, 0.15);
  color: #a78bfa;
  border: 1px solid rgba(139, 92, 246, 0.3);
`;

const EstimatedNodes = styled.div`
  margin-bottom: 16px;
  padding: 10px 12px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
`;

const EstimatedNodesTitle = styled.span`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.7);
  margin-right: 8px;
`;

const ButtonContainer = styled.div`
  display: flex;
  gap: 8px;
`;

const ApproveButton = styled(Button)`
  flex: 1;
`;

const RejectButton = styled(Button)`
  flex: 1;
`;

export const PlanCard: React.FC<PlanCardProps> = ({
  plan,
  onApprove,
  onReject,
  isSubmitting = false,
  submittedAction,
}) => {
  // Read-only mode when submittedAction is provided
  const isReadOnly = !!submittedAction;

  // Log when component mounts with plan
  React.useEffect(() => {
    console.log('[PlanCard] Mounted with plan:', {
      summary: plan.summary,
      complexity: plan.complexity,
      stepsCount: plan.steps.length,
      estimatedNodes: plan.estimated_nodes,
      isReadOnly,
      submittedAction,
    });
    return () => {
      console.log('[PlanCard] Unmounting');
    };
  }, [plan, isReadOnly, submittedAction]);

  const handleApprove = React.useCallback(() => {
    console.log('[PlanCard] Plan approved by user');
    if (onApprove) onApprove();
  }, [onApprove]);

  const handleReject = React.useCallback(() => {
    console.log('[PlanCard] Plan rejected by user');
    if (onReject) onReject();
  }, [onReject]);

  return (
    <CardContainer>
      <CardHeader>
        <CardTitle>
          <RocketOutlined style={{ color: isReadOnly ? (submittedAction === 'approved' ? '#22c55e' : '#f59e0b') : '#22c55e' }} />
          {isReadOnly 
            ? (submittedAction === 'approved' ? '✅ Plan Approved' : '📝 Plan Revised')
            : 'Implementation Plan'}
        </CardTitle>
        <ComplexityBadge $complexity={plan.complexity}>
          {plan.complexity.charAt(0).toUpperCase() + plan.complexity.slice(1)}
        </ComplexityBadge>
      </CardHeader>
      
      <Summary>{plan.summary}</Summary>
      
      <StepsContainer>
        <StepsTitle>Steps</StepsTitle>
        {plan.steps.map((step, index) => (
          <StepItem key={index}>
            <StepNumber>{index + 1}</StepNumber>
            <StepContent>
              <StepTitle>{step.title}</StepTitle>
              <StepDescription>{step.description}</StepDescription>
              {step.node_types.length > 0 && (
                <NodeTags>
                  {step.node_types.map((nodeType, i) => (
                    <NodeTag key={i}>{nodeType}</NodeTag>
                  ))}
                </NodeTags>
              )}
            </StepContent>
          </StepItem>
        ))}
      </StepsContainer>
      
      {plan.estimated_nodes.length > 0 && (
        <EstimatedNodes>
          <EstimatedNodesTitle>Estimated nodes:</EstimatedNodesTitle>
          <Space size={4} wrap>
            {plan.estimated_nodes.map((node, i) => (
              <NodeTag key={i}>{node}</NodeTag>
            ))}
          </Space>
        </EstimatedNodes>
      )}
      
      {/* Only show buttons in interactive mode */}
      {!isReadOnly && (
        <ButtonContainer>
          <ApproveButton
            type="primary"
            icon={<CheckOutlined />}
            onClick={handleApprove}
            disabled={isSubmitting}
            loading={isSubmitting}
            style={{ background: '#22c55e', borderColor: '#22c55e' }}
          >
            Proceed
          </ApproveButton>
          <RejectButton
            icon={<CloseOutlined />}
            onClick={handleReject}
            disabled={isSubmitting}
          >
            Revise
          </RejectButton>
        </ButtonContainer>
      )}
    </CardContainer>
  );
};

export default PlanCard;
