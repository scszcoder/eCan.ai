#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vehicle Monitor Manager - Data and Business Logic Handler
Handles vehicle monitoring operations without GUI components
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from gui.tool.MainGUITool import StaticResource
from utils.logger_helper import logger_helper as logger


class VehicleMonitorManager:
    """
    Vehicle Monitor Manager class that handles vehicle monitoring data and business logic
    without GUI components
    """
    
    def __init__(self, main_win, vehicle=None):
        """
        Initialize VehicleMonitorManager
        
        Args:
            main_win: Reference to main window/application
            vehicle: Optional specific vehicle to monitor
        """
        self.static_resource = StaticResource()
        self.mainwin = main_win
        self.vehicle = vehicle
        self.vehicles = self.mainwin.vehicles  # List of VEHICLE objects
        
        # Monitoring state
        self.is_monitoring = False
        self.selected_vehicle = None
        self.monitoring_progress = 0
        self.log_messages = []
        self.vehicle_status = {}
        
        # Command history
        self.command_history = []
        self.last_command_time = None
        
    def get_vehicles(self) -> List[Any]:
        """Get list of available vehicles"""
        return self.vehicles
        
    def get_selected_vehicle(self) -> Optional[Any]:
        """Get currently selected vehicle"""
        return self.selected_vehicle
        
    def set_selected_vehicle(self, vehicle: Any):
        """Set selected vehicle"""
        self.selected_vehicle = vehicle
        
    def get_vehicle_by_name(self, name: str) -> Optional[Any]:
        """Get vehicle by name"""
        for vehicle in self.vehicles:
            if vehicle.getName() == name:
                return vehicle
        return None
        
    def get_vehicle_by_ip(self, ip: str) -> Optional[Any]:
        """Get vehicle by IP address"""
        for vehicle in self.vehicles:
            if vehicle.getIP() == ip:
                return vehicle
        return None
        
    def get_vehicle_status(self, vehicle: Any) -> Dict[str, Any]:
        """
        Get status information for a vehicle
        
        Args:
            vehicle: Vehicle object
            
        Returns:
            Dictionary with vehicle status information
        """
        if not vehicle:
            return {}
            
        try:
            return {
                'name': vehicle.getName(),
                'ip': vehicle.getIP(),
                'os': vehicle.getOS(),
                'status': vehicle.getStatus() if hasattr(vehicle, 'getStatus') else 'unknown',
                'bot_count': len(vehicle.getBotIds()) if hasattr(vehicle, 'getBotIds') else 0,
                'capacity': vehicle.CAP if hasattr(vehicle, 'CAP') else 0,
                'last_seen': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting vehicle status: {e}")
            return {}
            
    def get_all_vehicles_status(self) -> List[Dict[str, Any]]:
        """Get status for all vehicles"""
        status_list = []
        for vehicle in self.vehicles:
            status = self.get_vehicle_status(vehicle)
            if status:
                status_list.append(status)
        return status_list
        
    def start_monitoring(self, vehicle: Any = None):
        """
        Start monitoring a vehicle
        
        Args:
            vehicle: Vehicle to monitor, uses selected vehicle if None
        """
        if vehicle:
            self.selected_vehicle = vehicle
        elif not self.selected_vehicle:
            logger.warning("No vehicle selected for monitoring")
            return False
            
        self.is_monitoring = True
        self.monitoring_progress = 0
        logger.info(f"Started monitoring vehicle: {self.selected_vehicle.getName()}")
        return True
        
    def stop_monitoring(self):
        """Stop monitoring current vehicle"""
        if self.selected_vehicle:
            logger.info(f"Stopped monitoring vehicle: {self.selected_vehicle.getName()}")
        self.is_monitoring = False
        self.monitoring_progress = 0
        
    def is_vehicle_monitoring(self) -> bool:
        """Check if vehicle monitoring is active"""
        return self.is_monitoring
        
    def get_monitoring_progress(self) -> int:
        """Get current monitoring progress (0-100)"""
        return self.monitoring_progress
        
    def update_monitoring_progress(self, progress: int):
        """
        Update monitoring progress
        
        Args:
            progress: Progress value (0-100)
        """
        if 0 <= progress <= 100:
            self.monitoring_progress = progress
            
    def add_log_message(self, message: str, message_type: str = "info"):
        """
        Add a log message
        
        Args:
            message: Log message content
            message_type: Type of message (info, warn, error, debug)
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'type': message_type,
            'vehicle': self.selected_vehicle.getName() if self.selected_vehicle else 'unknown'
        }
        self.log_messages.append(log_entry)
        
        # Keep only last 1000 messages to prevent memory issues
        if len(self.log_messages) > 1000:
            self.log_messages = self.log_messages[-1000:]
            
    def get_log_messages(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get log messages
        
        Args:
            limit: Maximum number of messages to return
            
        Returns:
            List of log messages
        """
        if limit:
            return self.log_messages[-limit:]
        return self.log_messages.copy()
        
    def clear_log_messages(self):
        """Clear all log messages"""
        self.log_messages.clear()
        
    def send_command(self, command: str, vehicle: Any = None) -> bool:
        """
        Send command to a vehicle
        
        Args:
            command: Command to send
            vehicle: Target vehicle, uses selected vehicle if None
            
        Returns:
            True if command sent successfully, False otherwise
        """
        target_vehicle = vehicle or self.selected_vehicle
        if not target_vehicle:
            logger.warning("No vehicle selected for command")
            return False
            
        try:
            # Record command in history
            command_entry = {
                'timestamp': datetime.now().isoformat(),
                'command': command,
                'vehicle': target_vehicle.getName(),
                'status': 'sent'
            }
            self.command_history.append(command_entry)
            self.last_command_time = datetime.now()
            
            # TODO: Implement actual command sending logic
            logger.info(f"Command sent to {target_vehicle.getName()}: {command}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False
            
    def get_command_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get command history
        
        Args:
            limit: Maximum number of commands to return
            
        Returns:
            List of command history entries
        """
        if limit:
            return self.command_history[-limit:]
        return self.command_history.copy()
        
    def clear_command_history(self):
        """Clear command history"""
        self.command_history.clear()
        
    def send_pause_command(self) -> bool:
        """Send pause command to selected vehicle"""
        try:
            self.mainwin.wan_rpa_ctrl("halt missions")
            self.add_log_message("Pause command sent", "info")
            return True
        except Exception as e:
            logger.error(f"Error sending pause command: {e}")
            return False
            
    def send_resume_command(self) -> bool:
        """Send resume command to selected vehicle"""
        try:
            self.mainwin.wan_rpa_ctrl("resume missions")
            self.add_log_message("Resume command sent", "info")
            return True
        except Exception as e:
            logger.error(f"Error sending resume command: {e}")
            return False
            
    def send_terminate_command(self) -> bool:
        """Send terminate command to selected vehicle"""
        try:
            self.mainwin.wan_rpa_ctrl("cancel missions")
            self.add_log_message("Terminate command sent", "info")
            return True
        except Exception as e:
            logger.error(f"Error sending terminate command: {e}")
            return False
            
    def send_report_command(self) -> bool:
        """Send report command to selected vehicle"""
        try:
            self.mainwin.wan_rpa_ctrl("show status")
            self.add_log_message("Report command sent", "info")
            return True
        except Exception as e:
            logger.error(f"Error sending report command: {e}")
            return False
            
    def process_log_message(self, message: str) -> Dict[str, Any]:
        """
        Process and format log message
        
        Args:
            message: Raw log message
            
        Returns:
            Processed log message data
        """
        try:
            if isinstance(message, str):
                msg_data = json.loads(message)
            else:
                msg_data = message
                
            processed_msg = self.format_displayable_message(msg_data)
            return processed_msg
            
        except Exception as e:
            logger.error(f"Error processing log message: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'content': str(message),
                'type': 'error',
                'error': str(e)
            }
            
    def format_displayable_message(self, msg_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format message for display
        
        Args:
            msg_data: Raw message data
            
        Returns:
            Formatted message data
        """
        try:
            log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Determine text color based on message type
            text_color = "color:#608F80;"  # Default color
            if "error" in str(msg_data.get("contents", "")):
                text_color = "color:#ff0000;"
            elif "warn" in str(msg_data.get("contents", "")):
                text_color = "color:#ff8000;"
            elif "info" in str(msg_data.get("contents", "")):
                text_color = "color:#004800;"
            elif "debug" in str(msg_data.get("contents", "")):
                text_color = "color:#90ffff;"
                
            if msg_data.get('type') == "logs":
                text_color = "color:#6000FF;"
                logger.debug("Processing log message...")
                
                # Decrypt message if needed
                contents = msg_data.get('contents', '').replace('\\"', '"')
                if hasattr(self.mainwin, 'generate_key_from_string') and hasattr(self.mainwin, 'decrypt_string'):
                    try:
                        ek = self.mainwin.generate_key_from_string(self.mainwin.main_key)
                        decrypted_msg = self.mainwin.decrypt_string(ek, contents)
                        processed_content = decrypted_msg
                    except Exception as e:
                        logger.error(f"Error decrypting message: {e}")
                        processed_content = contents
                else:
                    processed_content = contents
            else:
                # Handle other message types
                contents = msg_data.get('contents', '').replace('\\"', '"')
                try:
                    contents_json = json.loads(contents)
                    if "vehiclesInfo" in contents_json:
                        vinfo = contents_json["vehiclesInfo"]
                        vehicle_string = ""
                        for v in vinfo:
                            vehicle_string += f"{v.get('vname', '')}-{v.get('vehicles_status', '')}; "
                        processed_content = vehicle_string
                    else:
                        processed_content = contents
                except Exception as e:
                    logger.error(f"Error parsing message contents: {e}")
                    processed_content = contents
                    
            return {
                'timestamp': log_time,
                'content': processed_content,
                'color': text_color,
                'type': msg_data.get('type', 'unknown'),
                'raw_data': msg_data
            }
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}")
            return {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'content': f"Error formatting message: {str(e)}",
                'color': "color:#ff0000;",
                'type': 'error',
                'raw_data': msg_data
            }
            
    def get_vehicle_statistics(self) -> Dict[str, Any]:
        """Get comprehensive vehicle statistics"""
        try:
            total_vehicles = len(self.vehicles)
            total_bots = 0
            vehicles_by_os = {}
            vehicles_by_status = {}
            
            for vehicle in self.vehicles:
                # Count bots
                if hasattr(vehicle, 'getBotIds'):
                    bot_count = len(vehicle.getBotIds())
                    total_bots += bot_count
                    
                # Count by OS
                os_type = vehicle.getOS() if hasattr(vehicle, 'getOS') else 'unknown'
                vehicles_by_os[os_type] = vehicles_by_os.get(os_type, 0) + 1
                
                # Count by status
                status = vehicle.getStatus() if hasattr(vehicle, 'getStatus') else 'unknown'
                vehicles_by_status[status] = vehicles_by_status.get(status, 0) + 1
                
            return {
                'total_vehicles': total_vehicles,
                'total_bots': total_bots,
                'vehicles_by_os': vehicles_by_os,
                'vehicles_by_status': vehicles_by_status,
                'monitoring_active': self.is_monitoring,
                'selected_vehicle': self.selected_vehicle.getName() if self.selected_vehicle else None,
                'log_message_count': len(self.log_messages),
                'command_count': len(self.command_history)
            }
            
        except Exception as e:
            logger.error(f"Error getting vehicle statistics: {e}")
            return {}
            
    def export_monitoring_data(self, filepath: str) -> bool:
        """
        Export monitoring data to JSON file
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            True if exported successfully, False otherwise
        """
        try:
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'vehicle_status': self.get_all_vehicles_status(),
                'log_messages': self.log_messages,
                'command_history': self.command_history,
                'statistics': self.get_vehicle_statistics()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Monitoring data exported to: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting monitoring data: {e}")
            return False
            
    def cleanup(self):
        """Clean up resources"""
        try:
            self.stop_monitoring()
            self.clear_log_messages()
            self.clear_command_history()
            logger.info("VehicleMonitorManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")