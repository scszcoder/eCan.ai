// 统一的类型定义文件

// LLM Provider 相关类型 - 匹配后端返回的数据结构
export interface LLMProvider {
  name: string;
  display_name: string;
  class_name: string;
  provider: string;
  description: string;
  documentation_url: string;
  is_local: boolean;
  base_url: string | null;
  default_model: string | null;
  api_key_env_vars: string[];
  supported_models: any[];

  // User preferences
  is_preferred: boolean;
  preferred_model: string | null;
  custom_parameters: any;
  api_key_configured: boolean;  // 使用后端的字段名

  // Validation status
  is_valid: boolean;
  validation_error: string | null;
  missing_env_vars: string[];
}

// Settings 主接口
export interface Settings {
  debug_mode: boolean;
  default_wifi: string;
  default_printer: string;
  display_resolution: string;
  default_webdriver_path: string;
  img_engine: string;
  local_user_db_host: string;
  local_user_db_port: string;
  local_agent_db_host: string;
  local_agent_db_port: string;
  local_agent_ports: number[];
  local_server_port: string;
  lan_api_endpoint: string;
  last_bots_file: string;
  last_bots_file_time: number;
  mids_forced_to_run: any[];
  new_orders_dir: string;
  new_bots_file_path: string;
  wan_api_endpoint: string;
  ws_api_endpoint: string;
  schedule_engine: string;
  schedule_mode: string;
  wan_api_key: string;
  browser_use_file_system_path: string;
  gui_flowgram_schema: string;
  build_dom_tree_script_path: string;
  last_order_file: string;
  last_order_file_time: number;
  new_orders_path: string;
  default_llm: string;  // 默认使用的LLM提供商
}

// 工具函数
export const maskApiKey = (apiKey: string | null): string => {
  if (!apiKey) return '';
  if (apiKey.length <= 10) return '*'.repeat(apiKey.length);
  return `${apiKey.substring(0, 6)}${'*'.repeat(10)}${apiKey.substring(apiKey.length - 4)}`;
};
