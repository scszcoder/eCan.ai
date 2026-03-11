/**
 * A2UI Converter - Transforms ClarificationQuestion to A2UI messages
 * 
 * This converts the existing clarification question format to A2UI protocol
 * messages that can be rendered by the A2UI Lit renderer.
 */

import type { ClarificationQuestion } from '../../../types/skill-editor-chat.types';
import type {
  A2UIServerMessage,
  A2UICreateSurfaceMessage,
  A2UIUpdateComponentsMessage,
  A2UIUpdateDataModelMessage,
  A2UIComponent,
  A2UITextComponent,
  A2UITextFieldComponent,
  A2UIChoicePickerComponent,
  A2UIButtonComponent,
  A2UIColumnComponent,
  A2UIRowComponent,
  A2UIDividerComponent,
} from './types';
import { A2UI_STANDARD_CATALOG } from './types';

/**
 * Generate a unique surface ID for a clarification form
 */
export function generateSurfaceId(prefix = 'clarification'): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Convert ClarificationQuestion array to A2UI messages
 * 
 * Creates a complete A2UI surface with:
 * - Header text
 * - Questions with ChoicePicker components
 * - Submit/Cancel buttons
 */
export function clarificationToA2UI(
  questions: ClarificationQuestion[],
  surfaceId?: string
): {
  surfaceId: string;
  messages: A2UIServerMessage[];
  initialDataModel: Record<string, string[]>;
} {
  const sid = surfaceId || generateSurfaceId();
  const components: A2UIComponent[] = [];
  const initialDataModel: Record<string, string[]> = {};
  const freeformInitial: Record<string, string> = {};
  const freeformQuestionIds: string[] = [];
  const questionComponentIds: string[] = [];

  // 1. Header text
  const headerText: A2UITextComponent = {
    id: 'header-text',
    component: 'Text',
    text: '🤔 I have a few questions to better understand your requirements:',
    variant: 'h4',
  };
  components.push(headerText);

  // 2. Divider after header
  const headerDivider: A2UIDividerComponent = {
    id: 'header-divider',
    component: 'Divider',
    axis: 'horizontal',
  };
  components.push(headerDivider);

  // 3. Create components for each question
  questions.forEach((q, index) => {
    const questionId = `q_${q.id}`;
    const questionContainerId = `container_${q.id}`;
    
    // Initialize data model for this question
    initialDataModel[q.id] = [];

    // Question text
    const questionText: A2UITextComponent = {
      id: `text_${q.id}`,
      component: 'Text',
      text: `${index + 1}. ${q.question}`,
      variant: 'body',
    };
    components.push(questionText);

    // Context text if provided
    if (q.context) {
      const contextText: A2UITextComponent = {
        id: `context_${q.id}`,
        component: 'Text',
        text: q.context,
        variant: 'caption',
      };
      components.push(contextText);
    }

    // Choice picker for this question
    const choicePicker: A2UIChoicePickerComponent = {
      id: questionId,
      component: 'ChoicePicker',
      variant: q.allow_multiple ? 'multipleSelection' : 'mutuallyExclusive',
      options: q.choices.map(c => ({
        label: c.description ? `${c.label} - ${c.description}` : c.label,
        value: c.id,
      })),
      value: { path: `/answers/${q.id}` },
      checkRules: [
        {
          condition: {
            call: 'required',
            args: { value: { path: `/answers/${q.id}` } },
          },
          message: 'Please select an option',
        },
      ],
    };
    components.push(choicePicker);

    // Check if any choice has allow_freeform ("Other"-style option)
    const hasFreeform = q.choices.some(c => c.allow_freeform);
    if (hasFreeform) {
      const freeformField: A2UITextFieldComponent = {
        id: `freeform_${q.id}`,
        component: 'TextField',
        label: 'If you selected "Other", please specify:',
        value: { path: `/freeform/${q.id}` },
        variant: 'shortText',
      };
      components.push(freeformField);
      freeformInitial[q.id] = '';
      freeformQuestionIds.push(q.id);
    }

    // Column container for this question
    const columnChildren = q.context
      ? [`text_${q.id}`, `context_${q.id}`, questionId]
      : [`text_${q.id}`, questionId];
    if (hasFreeform) columnChildren.push(`freeform_${q.id}`);

    const questionContainer: A2UIColumnComponent = {
      id: questionContainerId,
      component: 'Column',
      children: columnChildren,
      align: 'stretch',
    };
    components.push(questionContainer);

    questionComponentIds.push(questionContainerId);
  });

  // 4. Submit button text
  const submitButtonText: A2UITextComponent = {
    id: 'submit-btn-text',
    component: 'Text',
    text: 'Submit Answers',
  };
  components.push(submitButtonText);

  // 5. Submit button
  const submitButton: A2UIButtonComponent = {
    id: 'submit-btn',
    component: 'Button',
    variant: 'primary',
    child: 'submit-btn-text',
    action: {
      name: 'submit_clarification',
      context: [
        ...questions.map(q => ({
          key: q.id,
          value: { path: `/answers/${q.id}` },
        })),
        ...freeformQuestionIds.map(qId => ({
          key: `freeform_${qId}`,
          value: { path: `/freeform/${qId}` },
        })),
      ],
    },
  };
  components.push(submitButton);

  // 6. Cancel button text
  const cancelButtonText: A2UITextComponent = {
    id: 'cancel-btn-text',
    component: 'Text',
    text: 'Cancel',
  };
  components.push(cancelButtonText);

  // 7. Cancel button
  const cancelButton: A2UIButtonComponent = {
    id: 'cancel-btn',
    component: 'Button',
    variant: 'borderless',
    child: 'cancel-btn-text',
    action: {
      name: 'cancel_clarification',
    },
  };
  components.push(cancelButton);

  // 8. Button row
  const buttonRow: A2UIRowComponent = {
    id: 'button-row',
    component: 'Row',
    children: ['submit-btn', 'cancel-btn'],
    justify: 'end',
    align: 'center',
  };
  components.push(buttonRow);

  // 9. Root column
  const rootColumn: A2UIColumnComponent = {
    id: 'root',
    component: 'Column',
    children: ['header-text', 'header-divider', ...questionComponentIds, 'button-row'],
    align: 'stretch',
  };
  components.push(rootColumn);

  // Create the A2UI messages
  const createSurface: A2UICreateSurfaceMessage = {
    version: 'v0.10',
    createSurface: {
      surfaceId: sid,
      catalogId: A2UI_STANDARD_CATALOG,
      theme: {
        primaryColor: '#3b82f6', // Blue accent matching skill editor
      },
      sendDataModel: true,
    },
  };

  const updateComponents: A2UIUpdateComponentsMessage = {
    version: 'v0.10',
    updateComponents: {
      surfaceId: sid,
      components,
    },
  };

  const updateDataModel: A2UIUpdateDataModelMessage = {
    version: 'v0.10',
    updateDataModel: {
      surfaceId: sid,
      path: '/answers',
      value: initialDataModel,
    },
  };

  const messages: A2UIServerMessage[] = [createSurface, updateComponents, updateDataModel];

  // Initialize freeform data model for "Other" text fields
  if (Object.keys(freeformInitial).length > 0) {
    const updateFreeformModel: A2UIUpdateDataModelMessage = {
      version: 'v0.10',
      updateDataModel: {
        surfaceId: sid,
        path: '/freeform',
        value: freeformInitial,
      },
    };
    messages.push(updateFreeformModel);
  }

  return {
    surfaceId: sid,
    messages,
    initialDataModel,
  };
}

/**
 * Convert A2UI action context to ClarificationResponse answers format.
 *
 * Freeform text values (from "Other" text fields) are passed through
 * as `freeform_<questionId>` keys so the backend can merge them.
 */
export function extractAnswersFromA2UIAction(
  context: Record<string, unknown>
): Record<string, string[]> {
  const answers: Record<string, string[]> = {};
  const freeformTexts: Record<string, string> = {};

  for (const [key, value] of Object.entries(context)) {
    if (key.startsWith('freeform_')) {
      // Collect freeform text separately first
      const text = typeof value === 'string' ? value.trim() : '';
      if (text) {
        const questionId = key.slice('freeform_'.length);
        freeformTexts[questionId] = text;
      }
    } else if (Array.isArray(value)) {
      answers[key] = value.map(v => String(v));
    } else if (typeof value === 'string') {
      answers[key] = [value];
    }
  }

  // Merge freeform text into answers: append ` (Other: <text>)` detail
  // and keep freeform_* keys for backend consumption
  for (const [qId, text] of Object.entries(freeformTexts)) {
    answers[`freeform_${qId}`] = [text];
  }

  return answers;
}

/**
 * Check if a message appears to be A2UI format
 */
export function isA2UIMessage(obj: unknown): obj is A2UIServerMessage {
  if (!obj || typeof obj !== 'object') return false;
  const msg = obj as Record<string, unknown>;
  return (
    msg.version === 'v0.10' &&
    ('createSurface' in msg ||
      'updateComponents' in msg ||
      'updateDataModel' in msg ||
      'deleteSurface' in msg)
  );
}

/**
 * Parse A2UI messages from LLM response
 * Can handle both single message and array of messages
 */
export function parseA2UIResponse(response: unknown): A2UIServerMessage[] {
  if (Array.isArray(response)) {
    return response.filter(isA2UIMessage);
  }
  if (isA2UIMessage(response)) {
    return [response];
  }
  return [];
}
