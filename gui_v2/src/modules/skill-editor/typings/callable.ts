import { JsonSchema } from './json-schema';

/**
 * Interface for defining a callable function
 * 定义可调用函数的接口
 */
export interface CallableFunction {
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
   * Function parameters schema
   * 函数参数模式
   */
  params: JsonSchema;
  
  /**
   * Function return type schema
   * 函数返回类型模式
   */
  returns: JsonSchema;
  
  /**
   * Function implementation type
   * 函数实现类型
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
  value?: string;
  onChange?: (value: string) => void;
  onEdit?: (value: CallableFunction) => void;
  onAdd?: () => void;
  systemFunctions?: CallableFunction[];
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