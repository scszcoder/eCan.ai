#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Train Manager - Data and Business Logic Handler
Handles training and recording operations without GUI components
"""

import asyncio
import json
import os
import platform
import queue
import time
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from typing import List, Dict, Any

import pyautogui
from pynput import keyboard, mouse

from utils.logger_helper import logger_helper as logger


class TrainManager:
    """
    Train Manager class that handles training data and business logic
    without GUI components
    """
    
    def __init__(self, main_win):
        """
        Initialize TrainManager
        
        Args:
            main_win: Reference to main window/application
        """
        self.main_win = main_win
        self.mouse_listener = None
        self.keyboard_listener = None
        
        self.record_over = False
        self.oldPos = None
        self.root_temp_dir = main_win.homepath + "/resource/skills/temp/"
        self.temp_dir = ''
        self.newSkill = None
        self.session = None
        self.auth_token = None
        
        # Recording data
        self.screen_image_stream = []
        self.record = []
        self.steps = 0
        self.actionRecord = []
        self.executor = ThreadPoolExecutor()
        self.loop = asyncio.get_event_loop()
        self.last_screenshot_time = time.time()
        self.frame_count = 0
        self.listeners_running = False
        
        # Event queue for processing recorded events
        self.event_queue = queue.Queue()
        
    def get_temp_dir(self) -> str:
        """Get current temporary directory"""
        return self.temp_dir
        
    def set_temp_dir(self, temp_dir: str):
        """Set temporary directory"""
        self.temp_dir = temp_dir
        
    def get_action_record(self) -> List[Dict[str, Any]]:
        """Get recorded actions"""
        return self.actionRecord
        
    def clear_action_record(self):
        """Clear recorded actions"""
        self.actionRecord.clear()
        self.steps = 0
        
    def get_screen_image_stream(self) -> List[Dict[str, Any]]:
        """Get screen image stream"""
        return self.screen_image_stream
        
    def clear_screen_image_stream(self):
        """Clear screen image stream"""
        self.screen_image_stream.clear()
        
    def is_recording(self) -> bool:
        """Check if recording is active"""
        return not self.record_over
        
    def start_recording(self):
        """Start recording process"""
        try:
            self.record_over = False
            logger.info("Starting input event listeners...")
            
            # Create temporary directory
            self.temp_dir = self.root_temp_dir + time.strftime("%Y%m%d-%H%M%S") + "/"
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
                
            # Start listeners
            self.loop.create_task(self.start_listeners())
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            
    def stop_recording(self):
        """Stop recording process"""
        self.record_over = True
        logger.info("Recording stopped")
        
    def cancel_recording(self):
        """Cancel recording process"""
        self.record_over = True
        logger.info("Recording cancelled")
        
    def on_move(self, x: int, y: int) -> bool:
        """
        Handle mouse move events
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            False if recording should stop, True otherwise
        """
        if self.record_over:
            self.record_over = False
            return False
            
        current_time = time.time()
        time_since_last_screenshot = current_time - self.last_screenshot_time
        
        if time_since_last_screenshot > 0.3:
            logger.debug(f'Pointer moved to ({x}, {y})')
            self.event_queue.put(('move', x, y, None, None, None))
            self.last_screenshot_time = current_time
            
        return True
        
    def on_click(self, x: int, y: int, button: Any, pressed: bool) -> bool:
        """
        Handle mouse click events
        
        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button
            pressed: Whether button is pressed
            
        Returns:
            False if recording should stop, True otherwise
        """
        if self.record_over:
            return False
            
        logger.debug(f"{'Pressed' if pressed else 'Released'} at ({x}, {y})")
        
        # Record event when button is released
        if not pressed:
            self.event_queue.put(('click', x, y, None, None, button))
            
        return True
        
    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> bool:
        """
        Handle mouse scroll events
        
        Args:
            x: X coordinate
            y: Y coordinate
            dx: Horizontal scroll delta
            dy: Vertical scroll delta
            
        Returns:
            False if recording should stop, True otherwise
        """
        if self.record_over:
            return False
            
        current_time = time.time()
        time_since_last_screenshot = current_time - self.last_screenshot_time
        
        if time_since_last_screenshot > 0.5:
            direction = 'down' if dy < 0 else 'up'
            logger.debug(f'Scrolled {direction} at ({x}, {y}) with delta ({dx}, {dy})')
            self.event_queue.put(('scroll', x, y, dx, dy, None))
            self.last_screenshot_time = current_time
            
        return True
        
    def on_press(self, key: Any):
        """
        Handle key press events
        
        Args:
            key: Key that was pressed
        """
        try:
            logger.debug(f'Alphanumeric key {key.char} pressed')
        except AttributeError:
            logger.debug(f'Special key {key} pressed')
            
    def on_release(self, key: Any) -> bool:
        """
        Handle key release events
        
        Args:
            key: Key that was released
            
        Returns:
            False if recording should stop, True otherwise
        """
        logger.debug(f'{key} released')
        
        if key == keyboard.Key.esc:
            # Stop recording on ESC key
            self.stop_recording()
            return False
            
        return True
        
    async def process_events(self):
        """Process recorded events asynchronously"""
        while not self.record_over:
            try:
                # Get event from queue
                event_type, x, y, dx, dy, button = self.event_queue.get()
                
                if event_type is not None:
                    await self.screenshot(event_type, x, y, dx, dy, button)
                    
                # Mark task as done
                self.event_queue.task_done()
                await asyncio.sleep(0.01)
                
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
                
    async def save_screenshot(self):
        """Save screenshots asynchronously"""
        while not self.record_over:
            if len(self.screen_image_stream) >= 5:
                for stream in self.screen_image_stream:
                    try:
                        stream['stream'].save(stream['file_name'])
                    except Exception as e:
                        logger.error(f"Failed to save screenshot: {e}")
                        
            await asyncio.sleep(1)
            
        # Save remaining screenshots when recording stops
        if self.record_over and len(self.screen_image_stream) > 0:
            for stream in self.screen_image_stream:
                try:
                    stream['stream'].save(stream['file_name'])
                except Exception as e:
                    logger.error(f"Failed to save final screenshot: {e}")
                    
    async def screenshot(self, option: str, x: int = None, y: int = None, 
                        dx: Any = None, dy: Any = None, button: Any = None):
        """
        Take screenshot and record action
        
        Args:
            option: Action type (move, click, scroll)
            x: X coordinate
            y: Y coordinate
            dx: Delta X
            dy: Delta Y
            button: Button information
        """
        self.steps += 1
        now = datetime.now()
        fname = self.temp_dir + option + "_step" + str(self.steps) + '_' + str(now.timestamp()) + ".png"
        
        logger.debug(f"Action: {option} at ({x}, {y}) - Step {self.steps}, File: {fname}")
        
        try:
            im = pyautogui.screenshot(fname)
            self.screen_image_stream.append({'file_name': fname, 'stream': im})
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            
        button_name = None
        if button is not None:
            button_name = button.name
            
        action = {
            'step': self.steps,
            'file_name': fname,
            'type': option,
            'time': now.timestamp(),
            'x': x,
            'y': y,
            'dx': dx,
            'dy': dy,
            'button': button_name
        }
        
        self.actionRecord.append(action)
        
    async def _start_listener(self, listener_class, callback_dict):
        """Start listener in executor"""
        def run_listener():
            with listener_class(**callback_dict) as listener:
                listener.join()
                
        await self.loop.run_in_executor(self.executor, run_listener)
        
    async def start_listeners(self):
        """Start mouse and keyboard listeners"""
        if self.listeners_running:
            logger.warning("Listeners are already running.")
            return
            
        listener_list = []
        self.listeners_running = True
        
        try:
            # Start mouse listener
            mouse_listener = self._start_listener(mouse.Listener, {
                'on_move': self.on_move,
                'on_click': self.on_click,
                'on_scroll': self.on_scroll,
            })
            listener_list.append(mouse_listener)
            
            # Start keyboard listener (except on macOS)
            if platform.system() != 'Darwin':
                keyboard_listener = self._start_listener(keyboard.Listener, {
                    'on_press': self.on_press,
                    'on_release': self.on_release,
                })
                listener_list.append(keyboard_listener)
                
            # Start event processing tasks
            process_events = self.process_events()
            listener_list.append(process_events)
            
            save_screenshot = self.save_screenshot()
            listener_list.append(save_screenshot)
            
            # Run all tasks concurrently
            await asyncio.gather(*listener_list)
            
        except Exception as e:
            logger.error(f"Error starting listeners: {e}")
            self.listeners_running = False
            
    def save_record_file(self, filename: str = None) -> bool:
        """
        Save recorded actions to file
        
        Args:
            filename: Optional filename, will prompt if not provided
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            if not filename:
                # Generate default filename
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                filename = f"process_record_{timestamp}.prf"
                
            # Ensure directory exists
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            with open(filename, 'w') as f:
                json.dump(self.actionRecord, f, indent=2)
                
            logger.info(f"Process record saved to: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save process record: {e}")
            return False
            
    def export_record_to_json(self, filepath: str) -> bool:
        """
        Export record data to JSON file
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            True if exported successfully, False otherwise
        """
        try:
            record_data = {
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'total_steps': len(self.actionRecord),
                    'temp_directory': self.temp_dir,
                    'platform': platform.system()
                },
                'actions': self.actionRecord,
                'screenshots': [
                    {
                        'file_name': stream['file_name'],
                        'timestamp': os.path.getctime(stream['file_name'])
                    }
                    for stream in self.screen_image_stream
                ]
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Record exported to: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export record: {e}")
            return False
            
    def get_record_summary(self) -> Dict[str, Any]:
        """Get summary of recorded actions"""
        if not self.actionRecord:
            return {
                'total_steps': 0,
                'action_types': {},
                'duration': 0,
                'screenshots': 0
            }
            
        action_types = {}
        for action in self.actionRecord:
            action_type = action.get('type', 'unknown')
            action_types[action_type] = action_types.get(action_type, 0) + 1
            
        # Calculate duration if we have timestamps
        duration = 0
        if len(self.actionRecord) >= 2:
            first_time = self.actionRecord[0].get('time', 0)
            last_time = self.actionRecord[-1].get('time', 0)
            duration = last_time - first_time
            
        return {
            'total_steps': len(self.actionRecord),
            'action_types': action_types,
            'duration': duration,
            'screenshots': len(self.screen_image_stream),
            'temp_directory': self.temp_dir
        }
        
    def set_cloud_credentials(self, session: Any, auth_token: str):
        """
        Set cloud credentials for skill operations
        
        Args:
            session: Session object
            auth_token: Authentication token
        """
        self.session = session
        self.auth_token = auth_token
        
    def skill_tutorial(self):
        """Start skill tutorial (placeholder for future implementation)"""
        logger.info("Skill tutorial requested")
        # TODO: Implement skill tutorial functionality
        
    def start_skill_definition(self):
        """Start skill definition process (placeholder for future implementation)"""
        logger.info("Skill definition requested")
        # TODO: Implement skill definition functionality
        
    def cleanup(self):
        """Clean up resources"""
        try:
            self.stop_recording()
            if self.executor:
                self.executor.shutdown(wait=False)
            logger.info("TrainManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


class ReminderManager:
    """
    Reminder Manager class that handles reminder logic
    without GUI components
    """
    
    def __init__(self, main_win):
        """
        Initialize ReminderManager
        
        Args:
            main_win: Reference to main window/application
        """
        self.main_win = main_win
        self.is_visible = False
        self.message = "Press <Esc> key to end recording"
        
    def get_message(self) -> str:
        """Get current reminder message"""
        return self.message
        
    def set_message(self, message: str):
        """Set reminder message"""
        self.message = message
        
    def show_reminder(self):
        """Show reminder (placeholder for future implementation)"""
        self.is_visible = True
        logger.info(f"Reminder shown: {self.message}")
        # TODO: Implement reminder display mechanism
        
    def hide_reminder(self):
        """Hide reminder"""
        self.is_visible = False
        logger.info("Reminder hidden")
        
    def is_reminder_visible(self) -> bool:
        """Check if reminder is visible"""
        return self.is_visible
        
    def update_reminder_position(self, x: int, y: int, width: int, height: int):
        """
        Update reminder position and size
        
        Args:
            x: X coordinate
            y: Y coordinate
            width: Width
            height: Height
        """
        logger.debug(f"Reminder position updated: ({x}, {y}) {width}x{height}")
        # TODO: Implement position update mechanism
        
    def get_reminder_info(self) -> Dict[str, Any]:
        """Get reminder information"""
        return {
            'message': self.message,
            'is_visible': self.is_visible,
            'platform': platform.system()
        }
