#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Platoon Manager - Data and Business Logic Handler
Handles platoon operations without GUI components
"""

from typing import List, Any
from utils.logger_helper import logger_helper as logger


class PlatoonManager:
    """
    Platoon Manager class that handles platoon data and business logic
    without GUI components
    """
    
    def __init__(self, parent, entrance="msg"):
        """
        Initialize PlatoonManager
        
        Args:
            parent: Reference to parent application
            entrance: Entry mode ("msg", "conn", "init")
        """
        self.parent = parent
        self.entrance = entrance
        
        # Platoon data
        self.platoon_data = {}
        self.vehicle_stats = {}
        self.mission_status = {}
        self.platoon_commands = []
        
        # Vehicle tracking
        self.vehicles = []
        self.field_links = []
        
        # Initialize platoon data
        self._init_platoon_data()
        
    def _init_platoon_data(self):
        """Initialize platoon data from parent"""
        try:
            if hasattr(self.parent, 'vehicles'):
                self.vehicles = self.parent.vehicles.copy()
                
            if hasattr(self.parent, 'fieldLinks'):
                self.field_links = self.parent.fieldLinks.copy()
                
            logger.info("Platoon data initialized")
            
        except Exception as e:
            logger.error(f"Error initializing platoon data: {e}")
            
    def get_vehicles(self) -> List[Any]:
        """Get list of vehicles in platoon"""
        return self.vehicles.copy()
        
    def add_vehicle(self, vehicle: Any) -> bool:
        """Add a vehicle to the platoon"""
        try:
            if vehicle not in self.vehicles:
                self.vehicles.append(vehicle)
                logger.info(f"Vehicle added to platoon: {vehicle.getName()}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding vehicle: {e}")
            return False
            
    def send_platoon_command(self, command: str, vehicle_indices: List[int], mission_ids: List[int]) -> bool:
        """Send command to platoon vehicles"""
        try:
            if hasattr(self.parent, 'sendPlatoonCommand'):
                self.parent.sendPlatoonCommand(command, vehicle_indices, mission_ids)
            logger.info(f"Platoon command sent: {command}")
            return True
        except Exception as e:
            logger.error(f"Error sending platoon command: {e}")
            return False


# Legacy class names for backward compatibility
class PlatoonListView:
    """Legacy PlatoonListView class - now just a placeholder for compatibility"""
    
    def __init__(self, parent):
        self.parent = parent
        self.selected_row = None


class PLATOON:
    """Legacy PLATOON class - now just a data container"""
    
    def __init__(self, ip: str, hostname: str, env: str, homepath: str):
        self.name = hostname
        self.ip = ip
        self.env = env
        self.homepath = homepath
        
    def getData(self) -> tuple:
        return self.name, self.ip, self.env

