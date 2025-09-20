#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General Settings Entity - General settings entity class
Integrates hardware detection functionality, replacing duplicate code from ui_settings.py
"""

import os
from typing import List, Optional, Any, TYPE_CHECKING
from utils.logger_helper import logger_helper as logger
from gui.utils.hardware_detector import get_hardware_detector

if TYPE_CHECKING:
    from gui.manager.config_manager import ConfigManager

# Platform-specific imports are handled by hardware_detector module


class GeneralSettings:
    """
    General settings entity class - corresponds to settings.json file
    Integrates hardware detection functionality, replacing duplicate code from ui_settings.py
    """

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize general settings entity

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.settings_file = os.path.join(config_manager.user_data_path, 'resource/data/settings.json')

        # Load settings
        self._data = self._load_settings()

        # Hardware detection cache
        self._printers = []
        self._wifi_networks = []
        self._hardware_initialized = False

    def _load_settings(self) -> dict:
        """Load settings data with LLM providers initialization"""
        default_settings = {
            "schedule_mode": "auto",
            "debug_mode": False,
            "default_wifi": "",
            "default_printer": "",
            "display_resolution": "",
            "default_webdriver_path": "",
            "build_dom_tree_script_path": "",
            "new_orders_dir": "c:/ding_dan/",
            "local_user_db_host": "127.0.0.1",
            "local_user_db_port": "5080",
            "local_agent_db_host": "192.168.0.16",
            "local_agent_db_port": "6668",
            "lan_api_endpoint": "",
            "wan_api_endpoint": "",
            "ws_api_endpoint": "",
            "ws_api_host": "",
            "img_engine": "lan",
            "schedule_engine": "wan",
            "local_agent_ports": [3600, 3800],
            "browser_use_file_system_path": "",
            "local_server_port": "4668",
            "gui_flowgram_schema": "",
            "wan_api_key": "",
            "last_bots_file": "",
            "last_bots_file_time": 0,
            "last_order_file": "",
            "last_order_file_time": 0,
            "new_bots_file_path": "",
            "new_orders_path": "",
            "mids_forced_to_run": [],
            "default_llm": ""  # Default LLM provider to use
        }

        # 加载基础设置
        settings = self.config_manager.load_json(self.settings_file, default_settings)

        # 确保所有必需的字段都存在
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
                logger.info(f"Added missing field '{key}' with default value: {value}")

        return settings

    def save(self) -> bool:
        """Save settings"""
        return self.config_manager.save_json(self.settings_file, self._data)

    def reload(self):
        """Reload settings"""
        self._data = self._load_settings()

    @property
    def data(self) -> dict:
        """Get settings data dictionary (excluding LLM providers which are handled independently)"""
        data = self._data.copy()
        return data

    def set_field(self, key: str, value: any) -> None:
        """Set a specific field in the settings data"""
        self._data[key] = value

    def get_field(self, key: str, default=None) -> any:
        """Get a specific field from the settings data"""
        return self._data.get(key, default)


    # ==================== Basic Mode Settings ====================
    
    @property
    def schedule_mode(self) -> str:
        """Schedule mode: auto, manual, test"""
        return self._data.get("schedule_mode", "auto")

    @schedule_mode.setter
    def schedule_mode(self, value: str):
        self._data["schedule_mode"] = value

    @property
    def debug_mode(self) -> bool:
        """Debug mode"""
        return self._data.get("debug_mode", False)

    @debug_mode.setter
    def debug_mode(self, value: bool):
        self._data["debug_mode"] = value

    # ==================== Hardware Settings ====================
    
    @property
    def default_wifi(self) -> str:
        """Default WiFi"""
        return self._data.get("default_wifi", "")

    @default_wifi.setter
    def default_wifi(self, value: str):
        self._data["default_wifi"] = value

    @property
    def default_printer(self) -> str:
        """Default printer"""
        return self._data.get("default_printer", "")

    @default_printer.setter
    def default_printer(self, value: str):
        self._data["default_printer"] = value

    @property
    def display_resolution(self) -> str:
        """Display resolution"""
        return self._data.get("display_resolution", "")

    @display_resolution.setter
    def display_resolution(self, value: str):
        self._data["display_resolution"] = value

    # ==================== Path Settings ====================
    
    @property
    def default_webdriver_path(self) -> str:
        """WebDriver path"""
        return self._data.get("default_webdriver_path", "")

    @default_webdriver_path.setter
    def default_webdriver_path(self, value: str):
        self._data["default_webdriver_path"] = value

    @property
    def build_dom_tree_script_path(self) -> str:
        """DOM tree build script path"""
        return self._data.get("build_dom_tree_script_path", "")

    @build_dom_tree_script_path.setter
    def build_dom_tree_script_path(self, value: str):
        self._data["build_dom_tree_script_path"] = value

    @property
    def new_orders_dir(self) -> str:
        """New orders directory"""
        return self._data.get("new_orders_dir", "c:/ding_dan/")

    @new_orders_dir.setter
    def new_orders_dir(self, value: str):
        self._data["new_orders_dir"] = value

    @property
    def browser_use_file_system_path(self) -> str:
        """Browser file system path"""
        return self._data.get("browser_use_file_system_path", "")

    @browser_use_file_system_path.setter
    def browser_use_file_system_path(self, value: str):
        self._data["browser_use_file_system_path"] = value

    # ==================== Database Settings ====================
    
    @property
    def local_user_db_host(self) -> str:
        """Local user database host"""
        return self._data.get("local_user_db_host", "127.0.0.1")

    @local_user_db_host.setter
    def local_user_db_host(self, value: str):
        self._data["local_user_db_host"] = value

    @property
    def local_user_db_port(self) -> str:
        """Local user database port"""
        return self._data.get("local_user_db_port", "5080")

    @local_user_db_port.setter
    def local_user_db_port(self, value: str):
        self._data["local_user_db_port"] = value

    @property
    def local_agent_db_host(self) -> str:
        """Local agent database host"""
        return self._data.get("local_agent_db_host", "192.168.0.16")

    @local_agent_db_host.setter
    def local_agent_db_host(self, value: str):
        self._data["local_agent_db_host"] = value

    @property
    def local_agent_db_port(self) -> str:
        """Local agent database port"""
        return self._data.get("local_agent_db_port", "6668")

    @local_agent_db_port.setter
    def local_agent_db_port(self, value: str):
        self._data["local_agent_db_port"] = value

    # ==================== API Endpoint Settings ====================
    
    @property
    def lan_api_endpoint(self) -> str:
        """LAN API endpoint"""
        return self._data.get("lan_api_endpoint", "")

    @lan_api_endpoint.setter
    def lan_api_endpoint(self, value: str):
        self._data["lan_api_endpoint"] = value

    @property
    def wan_api_endpoint(self) -> str:
        """WAN API endpoint"""
        return self._data.get("wan_api_endpoint", "")

    @wan_api_endpoint.setter
    def wan_api_endpoint(self, value: str):
        self._data["wan_api_endpoint"] = value

    @property
    def ws_api_endpoint(self) -> str:
        """WebSocket API endpoint"""
        return self._data.get("ws_api_endpoint", "")

    @ws_api_endpoint.setter
    def ws_api_endpoint(self, value: str):
        self._data["ws_api_endpoint"] = value

    @property
    def ws_api_host(self) -> str:
        """WebSocket API endpoint"""
        return self._data.get("ws_api_host", "")

    @ws_api_host.setter
    def ws_api_host(self, value: str):
        self._data["ws_api_host"] = value

    @property
    def wan_api_key(self) -> str:
        """WAN API key"""
        return self._data.get("wan_api_key", "")

    @wan_api_key.setter
    def wan_api_key(self, value: str):
        self._data["wan_api_key"] = value

    # ==================== Engine Settings ====================
    
    @property
    def img_engine(self) -> str:
        """Image engine: lan, wan"""
        return self._data.get("img_engine", "lan")

    @img_engine.setter
    def img_engine(self, value: str):
        self._data["img_engine"] = value

    @property
    def schedule_engine(self) -> str:
        """Schedule engine: lan, wan"""
        return self._data.get("schedule_engine", "wan")

    @schedule_engine.setter
    def schedule_engine(self, value: str):
        self._data["schedule_engine"] = value

    # ==================== Port Settings ====================
    
    @property
    def local_agent_ports(self) -> List[int]:
        """Local agent port range"""
        return self._data.get("local_agent_ports", [3600, 3800])

    @local_agent_ports.setter
    def local_agent_ports(self, value: List[int]):
        self._data["local_agent_ports"] = value

    @property
    def local_server_port(self) -> str:
        """Local server port"""
        return self._data.get("local_server_port", "4668")

    @local_server_port.setter
    def local_server_port(self, value: str):
        self._data["local_server_port"] = value

    # ==================== Other Settings ====================

    @property
    def gui_flowgram_schema(self) -> str:
        """GUI flowchart schema"""
        return self._data.get("gui_flowgram_schema", "")

    @gui_flowgram_schema.setter
    def gui_flowgram_schema(self, value: str):
        self._data["gui_flowgram_schema"] = value

    # ==================== File Tracking Settings ====================
    
    @property
    def last_bots_file(self) -> str:
        """Last bots file"""
        return self._data.get("last_bots_file", "")

    @last_bots_file.setter
    def last_bots_file(self, value: str):
        self._data["last_bots_file"] = value

    @property
    def last_bots_file_time(self) -> int:
        """Last bots file time"""
        return self._data.get("last_bots_file_time", 0)

    @last_bots_file_time.setter
    def last_bots_file_time(self, value: int):
        self._data["last_bots_file_time"] = value

    @property
    def last_order_file(self) -> str:
        """Last order file"""
        return self._data.get("last_order_file", "")

    @last_order_file.setter
    def last_order_file(self, value: str):
        self._data["last_order_file"] = value

    @property
    def last_order_file_time(self) -> int:
        """Last order file time"""
        return self._data.get("last_order_file_time", 0)

    @last_order_file_time.setter
    def last_order_file_time(self, value: int):
        self._data["last_order_file_time"] = value

    @property
    def new_bots_file_path(self) -> str:
        """New bots file path"""
        return self._data.get("new_bots_file_path", "")

    @new_bots_file_path.setter
    def new_bots_file_path(self, value: str):
        self._data["new_bots_file_path"] = value

    @property
    def new_orders_path(self) -> str:
        """New orders path"""
        return self._data.get("new_orders_path", "")

    @new_orders_path.setter
    def new_orders_path(self, value: str):
        self._data["new_orders_path"] = value

    @property
    def mids_forced_to_run(self) -> List[str]:
        """MIDs forced to run"""
        return self._data.get("mids_forced_to_run", [])

    @mids_forced_to_run.setter
    def mids_forced_to_run(self, value: List[str]):
        self._data["mids_forced_to_run"] = value

    # ==================== LLM Settings ====================
    
    @property
    def default_llm(self) -> str:
        """Default LLM provider to use"""
        return self._data.get("default_llm", "")

    @default_llm.setter
    def default_llm(self, value: str):
        self._data["default_llm"] = value

    # ==================== Convenience Methods ====================
    
    def set_milan_server(self, ip: str, port: str = "8848"):
        """Set MILAN server"""
        self._data["lan_api_host"] = ip
        self._data["lan_api_port"] = port
        self._data["lan_api_endpoint"] = f"http://{ip}:{port}/graphql"

    def set_lan_db_server(self, ip: str, port: str = "5080"):
        """Set LAN database server"""
        self._data["local_user_db_host"] = ip
        self._data["local_user_db_port"] = port

    def get_all_data(self) -> dict:
        """Get all settings data"""
        return self._data.copy()

    def update_data(self, data: dict):
        """Batch update settings data"""
        self._data.update(data)

    # ==================== Hardware Detection Functions (integrated from ui_settings.py) ====================

    def _ensure_hardware_initialized(self):
        """Ensure hardware detection is initialized"""
        if not self._hardware_initialized:
            self.detect_hardware()
            self._hardware_initialized = True

    def detect_hardware(self):
        """Detect hardware devices"""
        try:
            detector = get_hardware_detector()

            # Detect all hardware
            hardware_info = detector.detect_all_hardware()
            logger.info(f"Hardware detection completed using shared detector: {hardware_info}")

            # Update internal state
            self._printers = hardware_info['printers']
            self._wifi_networks = hardware_info['wifi_networks']

            # Auto-set default WiFi
            if not self.default_wifi and hardware_info['current_wifi']:
                self.default_wifi = hardware_info['current_wifi']

            # Auto-set default printer
            printer_names = hardware_info['printer_names']
            if not self.default_printer and printer_names:
                # Set the first available printer as default
                self.default_printer = printer_names[0]
                logger.info(f"Auto-set default printer to: {self.default_printer}")

            logger.info("Hardware detection completed using shared detector")
        except Exception as e:
            logger.error(f"Error detecting hardware: {e}")

    # ==================== Hardware Access Interface (using shared hardware detector) ====================

    def get_printer_names(self) -> List[str]:
        """Get printer names list"""
        self._ensure_hardware_initialized()
        
        detector = get_hardware_detector()
        return detector.get_printer_names()

    def get_wifi_networks(self) -> List[str]:
        """Get WiFi networks list"""
        self._ensure_hardware_initialized()
        return self._wifi_networks.copy()

    def get_available_printers(self) -> List[Any]:
        """Get available printers list"""
        self._ensure_hardware_initialized()
        return self._printers.copy()

    def get_current_wifi(self) -> Optional[str]:
        """Get current connected WiFi"""
        detector = get_hardware_detector()
        return detector.get_current_wifi()

    def refresh_hardware(self):
        """Refresh hardware detection"""
        self._hardware_initialized = False
        self.detect_hardware()
