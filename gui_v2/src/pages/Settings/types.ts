// 统一的TypeDefinition文件

// LLM Provider 相关Type - 匹配Backend返回的Data结构
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
  api_key_configured: boolean;  // 使用Backend的Field名

  // Validation status
  is_valid: boolean;
  validation_error: string | null;
  missing_env_vars: string[];
}

// Settings 主Interface - 与settings_template.json对齐
export interface Settings {
  // General
  schedule_mode: string;
  debug_mode: boolean;
  
  // Hardware
  default_wifi: string;
  default_printer: string;
  display_resolution: string;
  
  // Paths
  default_webdriver_path: string;
  build_dom_tree_script_path: string;
  new_orders_dir: string;
  new_bots_file_path: string;
  new_orders_path: string;
  browser_use_file_system_path: string;
  browser_use_download_dir: string;
  browser_use_user_data_dir: string;
  gui_flowgram_schema: string;
  
  // Local DB
  local_user_db_host: string;
  local_user_db_port: string;
  local_agent_db_host: string;
  local_agent_db_port: string;
  local_agent_ports: number[];
  local_server_port: string;
  
  // API Endpoints
  lan_api_endpoint: string;
  wan_api_endpoint: string;
  ws_api_endpoint: string;
  ws_api_host: string;
  ecan_cloud_searcher_url: string;
  
  // API Keys
  wan_api_key: string;
  ocr_api_key: string;
  
  // Engines
  network_api_engine: string;
  schedule_engine: string;
  
  // OCR
  ocr_api_endpoint: string;
  
  // LLM
  default_llm: string;
  default_llm_model: string;
  
  // Embedding
  default_embedding: string;
  default_embedding_model: string;
  
  // Rerank
  default_rerank: string;
  default_rerank_model: string;
  
  // Skill
  skill_use_git: boolean;
  
  // Internal
  last_bots_file: string;
  last_bots_file_time: number;
  last_order_file: string;
  last_order_file_time: number;
  mids_forced_to_run: any[];
}

// ToolFunction
export const maskApiKey = (apiKey: string | null): string => {
  if (!apiKey) return '';
  if (apiKey.length <= 10) return '*'.repeat(apiKey.length);
  return `${apiKey.substring(0, 6)}${'*'.repeat(10)}${apiKey.substring(apiKey.length - 4)}`;
};
