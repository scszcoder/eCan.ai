/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */


/**
 * Interface for defining a callable function
 * 定义可调用函数的接口
 */
export interface CallableFunction {
  /**
   * Function ID
   * 函数标识符
   */
  id?: string;
  /**
   * Function name
   * 函数名称
   */
  name: string;
  
  /**
   * Function description
   * 函数描述
   */
  desc: string;
  
  /**
   * Function parameters
   * 函数参数
   */
  params: {
    type: string;
    properties: Record<string, any>;
  };
  
  /**
   * Function return type
   * 函数返回类型
   */
  returns: {
    type: string;
    properties: Record<string, any>;
  };
  
  /**
   * Function type: system or custom
   * 函数类型：系统或自定义
   */
  type: 'system' | 'custom';
  
  /**
   * System function identifier (only for system functions)
   * 系统函数标识符（仅用于系统函数）
   */
  sysId?: string;
  
  /**
   * Custom implementation code (only for custom functions)
   * 自定义实现代码（仅用于自定义函数）
   */
  code?: string;
  
  /**
   * Function implementation (deprecated, use sysId or code instead)
   * 函数实现（已废弃，请使用 sysId 或 code）
   * @deprecated
   */
  impl?: string;
  
  /**
   * User ID (only for custom functions)
   * 用户 ID（仅用于自定义函数）
   */
  userId?: string;
}

/**
 * Callable editor props
 * 可调用函数编辑器属性
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
 * 可调用函数选择器属性
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
 * 可调用函数表单项属性
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
 * 统一的新建函数默认值
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