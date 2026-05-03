/**
 * ClarificationCard - Renders clarification questions with multiple-choice options
 */

import React, { useState, useCallback } from 'react';
import { Button, Checkbox, Input, Radio, Select } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import type { ClarificationQuestion } from '../../types/skill-editor-chat.types';

interface ClarificationCardProps {
  questions: ClarificationQuestion[];
  onSubmit?: (answers: Record<string, string[]>) => void;
  isSubmitting?: boolean;
  /** If provided, renders in read-only mode showing these answers */
  submittedAnswers?: Record<string, string[]>;
  /** Override locale; defaults to navigator.language. Use 'zh' or 'en'. */
  userLang?: string;
}

// Tiny i18n table for the static UI chrome of this card.
// Question/choice text comes from the backend already-localized.
const I18N: Record<'en' | 'zh', Record<string, string>> = {
  en: {
    title_active: 'I have a few questions to better understand your requirements:',
    title_readonly: 'Your answers to clarification questions:',
    please_select: '(please select)',
    submit: 'Submit Answers',
    submitting: 'Submitting...',
    answered_count: 'Please answer all questions ({answered}/{total} answered)',
    freeform_placeholder: 'Please describe in detail...',
    typeahead_placeholder: 'Type to search and select…',
  },
  zh: {
    title_active: '我有几个问题想了解一下：',
    title_readonly: '你对澄清问题的回答：',
    please_select: '（请选择）',
    submit: '提交回答',
    submitting: '提交中...',
    answered_count: '请回答所有问题（已回答 {answered}/{total}）',
    freeform_placeholder: '请详细描述...',
    typeahead_placeholder: '输入关键字搜索并选择…',
  },
};

function _resolveLang(override?: string): 'en' | 'zh' {
  const raw = (override
    || (typeof navigator !== 'undefined' ? navigator.language : '')
    || ''
  ).toLowerCase();
  return raw.startsWith('zh') ? 'zh' : 'en';
}

function _t(lang: 'en' | 'zh', key: string, vars?: Record<string, string | number>): string {
  let text = I18N[lang][key] ?? I18N.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
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

const FreeformInput = styled(Input.TextArea)`
  margin-top: 8px;
  background: rgba(15, 23, 42, 0.7) !important;
  border: 1px solid rgba(59, 130, 246, 0.3) !important;
  color: #e2e8f0 !important;
  border-radius: 6px;
  font-size: 12px;
  &::placeholder {
    color: rgba(148, 163, 184, 0.5) !important;
  }
  &:focus {
    border-color: rgba(59, 130, 246, 0.6) !important;
  }
`;

const FreeformReadOnly = styled.div`
  margin-top: 6px;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 6px;
  font-size: 12px;
  color: #e2e8f0;
  font-style: italic;
`;

const SubmitButton = styled(Button)`
  width: 100%;
  margin-top: 8px;
`;

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  questions,
  onSubmit,
  isSubmitting = false,
  submittedAnswers,
  userLang,
}) => {
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [freeformText, setFreeformText] = useState<Record<string, string>>({});
  const lang = _resolveLang(userLang);
  
  // Read-only mode when submittedAnswers is provided
  const isReadOnly = !!submittedAnswers;
  const displayAnswers = submittedAnswers || answers;
  const displayFreeform = submittedAnswers
    ? Object.fromEntries(
        Object.entries(submittedAnswers)
          .filter(([k]) => k.startsWith('freeform_'))
          .map(([k, v]) => [k.slice('freeform_'.length), (v || [''])[0]])
      )
    : freeformText;

  // Defensive: ensure questions is a valid array with proper structure
  const safeQuestions = React.useMemo(() => {
    if (!Array.isArray(questions)) return [];
    return questions.filter(q => 
      q && 
      typeof q === 'object' && 
      q.id && 
      q.question && 
      Array.isArray(q.choices)
    ).map(q => ({
      ...q,
      choices: q.choices.filter((c: any) => c && typeof c === 'object' && c.id && c.label)
    }));
  }, [questions]);

  // Log when component mounts with questions
  React.useEffect(() => {
    console.log('[ClarificationCard] Mounted with questions:', {
      count: safeQuestions.length,
      questionIds: safeQuestions.map(q => q.id),
    });
    return () => {
      console.log('[ClarificationCard] Unmounting');
    };
  }, [safeQuestions]);

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

  const handleFreeformChange = useCallback((questionId: string, text: string) => {
    setFreeformText(prev => ({ ...prev, [questionId]: text }));
  }, []);

  const handleSubmit = useCallback(() => {
    // Merge freeform text into answers as freeform_{qid} keys
    const merged: Record<string, string[]> = { ...answers };
    for (const [qid, text] of Object.entries(freeformText)) {
      if (text.trim()) {
        merged[`freeform_${qid}`] = [text.trim()];
      }
    }
    console.log('[ClarificationCard] Submitting answers:', merged);
    if (onSubmit) {
      onSubmit(merged);
    }
  }, [answers, freeformText, onSubmit]);

  const answeredCount = safeQuestions.filter(q => (displayAnswers[q.id] || []).length > 0).length;
  const isComplete = answeredCount === safeQuestions.length;

  // Don't render anything if no valid questions
  if (safeQuestions.length === 0) {
    console.warn('[ClarificationCard] No valid questions to render');
    return null;
  }

  return (
    <CardContainer>
      <CardHeader>
        <span style={{ fontSize: 16 }}>{isReadOnly ? '✅' : '🤔'}</span>
        <CardTitle>
          {_t(lang, isReadOnly ? 'title_readonly' : 'title_active')}
        </CardTitle>
      </CardHeader>
      
      {safeQuestions.map((question, index) => {
        const hasAnswer = (displayAnswers[question.id] || []).length > 0;
        const isSearchable = (question as any).widget_type === 'searchable_multi_select';

        if (isSearchable) {
          // Render an Ant Design searchable multi-select dropdown.
          // Best for large choice lists (e.g., the user's skill catalogue).
          const selectedValues = displayAnswers[question.id] || [];
          return (
            <QuestionContainer key={question.id}>
              <QuestionText style={!isReadOnly && !hasAnswer ? { color: '#fbbf24' } : undefined}>
                {index + 1}. {question.question}
                {!isReadOnly && !hasAnswer && <span style={{ fontSize: 11, marginLeft: 6, color: '#fbbf24' }}>{_t(lang, 'please_select')}</span>}
              </QuestionText>
              {question.context && (
                <QuestionContext>{question.context}</QuestionContext>
              )}
              <Select
                mode="multiple"
                showSearch
                allowClear
                placeholder={_t(lang, 'typeahead_placeholder')}
                value={selectedValues}
                disabled={isReadOnly}
                style={{ width: '100%' }}
                optionFilterProp="label"
                filterOption={(input, option) => {
                  const lbl = String((option as any)?.label ?? '').toLowerCase();
                  return lbl.includes(input.toLowerCase());
                }}
                onChange={(vals: string[]) => {
                  setAnswers(prev => ({ ...prev, [question.id]: vals }));
                }}
                options={question.choices.map(c => ({
                  value: c.id,
                  label: c.description ? `${c.label} — ${c.description}` : c.label,
                }))}
              />
            </QuestionContainer>
          );
        }

        return (
          <QuestionContainer key={question.id}>
            <QuestionText style={!isReadOnly && !hasAnswer ? { color: '#fbbf24' } : undefined}>
              {index + 1}. {question.question}
              {!isReadOnly && !hasAnswer && <span style={{ fontSize: 11, marginLeft: 6, color: '#fbbf24' }}>{_t(lang, 'please_select')}</span>}
            </QuestionText>
            {question.context && (
              <QuestionContext>{question.context}</QuestionContext>
            )}
            <ChoiceContainer>
              {question.choices.map(choice => {
                const isSelected = (displayAnswers[question.id] || []).includes(choice.id);
                // In read-only mode, only show selected choices
                if (isReadOnly && !isSelected) {
                  return null;
                }
                return (
                  <ChoiceItem
                    key={choice.id}
                    $selected={isSelected}
                    onClick={isReadOnly ? undefined : (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleChoiceToggle(question.id, choice.id, question.allow_multiple);
                    }}
                    style={isReadOnly ? { cursor: 'default' } : undefined}
                  >
                    {question.allow_multiple ? (
                      <Checkbox checked={isSelected} disabled={isReadOnly} style={{ marginTop: 2, pointerEvents: 'none' }} />
                    ) : (
                      <Radio checked={isSelected} disabled={isReadOnly} style={{ marginTop: 2, pointerEvents: 'none' }} />
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
              {/* Freeform text input: show when ANY selected choice has allow_freeform */}
              {(() => {
                const selectedIds = displayAnswers[question.id] || [];
                const anyFreeformSelected = question.choices.some(c => c.allow_freeform && selectedIds.includes(c.id));
                if (!anyFreeformSelected) return null;
                if (isReadOnly) {
                  const text = displayFreeform[question.id];
                  return text ? <FreeformReadOnly>{text}</FreeformReadOnly> : null;
                }
                return (
                  <FreeformInput
                    placeholder={_t(lang, 'freeform_placeholder')}
                    value={freeformText[question.id] || ''}
                    onChange={(e) => handleFreeformChange(question.id, e.target.value)}
                    autoSize={{ minRows: 2, maxRows: 5 }}
                    onClick={(e) => e.stopPropagation()}
                  />
                );
              })()}
            </ChoiceContainer>
          </QuestionContainer>
        );
      })}
      
      {/* Only show submit button in interactive mode */}
      {!isReadOnly && (
        <>
          {!isComplete && (
            <div style={{ fontSize: 11, color: '#fbbf24', textAlign: 'center', marginTop: 4 }}>
              {_t(lang, 'answered_count', { answered: answeredCount, total: safeQuestions.length })}
            </div>
          )}
          <SubmitButton
            type="primary"
            icon={<CheckOutlined />}
            onClick={handleSubmit}
            disabled={!isComplete || isSubmitting}
            loading={isSubmitting}
          >
            {_t(lang, isSubmitting ? 'submitting' : 'submit')}
          </SubmitButton>
        </>
      )}
    </CardContainer>
  );
};

export default ClarificationCard;
