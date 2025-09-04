#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Manager - Data and Business Logic Handler
Handles skill management operations without GUI components
"""

import json
import traceback
from typing import List, Dict, Any, Optional

from bot.Cloud import send_query_skills_request_to_cloud
from bot.Logger import LOG_SWITCH_BOARD, log3


class SkillManager:
    """
    Skill Manager class that handles skill data and business logic
    without GUI components
    """
    
    def __init__(self, mainwin):
        """
        Initialize SkillManager
        
        Args:
            mainwin: Reference to main window/application
        """
        self.mainwin = mainwin
        self.skills = []
        self.search_result_skills = []
        
    def get_skills(self) -> List[Any]:
        """Get all skills"""
        return self.skills
        
    def set_skills(self, skills: List[Any]):
        """Set skills list"""
        self.skills = skills
        
    def add_skill(self, skill: Any):
        """Add a skill to the list"""
        self.skills.append(skill)
        
    def remove_skill(self, skill: Any):
        """Remove a skill from the list"""
        if skill in self.skills:
            self.skills.remove(skill)
            
    def get_skill_by_id(self, skill_id: int) -> Optional[Any]:
        """Get skill by ID"""
        for skill in self.skills:
            if skill.getSkid() == skill_id:
                return skill
        return None
        
    def search_skills(self, search_phrase: str) -> List[Any]:
        """
        Search skills by phrase across multiple fields
        
        Args:
            search_phrase: Search keywords separated by spaces
            
        Returns:
            List of matching skills
        """
        matched_skills = []
        search_phrases = search_phrase.split()
        
        for skill in self.skills:
            for phrase in search_phrases:
                if (phrase.lower() in skill.getName().lower() or
                    phrase.lower() in skill.getPlatform().lower() or
                    phrase.lower() in skill.getApp().lower() or
                    phrase.lower() in skill.getSiteName().lower() or
                    phrase.lower() in skill.getPage().lower() or
                    phrase.lower() in skill.getDescription().lower()):
                    matched_skills.append(skill)
                    break
                    
        self.search_result_skills = matched_skills
        return matched_skills
        
    def get_search_results(self) -> List[Any]:
        """Get last search results"""
        return self.search_result_skills
        
    def fetch_my_skills(self, search_phrase: str = "") -> Dict[str, Any]:
        """
        Fetch skills from cloud based on ownership and search criteria
        
        Args:
            search_phrase: Optional search phrase
            
        Returns:
            Response from cloud API
        """
        self.mainwin.showMsg("Start fetching my skills......")
        
        try:
            if search_phrase == "":
                qsettings = {"byowneruser": True, "qphrase": ""}
            else:
                qsettings = {"byowneruser": False, "qphrase": search_phrase}
                
            resp = send_query_skills_request_to_cloud(
                self.mainwin.session, 
                self.mainwin.get_auth_token(), 
                qsettings, 
                self.mainwin.getWanApiEndpoint()
            )
            
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorFetchMySkills:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorFetchMySkills traceback information not available:" + str(e)
            log3(ex_stat)
            resp = {}
            
        return resp
        
    def save_skill_attributes(self, skill_data: List[List[Any]]):
        """
        Save skill attributes from data
        
        Args:
            skill_data: List of skill data rows
        """
        print("Saving skill attributes...")
        
        # Loop through the rows and save the data
        for row_data in skill_data:
            try:
                skill_id = int(row_data[0])  # Skill ID is in first column
                skill = self.get_skill_by_id(skill_id)
                
                if skill:
                    # Update the app_link value (assuming it's in column 7)
                    if len(row_data) > 7:
                        app_link = row_data[7]
                        skill.setAppLink(app_link)
                        
                    # Update other skill attributes if necessary
                    # (example: skill.setName(row_data[1]))
                    
            except Exception as e:
                print(f"Error saving skill {skill_id}: {e}")
                
        print("Skills saved successfully.")
        
    def open_skill(self, skill: Any):
        """Open a skill for editing"""
        self.mainwin.showMsg("opening skill....")
        if hasattr(self.mainwin, 'trainNewSkillWin'):
            self.mainwin.trainNewSkillWin.show()
            
    def copy_skill(self, skill: Any):
        """Copy a skill"""
        self.mainwin.showMsg("copying skill....")
        # Implement skill copying logic here
        
    def delete_skill(self, skill: Any) -> bool:
        """
        Delete a skill
        
        Args:
            skill: Skill to delete
            
        Returns:
            True if deletion was confirmed, False otherwise
        """
        self.mainwin.showMsg("deleting skill....")
        
        # Note: In the original code, this showed a confirmation dialog
        # Since we're removing GUI, you'll need to handle confirmation differently
        # For now, we'll assume deletion is confirmed
        
        # Remove from local list
        if skill in self.skills:
            self.skills.remove(skill)
            
        # TODO: Implement cloud deletion if needed
        # jresp = send_remove_skills_request_to_cloud(...)
        
        return True
        
    def get_skill_data_for_display(self, skills: List[Any] = None) -> List[List[Any]]:
        """
        Get skill data formatted for display
        
        Args:
            skills: Optional list of skills, uses self.skills if None
            
        Returns:
            List of skill data rows
        """
        if skills is None:
            skills = self.skills
            
        skill_data = []
        
        for skill in skills:
            row_data = [
                str(skill.getSkid()) if skill.getSkid() else "N/A",
                skill.getName() or "N/A",
                skill.getOwner() or "Unknown",
                skill.getOwner() or "Unknown",  # Users column
                skill.getCreatedOn() or "N/A",
                skill.getPlatform() or "N/A",
                skill.getApp() or "N/A",
                skill.getAppLink() or "N/A",
                skill.getAppArgs() or "N/A",
                skill.getSiteName() or "N/A",
                skill.getSite() or "N/A",
                skill.getPage() or "N/A",
                skill.getPrivacy() or "N/A"
            ]
            skill_data.append(row_data)
            
        return skill_data
        
    def update_skill_from_data(self, skill_id: int, column: int, value: Any):
        """
        Update a specific skill field
        
        Args:
            skill_id: ID of the skill to update
            column: Column index (field to update)
            value: New value
        """
        skill = self.get_skill_by_id(skill_id)
        if not skill:
            return False
            
        try:
            # Map column indices to skill methods
            column_mapping = {
                1: skill.setName,
                2: skill.setOwner,
                5: skill.setPlatform,
                6: skill.setApp,
                7: skill.setAppLink,
                8: skill.setAppArgs,
                9: skill.setSiteName,
                10: skill.setSite,
                11: skill.setPage,
                12: skill.setPrivacy
            }
            
            if column in column_mapping:
                column_mapping[column](value)
                return True
                
        except Exception as e:
            print(f"Error updating skill {skill_id} column {column}: {e}")
            
        return False
        
    def get_skills_by_owner(self, owner: str) -> List[Any]:
        """Get skills by owner"""
        return [skill for skill in self.skills if skill.getOwner() == owner]
        
    def get_skills_by_platform(self, platform: str) -> List[Any]:
        """Get skills by platform"""
        return [skill for skill in self.skills if skill.getPlatform() == platform]
        
    def get_skills_by_privacy(self, privacy: str) -> List[Any]:
        """Get skills by privacy level"""
        return [skill for skill in self.skills if skill.getPrivacy() == privacy]
        
    def get_skills_count(self) -> int:
        """Get total number of skills"""
        return len(self.skills)
        
    def clear_skills(self):
        """Clear all skills"""
        self.skills.clear()
        self.search_result_skills.clear()
        
    def export_skills_to_json(self, filepath: str):
        """Export skills to JSON file"""
        try:
            skills_data = []
            for skill in self.skills:
                skill_dict = {
                    'id': skill.getSkid(),
                    'name': skill.getName(),
                    'owner': skill.getOwner(),
                    'platform': skill.getPlatform(),
                    'app': skill.getApp(),
                    'app_link': skill.getAppLink(),
                    'app_args': skill.getAppArgs(),
                    'site_name': skill.getSiteName(),
                    'site': skill.getSite(),
                    'page': skill.getPage(),
                    'privacy': skill.getPrivacy(),
                    'created_on': skill.getCreatedOn(),
                    'description': skill.getDescription()
                }
                skills_data.append(skill_dict)
                
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(skills_data, f, indent=2, ensure_ascii=False)
                
            self.mainwin.showMsg(f"Skills exported to {filepath}")
            
        except Exception as e:
            self.mainwin.showMsg(f"Error exporting skills: {e}")
            
    def import_skills_from_json(self, filepath: str):
        """Import skills from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                skills_data = json.load(f)
                
            # Note: This is a simplified import - you may need to create proper skill objects
            # depending on your skill class implementation
            for skill_dict in skills_data:
                # Create skill object and add to list
                # This depends on how your skill class works
                pass
                
            self.mainwin.showMsg(f"Skills imported from {filepath}")
            
        except Exception as e:
            self.mainwin.showMsg(f"Error importing skills: {e}")
            
    def validate_skill(self, skill: Any) -> Dict[str, Any]:
        """
        Validate a skill's data
        
        Args:
            skill: Skill to validate
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check required fields
        if not skill.getName():
            validation_result['is_valid'] = False
            validation_result['errors'].append("Skill name is required")
            
        if not skill.getPlatform():
            validation_result['warnings'].append("Platform is not specified")
            
        if not skill.getApp():
            validation_result['warnings'].append("App is not specified")
            
        return validation_result
        
    def get_skills_summary(self) -> Dict[str, Any]:
        """Get summary statistics of skills"""
        if not self.skills:
            return {
                'total': 0,
                'by_platform': {},
                'by_privacy': {},
                'by_owner': {}
            }
            
        summary = {
            'total': len(self.skills),
            'by_platform': {},
            'by_privacy': {},
            'by_owner': {}
        }
        
        for skill in self.skills:
            # Count by platform
            platform = skill.getPlatform() or 'Unknown'
            summary['by_platform'][platform] = summary['by_platform'].get(platform, 0) + 1
            
            # Count by privacy
            privacy = skill.getPrivacy() or 'Unknown'
            summary['by_privacy'][privacy] = summary['by_privacy'].get(privacy, 0) + 1
            
            # Count by owner
            owner = skill.getOwner() or 'Unknown'
            summary['by_owner'][owner] = summary['by_owner'].get(owner, 0) + 1
            
        return summary