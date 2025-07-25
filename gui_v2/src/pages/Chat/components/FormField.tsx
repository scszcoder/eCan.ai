import React from 'react';
import { AnyForm } from './forms/types';
import NormalFormUI from './forms/NormalFormUI';
import ScoreFormUI from './forms/ScoreFormUI';

interface DynamicFormProps {
  form: AnyForm;
  chatId?: string;
  messageId?: string;
  onFormSubmit?: (
    formId: string,
    values: Record<string, any>,
    chatId?: string,
    messageId?: string,
    processedForm?: any
  ) => void;
}

const DynamicForm: React.FC<DynamicFormProps> = ({ form, chatId, messageId, onFormSubmit }) => {
  if (form.type === 'score') {
    return <ScoreFormUI form={form} />;
  }
  return <NormalFormUI form={form} chatId={chatId} messageId={messageId} onFormSubmit={onFormSubmit} />;
};

export default DynamicForm; 