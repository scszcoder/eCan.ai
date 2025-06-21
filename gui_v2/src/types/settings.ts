// 系统设置相关的类型定义
export interface Settings {
  api_api_port: string;
  debug_mode: boolean;
  default_wifi: string;
  default_printer: string;
  display_resolution: string;
  default_webdriver: string;
  img_engine: string;
  localUserDB_host: string;
  localUserDB_port: string;
  localAgentDB_host: string;
  localAgentDB_port: string;
  localAgent_ports: number[];
  local_server_port: string;
  lan_api_endpoint: string;
  lan_api_host: string;
  last_bots_file: string;
  last_bots_file_time: string;
  mids_forced_to_run: any[];
  new_orders_dir: string;
  new_bots_file_path: string;
  wan_api_endpoint: string;
  ws_api_endpoint: string;
  schedule_engine: string;
  schedule_mode: string;
  theme: 'light' | 'dark';
  language: string;
} 