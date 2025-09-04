#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Manager - Data and Business Logic Handler
Handles bot management operations without GUI components
"""

import json
from typing import List, Dict, Any, Optional

from bot.ebbot import EBBOT
from common.models import VehicleModel
from gui.tool.MainGUITool import StaticResource


class BotManager:
    """
    Bot Manager class that handles bot data and business logic
    without GUI components
    """
    
    def __init__(self, main_win):
        """
        Initialize BotManager
        
        Args:
            main_win: Reference to main window/application
        """
        self.main_win = main_win
        self.newBot = EBBOT(main_win)
        self.vehicleArray = self.findAllVehicle()
        self.homepath = self.main_win.homepath
        
        # Bot data
        self.bot_id = ""
        self.icon_path = ""
        self.pseudo_first_name = ""
        self.pseudo_last_name = ""
        self.pseudo_nick_name = ""
        self.location_city = ""
        self.location_state = ""
        self.age = ""
        self.vehicle = ""
        self.gender = "Unknown"
        self.birthday = ""
        
        # Interest settings
        self.selected_interest_platform = "Amazon"
        self.selected_interest_main_category = "any"
        self.selected_interest_sub_category1 = "any"
        self.selected_interest_sub_category2 = "any"
        self.selected_interest_sub_category3 = "any"
        self.selected_interest_sub_category4 = "any"
        self.selected_interest_sub_category5 = "any"
        
        # Role settings
        self.selected_role_platform = "Amazon"
        self.selected_role_level = "Green"
        self.selected_role_role = "Buyer"
        
        # Mode
        self.mode = "new"  # "new" or "update"
        
        # Data collections
        self.roles = []
        self.interests = []
        
        # Static resources
        self.static_resource = StaticResource()
        
    def get_bot_id(self) -> str:
        """Get bot ID"""
        return self.bot_id
        
    def set_bot_id(self, bot_id: str):
        """Set bot ID"""
        self.bot_id = bot_id
        
    def get_icon_path(self) -> str:
        """Get icon path"""
        return self.icon_path
        
    def set_icon_path(self, icon_path: str):
        """Set icon path"""
        self.icon_path = icon_path
        
    def get_pseudo_name(self) -> Dict[str, str]:
        """Get pseudo name information"""
        return {
            'first_name': self.pseudo_first_name,
            'last_name': self.pseudo_last_name,
            'nick_name': self.pseudo_nick_name
        }
        
    def set_pseudo_name(self, first_name: str = "", last_name: str = "", nick_name: str = ""):
        """Set pseudo name information"""
        if first_name:
            self.pseudo_first_name = first_name
        if last_name:
            self.pseudo_last_name = last_name
        if nick_name:
            self.pseudo_nick_name = nick_name
            
    def get_location(self) -> Dict[str, str]:
        """Get location information"""
        return {
            'city': self.location_city,
            'state': self.location_state
        }
        
    def set_location(self, city: str = "", state: str = ""):
        """Set location information"""
        if city:
            self.location_city = city
        if state:
            self.location_state = state
            
    def get_age(self) -> str:
        """Get age"""
        return self.age
        
    def set_age(self, age: str):
        """Set age"""
        self.age = age
        
    def get_vehicle(self) -> str:
        """Get vehicle"""
        return self.vehicle
        
    def set_vehicle(self, vehicle: str):
        """Set vehicle"""
        self.vehicle = vehicle
        
    def get_gender(self) -> str:
        """Get gender"""
        return self.gender
        
    def set_gender(self, gender: str):
        """Set gender"""
        if gender in ["Male", "Female", "Unknown"]:
            self.gender = gender
            
    def get_birthday(self) -> str:
        """Get birthday"""
        return self.birthday
        
    def set_birthday(self, birthday: str):
        """Set birthday"""
        self.birthday = birthday
        
    def get_interest_settings(self) -> Dict[str, str]:
        """Get interest settings"""
        return {
            'platform': self.selected_interest_platform,
            'main_category': self.selected_interest_main_category,
            'sub_category1': self.selected_interest_sub_category1,
            'sub_category2': self.selected_interest_sub_category2,
            'sub_category3': self.selected_interest_sub_category3,
            'sub_category4': self.selected_interest_sub_category4,
            'sub_category5': self.selected_interest_sub_category5
        }
        
    def set_interest_settings(self, platform: str = None, main_category: str = None,
                            sub_category1: str = None, sub_category2: str = None,
                            sub_category3: str = None, sub_category4: str = None,
                            sub_category5: str = None):
        """Set interest settings"""
        if platform:
            self.selected_interest_platform = platform
        if main_category:
            self.selected_interest_main_category = main_category
        if sub_category1:
            self.selected_interest_sub_category1 = sub_category1
        if sub_category2:
            self.selected_interest_sub_category2 = sub_category2
        if sub_category3:
            self.selected_interest_sub_category3 = sub_category3
        if sub_category4:
            self.selected_interest_sub_category4 = sub_category4
        if sub_category5:
            self.selected_interest_sub_category5 = sub_category5
            
    def get_role_settings(self) -> Dict[str, str]:
        """Get role settings"""
        return {
            'platform': self.selected_role_platform,
            'level': self.selected_role_level,
            'role': self.selected_role_role
        }
        
    def set_role_settings(self, platform: str = None, level: str = None, role: str = None):
        """Set role settings"""
        if platform:
            self.selected_role_platform = platform
        if level:
            self.selected_role_level = level
        if role:
            self.selected_role_role = role
            
    def get_mode(self) -> str:
        """Get current mode"""
        return self.mode
        
    def set_mode(self, mode: str):
        """Set mode"""
        if mode in ["new", "update"]:
            self.mode = mode
            
    def get_roles(self) -> List[Dict[str, Any]]:
        """Get roles list"""
        return self.roles
        
    def add_role(self, role_data: Dict[str, Any]):
        """Add a role"""
        self.roles.append(role_data)
        
    def remove_role(self, role_index: int):
        """Remove a role by index"""
        if 0 <= role_index < len(self.roles):
            self.roles.pop(role_index)
            
    def update_role(self, role_index: int, role_data: Dict[str, Any]):
        """Update a role by index"""
        if 0 <= role_index < len(self.roles):
            self.roles[role_index] = role_data
            
    def get_interests(self) -> List[Dict[str, Any]]:
        """Get interests list"""
        return self.interests
        
    def add_interest(self, interest_data: Dict[str, Any]):
        """Add an interest"""
        self.interests.append(interest_data)
        
    def remove_interest(self, interest_index: int):
        """Remove an interest by index"""
        if 0 <= interest_index < len(self.interests):
            self.interests.pop(interest_index)
            
    def update_interest(self, interest_index: int, interest_data: Dict[str, Any]):
        """Update an interest by index"""
        if 0 <= interest_index < len(self.interests):
            self.interests[interest_index] = interest_data
            
    def get_available_platforms(self) -> List[str]:
        """Get available platforms"""
        platforms = self.static_resource.SITES.copy()
        platforms.insert(0, "any")
        return platforms
        
    def get_available_vehicles(self) -> List[Dict[str, Any]]:
        """Get available vehicles with capacity information"""
        vehicles = []
        for vehicle in self.main_win.vehicles:
            vehicle_info = {
                'name': vehicle.getName(),
                'os': vehicle.getOS(),
                'ip': vehicle.getIP(),
                'capacity': vehicle.CAP,
                'current_bots': len(vehicle.getBotIds()),
                'available': len(vehicle.getBotIds()) < vehicle.CAP
            }
            vehicles.append(vehicle_info)
        return vehicles
        
    def get_vehicle_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get vehicle by name"""
        for vehicle in self.get_available_vehicles():
            if vehicle['name'] == name:
                return vehicle
        return None
        
    def validate_bot_data(self) -> Dict[str, Any]:
        """
        Validate bot data
        
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check required fields
        if not self.location_city:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Location city is required")
            
        if not self.location_state:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Location state is required")
            
        if not self.vehicle:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Vehicle is required")
            
        if not self.gender or self.gender == "Unknown":
            validation_result['warnings'].append("Gender is not specified")
            
        if not self.birthday:
            validation_result['warnings'].append("Birthday is not specified")
            
        # Check vehicle capacity
        if self.vehicle:
            vehicle_info = self.get_vehicle_by_name(self.vehicle)
            if vehicle_info and not vehicle_info['available']:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Vehicle {self.vehicle} is at full capacity")
                
        return validation_result
        
    def save_bot(self) -> bool:
        """
        Save bot data
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Validate data first
            validation = self.validate_bot_data()
            if not validation['is_valid']:
                print(f"Validation errors: {validation['errors']}")
                return False
                
            # Update bot object
            if self.newBot:
                self.newBot.setBotId(self.bot_id)
                self.newBot.setIconPath(self.icon_path)
                self.newBot.setPseudoFirstName(self.pseudo_first_name)
                self.newBot.setPseudoLastName(self.pseudo_last_name)
                self.newBot.setPseudoNickName(self.pseudo_nick_name)
                self.newBot.setLocationCity(self.location_city)
                self.newBot.setLocationState(self.location_state)
                self.newBot.setAge(self.age)
                self.newBot.setVehicle(self.vehicle)
                self.newBot.setGender(self.gender)
                self.newBot.setBirthday(self.birthday)
                
                # Save roles and interests
                self.newBot.setRoles(self.roles)
                self.newBot.setInterests(self.interests)
                
            print("Bot saved successfully")
            return True
            
        except Exception as e:
            print(f"Error saving bot: {e}")
            return False
            
    def load_bot(self, bot: EBBOT):
        """
        Load bot data from EBBOT object
        
        Args:
            bot: EBBOT object to load from
        """
        try:
            if bot:
                self.newBot = bot
                self.bot_id = bot.getBotId() or ""
                self.icon_path = bot.getIconPath() or ""
                self.pseudo_first_name = bot.getPseudoFirstName() or ""
                self.pseudo_last_name = bot.getPseudoLastName() or ""
                self.pseudo_nick_name = bot.getPseudoNickName() or ""
                self.location_city = bot.getLocationCity() or ""
                self.location_state = bot.getLocationState() or ""
                self.age = bot.getAge() or ""
                self.vehicle = bot.getVehicle() or ""
                self.gender = bot.getGender() or "Unknown"
                self.birthday = bot.getBirthday() or ""
                
                # Load roles and interests
                self.roles = bot.getRoles() or []
                self.interests = bot.getInterests() or []
                
        except Exception as e:
            print(f"Error loading bot: {e}")
            
    def export_bot_to_json(self, filepath: str) -> bool:
        """
        Export bot data to JSON file
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            True if exported successfully, False otherwise
        """
        try:
            bot_data = {
                'bot_id': self.bot_id,
                'icon_path': self.icon_path,
                'pseudo_name': self.get_pseudo_name(),
                'location': self.get_location(),
                'age': self.age,
                'vehicle': self.vehicle,
                'gender': self.gender,
                'birthday': self.birthday,
                'interest_settings': self.get_interest_settings(),
                'role_settings': self.get_role_settings(),
                'roles': self.roles,
                'interests': self.interests,
                'mode': self.mode
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(bot_data, f, indent=2, ensure_ascii=False)
                
            print(f"Bot exported to: {filepath}")
            return True
            
        except Exception as e:
            print(f"Error exporting bot: {e}")
            return False
            
    def import_bot_from_json(self, filepath: str) -> bool:
        """
        Import bot data from JSON file
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            True if imported successfully, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                bot_data = json.load(f)
                
            # Load basic fields
            self.bot_id = bot_data.get('bot_id', '')
            self.icon_path = bot_data.get('icon_path', '')
            self.age = bot_data.get('age', '')
            self.vehicle = bot_data.get('vehicle', '')
            self.gender = bot_data.get('gender', 'Unknown')
            self.birthday = bot_data.get('birthday', '')
            self.mode = bot_data.get('mode', 'new')
            
            # Load pseudo name
            pseudo_name = bot_data.get('pseudo_name', {})
            self.pseudo_first_name = pseudo_name.get('first_name', '')
            self.pseudo_last_name = pseudo_name.get('last_name', '')
            self.pseudo_nick_name = pseudo_name.get('nick_name', '')
            
            # Load location
            location = bot_data.get('location', {})
            self.location_city = location.get('city', '')
            self.location_state = location.get('state', '')
            
            # Load settings
            interest_settings = bot_data.get('interest_settings', {})
            self.set_interest_settings(**interest_settings)
            
            role_settings = bot_data.get('role_settings', {})
            self.set_role_settings(**role_settings)
            
            # Load collections
            self.roles = bot_data.get('roles', [])
            self.interests = bot_data.get('interests', [])
            
            print(f"Bot imported from: {filepath}")
            return True
            
        except Exception as e:
            print(f"Error importing bot: {e}")
            return False
            
    def get_bot_summary(self) -> Dict[str, Any]:
        """Get summary of bot data"""
        return {
            'bot_id': self.bot_id,
            'pseudo_name': f"{self.pseudo_first_name} {self.pseudo_last_name}".strip(),
            'location': f"{self.location_city}, {self.location_state}".strip(', '),
            'vehicle': self.vehicle,
            'gender': self.gender,
            'age': self.age,
            'total_roles': len(self.roles),
            'total_interests': len(self.interests),
            'mode': self.mode,
            'is_valid': self.validate_bot_data()['is_valid']
        }
        
    def clear_bot_data(self):
        """Clear all bot data"""
        self.bot_id = ""
        self.icon_path = ""
        self.pseudo_first_name = ""
        self.pseudo_last_name = ""
        self.pseudo_nick_name = ""
        self.location_city = ""
        self.location_state = ""
        self.age = ""
        self.vehicle = ""
        self.gender = "Unknown"
        self.birthday = ""
        self.roles.clear()
        self.interests.clear()
        self.mode = "new"
        
    def findAllVehicle(self) -> List[VehicleModel]:
        """Find all available vehicles"""
        return self.main_win.vehicles if hasattr(self.main_win, 'vehicles') else []
        
    def findVehicleByIp(self, ip: str) -> Optional[VehicleModel]:
        """Find vehicle by IP address"""
        for vehicle in self.vehicleArray:
            if vehicle.getIP() == ip:
                return vehicle
        return None
        
    def get_bot_statistics(self) -> Dict[str, Any]:
        """Get bot creation statistics"""
        try:
            total_bots = len(self.main_win.bots) if hasattr(self.main_win, 'bots') else 0
            total_vehicles = len(self.vehicleArray)
            
            # Count bots by vehicle
            bots_by_vehicle = {}
            for vehicle in self.vehicleArray:
                vehicle_name = vehicle.getName()
                bot_count = len(vehicle.getBotIds())
                bots_by_vehicle[vehicle_name] = bot_count
                
            # Count bots by gender
            bots_by_gender = {}
            if hasattr(self.main_win, 'bots'):
                for bot in self.main_win.bots:
                    gender = bot.getGender() or "Unknown"
                    bots_by_gender[gender] = bots_by_gender.get(gender, 0) + 1
                    
            return {
                'total_bots': total_bots,
                'total_vehicles': total_vehicles,
                'bots_by_vehicle': bots_by_vehicle,
                'bots_by_gender': bots_by_gender,
                'available_vehicles': [v for v in self.get_available_vehicles() if v['available']]
            }
            
        except Exception as e:
            print(f"Error getting bot statistics: {e}")
            return {}
            
    def cleanup(self):
        """Clean up resources"""
        try:
            self.clear_bot_data()
            print("BotManager cleanup completed")
        except Exception as e:
            print(f"Error during cleanup: {e}")
