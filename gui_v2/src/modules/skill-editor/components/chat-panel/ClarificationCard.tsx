/**
 * ClarificationCard - Renders clarification questions with multiple-choice options
 */

import React, { useState, useCallback } from 'react';
import { Button, Checkbox, Radio, Space } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import type { ClarificationQuestion } from '../../types/skill-editor-chat.types';

interface ClarificationCardProps {
  questions: ClarificationQuestion[];
  onSubmit: (answers: Record<string, string[]>) => void;
  isSubmitting?: boolean;
}

const CardContainer = styled.div`
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
`;

const CardTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
`;

const QuestionContainer = styled.div`
  margin-bottom: 16px;
  
  &:last-of-type {
    margin-bottom: 12px;
  }
`;

const QuestionText = styled.div`
  font-size: 13px;
  font-weight: 500;
  color: #e2e8f0;
  margin-bottom: 8px;
`;

const QuestionContext = styled.div`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.7);
  margin-bottom: 8px;
  font-style: italic;
`;

const ChoiceContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 4px;
`;

const ChoiceItem = styled.div<{ $selected: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background: ${props => props.$selected ? 'rgba(59, 130, 246, 0.15)' : 'rgba(15, 23, 42, 0.5)'};
  border: 1px solid ${props => props.$selected ? 'rgba(59, 130, 246, 0.4)' : 'rgba(148, 163, 184, 0.2)'};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover {
    background: ${props => props.$selected ? 'rgba(59, 130, 246, 0.2)' : 'rgba(51, 65, 85, 0.5)'};
    border-color: rgba(59, 130, 246, 0.3);
  }
`;

const ChoiceLabel = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: #e2e8f0;
`;

const ChoiceDescription = styled.span`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.7);
  margin-left: 4px;
`;

const SubmitButton = styled(Button)`
  width: 100%;
  margin-top: 8px;
`;

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  questions,
  onSubmit,
  isSubmitting = false,
}) => {
  const [answers, setAnswers] = useState<Record<string, string[]>>({});

  // Log when component mounts with questions
  React.useEffect(() => {
    console.log('[ClarificationCard] Mounted with questions:', {
      count: questions.length,
      questionIds: questions.map(q => q.id),
    });
    return () => {
      console.log('[ClarificationCard] Unmounting');
    };
  }, [questions]);

  const handleChoiceToggle = useCallback((questionId: string, choiceId: string, allowMultiple: boolean) => {
    console.log('[ClarificationCard] Choice toggled:', { questionId, choiceId, allowMultiple });
    setAnswers(prev => {
      const currentAnswers = prev[questionId] || [];
      
      if (allowMultiple) {
        // Toggle for multi-select
        if (currentAnswers.includes(choiceId)) {
          const newAnswers = {
            ...prev,
            [questionId]: currentAnswers.filter(id => id !== choiceId),
          };
          console.log('[ClarificationCard] Updated answers (removed):', newAnswers);
          return newAnswers;
        } else {
          const newAnswers = {
            ...prev,
            [questionId]: [...currentAnswers, choiceId],
          };
          console.log('[ClarificationCard] Updated answers (added):', newAnswers);
          return newAnswers;
        }
      } else {
        // Single select - replace
        const newAnswers = {
          ...prev,
          [questionId]: [choiceId],
        };
        console.log('[ClarificationCard] Updated answers (single select):', newAnswers);
        return newAnswers;
      }
    });
  }, []);

  const handleSubmit = useCallback(() => {
    console.log('[ClarificationCard] Submitting answers:', answers);
    onSubmit(answers);
  }, [answers, onSubmit]);

  const isComplete = questions.every(q => (answers[q.id] || []).length > 0);

  return (
    <CardContainer>
      <CardHeader>
        <span style={{ fontSize: 16 }}>🤔</span>
        <CardTitle>I have a few questions to better understand your requirements:</CardTitle>
      </CardHeader>
      
      {questions.map((question, index) => (
        <QuestionContainer key={question.id}>
          <QuestionText>
            {index + 1}. {question.question}
          </QuestionText>
          {question.context && (
            <QuestionContext>{question.context}</QuestionContext>
          )}
          <ChoiceContainer>
            {question.choices.map(choice => {
              const isSelected = (answers[question.id] || []).includes(choice.id);
              return (
                <ChoiceItem
                  key={choice.id}
                  $selected={isSelected}
                  onClick={() => handleChoiceToggle(question.id, choice.id, question.allow_multiple)}
                >
                  {question.allow_multiple ? (
                    <Checkbox checked={isSelected} style={{ marginTop: 2 }} />
                  ) : (
                    <Radio checked={isSelected} style={{ marginTop: 2 }} />
                  )}
                  <div>
                    <ChoiceLabel>{choice.label}</ChoiceLabel>
                    {choice.description && (
                      <ChoiceDescription>- {choice.description}</ChoiceDescription>
                    )}
                  </div>
                </ChoiceItem>
              );
            })}
          </ChoiceContainer>
        </QuestionContainer>
      ))}
      
      <SubmitButton
        type="primary"
        icon={<CheckOutlined />}
        onClick={handleSubmit}
        disabled={!isComplete || isSubmitting}
        loading={isSubmitting}
      >
        {isSubmitting ? 'Submitting...' : 'Submit Answers'}
      </SubmitButton>
    </CardContainer>
  );
};

export default ClarificationCard;
