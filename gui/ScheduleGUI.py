#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schedule Manager - Data and Business Logic Handler
Handles scheduling operations without GUI components
"""

from datetime import datetime, date
from typing import Dict, List, Any, Optional
from utils.logger_helper import logger_helper


class ScheduleManager:
    """
    Schedule Manager class that handles scheduling data and business logic
    without GUI components
    """
    
    def __init__(self):
        """
        Initialize ScheduleManager
        """
        self.events = {}
        self.schedules = {}
        self.recurring_tasks = {}
        self.notifications = []
        
        # Initialize with some default events if needed
        self._init_default_events()
        
    def _init_default_events(self):
        """Initialize with default events"""
        try:
            # Example default events (can be removed or modified)
            default_date = date(2019, 5, 24)
            self.events[default_date] = ["Bob's birthday"]
            
            default_date2 = date(2019, 5, 19)
            self.events[default_date2] = ["Alice's birthday"]
            
        except Exception as e:
            logger_helper.error(f"Error initializing default events: {e}")
            
    def add_event(self, event_date: date, event_description: str) -> bool:
        """
        Add an event to the schedule
        
        Args:
            event_date: Date for the event
            event_description: Description of the event
            
        Returns:
            True if event added successfully, False otherwise
        """
        try:
            if event_date not in self.events:
                self.events[event_date] = []
            
            self.events[event_date].append(event_description)
            logger_helper.info(f"Event added: {event_description} on {event_date}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error adding event: {e}")
            return False
            
    def remove_event(self, event_date: date, event_description: str) -> bool:
        """
        Remove an event from the schedule
        
        Args:
            event_date: Date of the event
            event_description: Description of the event to remove
            
        Returns:
            True if event removed successfully, False otherwise
        """
        try:
            if event_date in self.events:
                if event_description in self.events[event_date]:
                    self.events[event_date].remove(event_description)
                    
                    # Remove the date if no events remain
                    if not self.events[event_date]:
                        del self.events[event_date]
                        
                    logger_helper.info(f"Event removed: {event_description} from {event_date}")
                    return True
                    
            logger_helper.warning(f"Event not found: {event_description} on {event_date}")
            return False
            
        except Exception as e:
            logger_helper.error(f"Error removing event: {e}")
            return False
            
    def get_events_for_date(self, event_date: date) -> List[str]:
        """
        Get all events for a specific date
        
        Args:
            event_date: Date to get events for
            
        Returns:
            List of event descriptions for the date
        """
        return self.events.get(event_date, [])
        
    def get_events_for_date_range(self, start_date: date, end_date: date) -> Dict[date, List[str]]:
        """
        Get all events within a date range
        
        Args:
            start_date: Start date of the range
            end_date: End date of the range
            
        Returns:
            Dictionary mapping dates to lists of events
        """
        range_events = {}
        
        for event_date, events in self.events.items():
            if start_date <= event_date <= end_date:
                range_events[event_date] = events
                
        return range_events
        
    def get_all_events(self) -> Dict[date, List[str]]:
        """Get all events"""
        return self.events.copy()
        
    def clear_events_for_date(self, event_date: date) -> bool:
        """
        Clear all events for a specific date
        
        Args:
            event_date: Date to clear events for
            
        Returns:
            True if events cleared successfully, False otherwise
        """
        try:
            if event_date in self.events:
                del self.events[event_date]
                logger_helper.info(f"All events cleared for {event_date}")
                return True
            return False
            
        except Exception as e:
            logger_helper.error(f"Error clearing events for date: {e}")
            return False
            
    def clear_all_events(self) -> bool:
        """
        Clear all events
        
        Returns:
            True if all events cleared successfully, False otherwise
        """
        try:
            self.events.clear()
            logger_helper.info("All events cleared")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error clearing all events: {e}")
            return False
            
    def add_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> bool:
        """
        Add a schedule
        
        Args:
            schedule_id: Unique identifier for the schedule
            schedule_data: Schedule data dictionary
            
        Returns:
            True if schedule added successfully, False otherwise
        """
        try:
            self.schedules[schedule_id] = schedule_data
            logger_helper.info(f"Schedule added: {schedule_id}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error adding schedule: {e}")
            return False
            
    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a schedule by ID
        
        Args:
            schedule_id: Schedule identifier
            
        Returns:
            Schedule data or None if not found
        """
        return self.schedules.get(schedule_id)
        
    def remove_schedule(self, schedule_id: str) -> bool:
        """
        Remove a schedule
        
        Args:
            schedule_id: Schedule identifier to remove
            
        Returns:
            True if schedule removed successfully, False otherwise
        """
        try:
            if schedule_id in self.schedules:
                del self.schedules[schedule_id]
                logger_helper.info(f"Schedule removed: {schedule_id}")
                return True
            return False
            
        except Exception as e:
            logger_helper.error(f"Error removing schedule: {e}")
            return False
            
    def add_recurring_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """
        Add a recurring task
        
        Args:
            task_id: Unique identifier for the task
            task_data: Task data dictionary
            
        Returns:
            True if task added successfully, False otherwise
        """
        try:
            self.recurring_tasks[task_id] = task_data
            logger_helper.info(f"Recurring task added: {task_id}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error adding recurring task: {e}")
            return False
            
    def get_recurring_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a recurring task by ID
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task data or None if not found
        """
        return self.recurring_tasks.get(task_id)
        
    def remove_recurring_task(self, task_id: str) -> bool:
        """
        Remove a recurring task
        
        Args:
            task_id: Task identifier to remove
            
        Returns:
            True if task removed successfully, False otherwise
        """
        try:
            if task_id in self.recurring_tasks:
                del self.recurring_tasks[task_id]
                logger_helper.info(f"Recurring task removed: {task_id}")
                return True
            return False
            
        except Exception as e:
            logger_helper.error(f"Error removing recurring task: {e}")
            return False
            
    def add_notification(self, notification_data: Dict[str, Any]) -> bool:
        """
        Add a notification
        
        Args:
            notification_data: Notification data dictionary
            
        Returns:
            True if notification added successfully, False otherwise
        """
        try:
            notification_id = f"notification_{len(self.notifications) + 1}"
            notification_data['id'] = notification_id
            notification_data['timestamp'] = datetime.now().isoformat()
            
            self.notifications.append(notification_data)
            logger_helper.info(f"Notification added: {notification_id}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error adding notification: {e}")
            return False
            
    def get_notifications(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get notifications
        
        Args:
            limit: Maximum number of notifications to return
            
        Returns:
            List of notification data
        """
        if limit:
            return self.notifications[-limit:]
        return self.notifications.copy()
        
    def clear_notifications(self) -> bool:
        """
        Clear all notifications
        
        Returns:
            True if notifications cleared successfully, False otherwise
        """
        try:
            self.notifications.clear()
            logger_helper.info("All notifications cleared")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error clearing notifications: {e}")
            return False
            
    def get_schedule_summary(self) -> Dict[str, Any]:
        """Get a summary of all scheduling data"""
        try:
            return {
                'total_events': len(self.events),
                'total_schedules': len(self.schedules),
                'total_recurring_tasks': len(self.recurring_tasks),
                'total_notifications': len(self.notifications),
                'date_range': {
                    'start': min(self.events.keys()) if self.events else None,
                    'end': max(self.events.keys()) if self.events else None
                }
            }
            
        except Exception as e:
            logger_helper.error(f"Error getting schedule summary: {e}")
            return {}
            
    def export_schedule_data(self, filepath: str) -> bool:
        """
        Export schedule data to JSON file
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            True if exported successfully, False otherwise
        """
        try:
            import json
            
            # Convert date objects to strings for JSON serialization
            export_data = {
                'events': {str(date): events for date, events in self.events.items()},
                'schedules': self.schedules,
                'recurring_tasks': self.recurring_tasks,
                'notifications': self.notifications,
                'export_timestamp': datetime.now().isoformat()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            logger_helper.info(f"Schedule data exported to: {filepath}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error exporting schedule data: {e}")
            return False
            
    def import_schedule_data(self, filepath: str) -> bool:
        """
        Import schedule data from JSON file
        
        Args:
            filepath: Path to load JSON file from
            
        Returns:
            True if imported successfully, False otherwise
        """
        try:
            import json
            
            with open(filepath, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
                
            # Convert string dates back to date objects
            if 'events' in import_data:
                self.events = {}
                for date_str, events in import_data['events'].items():
                    try:
                        event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self.events[event_date] = events
                    except ValueError:
                        logger_helper.warning(f"Invalid date format: {date_str}")
                        
            if 'schedules' in import_data:
                self.schedules = import_data['schedules']
                
            if 'recurring_tasks' in import_data:
                self.recurring_tasks = import_data['recurring_tasks']
                
            if 'notifications' in import_data:
                self.notifications = import_data['notifications']
                
            logger_helper.info(f"Schedule data imported from: {filepath}")
            return True
            
        except Exception as e:
            logger_helper.error(f"Error importing schedule data: {e}")
            return False
            
    def cleanup(self):
        """Clean up resources"""
        try:
            self.clear_all_events()
            self.schedules.clear()
            self.recurring_tasks.clear()
            self.clear_notifications()
            logger_helper.info("ScheduleManager cleanup completed")
        except Exception as e:
            logger_helper.error(f"Error during cleanup: {e}")


# Legacy class name for backward compatibility
class Scheduler:
    """
    Legacy Scheduler class - now just an alias for ScheduleManager
    """
    
    def __init__(self, parent=None):
        """
        Initialize Scheduler (legacy compatibility)
        
        Args:
            parent: Parent object (ignored for compatibility)
        """
        self.manager = ScheduleManager()
        
    def get_manager(self) -> ScheduleManager:
        """Get the underlying ScheduleManager instance"""
        return self.manager

