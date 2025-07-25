// 表单类型定义
import { FormField as IFormField } from '../../types/chat';

export interface ScoreForm {
  id: string;
  type: 'score';
  title?: string;
  components: any[];
}

export interface NormalForm {
  id: string;
  type: 'normal';
  title?: string;
  fields: IFormField[];
  submit_text?: string;
}

export type AnyForm = NormalForm | ScoreForm;

export interface DynamicFormBaseProps {
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

export interface DynamicScoreFormProps extends DynamicFormBaseProps {
  form: ScoreForm;
}

export interface DynamicNormalFormProps extends DynamicFormBaseProps {
  form: NormalForm;
} 