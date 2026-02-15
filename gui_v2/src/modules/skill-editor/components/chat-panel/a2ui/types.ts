/**
 * A2UI Types for Skill Editor
 * 
 * These types define the A2UI message format for generating
 * dynamic forms and UI surfaces from LLM responses.
 */

// ============================================================
// A2UI Protocol Message Types (v0.10)
// ============================================================

/** Theme configuration for a surface */
export interface A2UITheme {
  primaryColor?: string;
  font?: string;
  logoUrl?: string;
}

/** Create surface message */
export interface A2UICreateSurfaceMessage {
  version: 'v0.10';
  createSurface: {
    surfaceId: string;
    catalogId: string;
    theme?: A2UITheme;
    sendDataModel?: boolean;
  };
}

/** Component base properties */
export interface A2UIComponentBase {
  id: string;
  component: string;
  weight?: number;
  accessibility?: {
    label?: string;
    description?: string;
  };
}

/** Text component */
export interface A2UITextComponent extends A2UIComponentBase {
  component: 'Text';
  text: string | { path: string };
  variant?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'caption' | 'body';
}

/** Button component */
export interface A2UIButtonComponent extends A2UIComponentBase {
  component: 'Button';
  child: string; // ComponentId reference
  variant?: 'primary' | 'borderless';
  action: A2UIAction;
}

/** TextField component */
export interface A2UITextFieldComponent extends A2UIComponentBase {
  component: 'TextField';
  label: string | { path: string };
  value?: string | { path: string };
  variant?: 'longText' | 'number' | 'shortText' | 'obscured';
  checkRules?: A2UICheckRule[];
}

/** CheckBox component */
export interface A2UICheckBoxComponent extends A2UIComponentBase {
  component: 'CheckBox';
  label: string | { path: string };
  value: boolean | { path: string };
}

/** ChoicePicker component (for multiple choice questions) */
export interface A2UIChoicePickerComponent extends A2UIComponentBase {
  component: 'ChoicePicker';
  label?: string | { path: string };
  variant?: 'multipleSelection' | 'mutuallyExclusive';
  options: Array<{
    label: string | { path: string };
    value: string;
  }>;
  value: string[] | { path: string };
  checkRules?: A2UICheckRule[];
}

/** Column layout component */
export interface A2UIColumnComponent extends A2UIComponentBase {
  component: 'Column';
  children: string[] | { componentId: string; path: string };
  justify?: 'start' | 'center' | 'end' | 'spaceBetween' | 'spaceAround' | 'spaceEvenly' | 'stretch';
  align?: 'start' | 'center' | 'end' | 'stretch';
}

/** Row layout component */
export interface A2UIRowComponent extends A2UIComponentBase {
  component: 'Row';
  children: string[] | { componentId: string; path: string };
  justify?: 'start' | 'center' | 'end' | 'spaceBetween' | 'spaceAround' | 'spaceEvenly' | 'stretch';
  align?: 'start' | 'center' | 'end' | 'stretch';
}

/** Card component */
export interface A2UICardComponent extends A2UIComponentBase {
  component: 'Card';
  child: string; // ComponentId reference
}

/** Divider component */
export interface A2UIDividerComponent extends A2UIComponentBase {
  component: 'Divider';
  axis?: 'horizontal' | 'vertical';
}

/** Icon component */
export interface A2UIIconComponent extends A2UIComponentBase {
  component: 'Icon';
  name: string;
}

/** Union of all component types */
export type A2UIComponent =
  | A2UITextComponent
  | A2UIButtonComponent
  | A2UITextFieldComponent
  | A2UICheckBoxComponent
  | A2UIChoicePickerComponent
  | A2UIColumnComponent
  | A2UIRowComponent
  | A2UICardComponent
  | A2UIDividerComponent
  | A2UIIconComponent;

/** Action definition */
export interface A2UIAction {
  name: string;
  context?: Array<{
    key: string;
    value: string | number | boolean | { path: string };
  }>;
}

/** Check rule for validation */
export interface A2UICheckRule {
  condition: boolean | { call: string; args: Record<string, unknown> };
  message: string;
}

/** Update components message */
export interface A2UIUpdateComponentsMessage {
  version: 'v0.10';
  updateComponents: {
    surfaceId: string;
    components: A2UIComponent[];
  };
}

/** Update data model message */
export interface A2UIUpdateDataModelMessage {
  version: 'v0.10';
  updateDataModel: {
    surfaceId: string;
    path?: string;
    value?: unknown;
  };
}

/** Delete surface message */
export interface A2UIDeleteSurfaceMessage {
  version: 'v0.10';
  deleteSurface: {
    surfaceId: string;
  };
}

/** Union of all server-to-client message types */
export type A2UIServerMessage =
  | A2UICreateSurfaceMessage
  | A2UIUpdateComponentsMessage
  | A2UIUpdateDataModelMessage
  | A2UIDeleteSurfaceMessage;

// ============================================================
// Client Event Types
// ============================================================

/** User action event sent from client to server */
export interface A2UIUserAction {
  userAction: {
    name: string;
    surfaceId: string;
    sourceComponentId: string;
    timestamp: string;
    context?: Record<string, unknown>;
  };
}

// ============================================================
// Form-specific Types (for ClarificationQuestion integration)
// ============================================================

/** A2UI-formatted clarification form response from LLM */
export interface A2UIClarificationForm {
  /** Surface ID for this form */
  surfaceId: string;
  /** A2UI messages to create and populate the surface */
  messages: A2UIServerMessage[];
  /** Data model for the form */
  dataModel: Record<string, unknown>;
}

/** Standard catalog ID for A2UI */
export const A2UI_STANDARD_CATALOG = 'https://a2ui.org/specification/v0_10/standard_catalog.json';
