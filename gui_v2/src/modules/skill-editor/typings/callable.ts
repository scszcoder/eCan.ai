/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */


/**
 * Interface for defining a callable function
 * Definition可调用Function的Interface
 */
export interface CallableFunction {
  /**
   * Function ID
   * Function标识符
   */
  id?: string;
  /**
   * Function name
   * FunctionName
   */
  name: string;
  
  /**
   * Function description
   * FunctionDescription
   */
  desc: string;
  
  /**
   * Function parameters
   * FunctionParameter
   */
  params: {
    type: string;
    properties: Record<string, any>;
  };
  
  /**
   * Function return type
   * Function返回Type
   */
  returns: {
    type: string;
    properties: Record<string, any>;
  };
  
  /**
   * Function type: system or custom
   * FunctionType：System或Custom
   */
  type: 'system' | 'custom';
  
  /**
   * System function identifier (only for system functions)
   * SystemFunction标识符（仅Used forSystemFunction）
   */
  sysId?: string;
  
  /**
   * Custom implementation code (only for custom functions)
   * CustomImplementationCode（仅Used forCustomFunction）
   */
  code?: string;
  
  /**
   * Function implementation (deprecated, use sysId or code instead)
   * FunctionImplementation（已Deprecated，请使用 sysId 或 code）
   * @deprecated
   */
  impl?: string;
  
  /**
   * User ID (only for custom functions)
   * User ID（仅Used forCustomFunction）
   */
  userId?: string;
}

/**
 * Callable editor props
 * 可调用FunctionEdit器Property
 */
export interface CallableEditorProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
  onSave?: (value: CallableFunction) => void;
  onCancel?: () => void;
  mode?: 'edit' | 'create';
  systemFunctions?: CallableFunction[];
}

/**
 * Callable selector props
 * 可调用FunctionSelect器Property
 */
export interface CallableSelectorProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
  onAdd?: () => void;
  systemFunctions?: CallableFunction[];
  readonly?: boolean;
}

/**
 * Callable form field props
 * 可调用FunctionForm项Property
 */
export interface CallableFormFieldProps {
  value?: CallableFunction;
  onChange?: (value: CallableFunction) => void;
  systemFunctions?: CallableFunction[];
}

/**
 * Callable function filter type
 */
export interface CallableFilter {
  /** Text filter for searching in name, description, etc. */
  text?: string;
  /** Type filter: system or custom */
  type?: 'system' | 'custom';
} 

/**
 * Create a default callable function object.
 * 统一的新建FunctionDefaultValue
 */
export function createDefaultCallableFunction(): CallableFunction {
  return {
    name: '',
    desc: '',
    params: {
      type: 'object',
      properties: {},
    },
    returns: {
      type: 'object',
      properties: {},
    },
    type: 'custom',
  };
}