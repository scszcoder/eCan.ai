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
  // theme: 'light' | 'dark';
  // language: string;
  // 更多属性...
}