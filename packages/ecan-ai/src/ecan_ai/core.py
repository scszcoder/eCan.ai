"""
EcanAI - Main facade class for the eCan.ai library.

This module provides a clean, user-friendly API for interacting with
eCan.ai agents, skills, tasks, vehicles, and knowledge bases.

Example usage:
    from ecan_ai import EcanAI
    
    ecan = EcanAI(db_path="path/to/ecan_base.db")
    
    # List agents
    agents = ecan.agents.list()
    
    # Create an agent
    agent = ecan.agents.create(name="MyAgent", description="...")
    
    # Get agent by ID
    agent = ecan.agents.get("agent_id")
"""

from typing import Optional, List, Dict, Any
from pathlib import Path


class AgentManager:
    """Manager for agent operations. Wraps DBAgentService."""
    
    def __init__(self, db_mgr):
        self._db_mgr = db_mgr
    
    @property
    def _service(self):
        return self._db_mgr.get_agent_service()
    
    def list(self, name: str = None, owner: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List agents with optional filtering."""
        result = self._service.query_agents(name=name)
        if result.get('success'):
            data = result.get('data', [])
            if owner:
                data = [a for a in data if a.get('owner') == owner]
            return data[:limit]
        return []
    
    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        result = self._service.get_agent_by_id(agent_id)
        if result.get('success'):
            return result.get('data')
        return None
    
    def create(self, name: str, description: str = "", owner: str = None, **kwargs) -> Optional[Dict[str, Any]]:
        """Create a new agent."""
        agent_data = {
            'name': name,
            'description': description,
            'owner': owner or 'default',
            'status': 'active',
            **kwargs
        }
        result = self._service.add_agent(agent_data)
        if result.get('success'):
            return result.get('data')
        return None
    
    def update(self, agent_id: str, **kwargs) -> bool:
        """Update an agent."""
        result = self._service.update_agent(agent_id, kwargs)
        return result.get('success', False)
    
    def delete(self, agent_id: str) -> bool:
        """Delete an agent."""
        result = self._service.delete_agent(agent_id)
        return result.get('success', False)


class SkillManager:
    """Manager for skill operations. Wraps DBSkillService."""
    
    def __init__(self, db_mgr):
        self._db_mgr = db_mgr
    
    @property
    def _service(self):
        return self._db_mgr.get_skill_service()
    
    def list(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List skills with optional filtering."""
        result = self._service.query_skills(name=name)
        if result.get('success'):
            return result.get('data', [])[:limit]
        return []
    
    def get(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get skill by ID."""
        result = self._service.get_skill_by_id(skill_id)
        if result.get('success'):
            return result.get('data')
        return None
    
    def create(self, name: str, description: str = "", skill_type: str = "custom", **kwargs) -> Optional[Dict[str, Any]]:
        """Create a new skill."""
        skill_data = {
            'name': name,
            'description': description,
            'skill_type': skill_type,
            'status': 'active',
            **kwargs
        }
        result = self._service.add_skill(skill_data)
        if result.get('success'):
            return result.get('data')
        return None
    
    def delete(self, skill_id: str) -> bool:
        """Delete a skill."""
        result = self._service.delete_skill(skill_id)
        return result.get('success', False)


class TaskManager:
    """Manager for task operations. Wraps DBTaskService."""
    
    def __init__(self, db_mgr):
        self._db_mgr = db_mgr
    
    @property
    def _service(self):
        return self._db_mgr.get_task_service()
    
    def list(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List tasks with optional filtering."""
        result = self._service.query_tasks(name=name)
        if result.get('success'):
            return result.get('data', [])[:limit]
        return []
    
    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        result = self._service.get_task_by_id(task_id)
        if result.get('success'):
            return result.get('data')
        return None
    
    def create(self, name: str, description: str = "", task_type: str = "general", **kwargs) -> Optional[Dict[str, Any]]:
        """Create a new task."""
        task_data = {
            'name': name,
            'description': description,
            'task_type': task_type,
            'status': 'pending',
            **kwargs
        }
        result = self._service.add_task(task_data)
        if result.get('success'):
            return result.get('data')
        return None
    
    def delete(self, task_id: str) -> bool:
        """Delete a task."""
        result = self._service.delete_task(task_id)
        return result.get('success', False)


class VehicleManager:
    """Manager for vehicle operations. Wraps DBVehicleService."""
    
    def __init__(self, db_mgr):
        self._db_mgr = db_mgr
    
    @property
    def _service(self):
        return self._db_mgr.get_vehicle_service()
    
    def list(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List vehicles with optional filtering."""
        result = self._service.query_vehicles(name=name)
        if result.get('success'):
            return result.get('data', [])[:limit]
        return []
    
    def get(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        """Get vehicle by ID."""
        result = self._service.get_vehicle_by_id(vehicle_id)
        if result.get('success'):
            return result.get('data')
        return None
    
    def create(self, name: str, description: str = "", vehicle_type: str = "computer", **kwargs) -> Optional[Dict[str, Any]]:
        """Create a new vehicle."""
        vehicle_data = {
            'name': name,
            'description': description,
            'vehicle_type': vehicle_type,
            'status': 'active',
            **kwargs
        }
        result = self._service.add_vehicle(vehicle_data)
        if result.get('success'):
            return result.get('data')
        return None
    
    def delete(self, vehicle_id: str) -> bool:
        """Delete a vehicle."""
        result = self._service.delete_vehicle(vehicle_id)
        return result.get('success', False)


class EcanAI:
    """
    Main facade class for the eCan.ai library.
    
    Provides a clean API for managing agents, skills, tasks, vehicles,
    and knowledge bases without exposing database internals.
    
    Example:
        ecan = EcanAI(db_path="ecan_base.db")
        agents = ecan.agents.list()
        agent = ecan.agents.create(name="MyAgent")
    """
    
    def __init__(self, db_path: str = None, auto_migrate: bool = True):
        """
        Initialize EcanAI.
        
        Args:
            db_path: Path to the database file. If None, uses default location.
            auto_migrate: Whether to automatically run database migrations.
        """
        from .db import initialize_ecan_database
        
        # Determine database path
        if db_path is None:
            db_path = Path.home() / ".ecan" / "data"
        else:
            db_path = Path(db_path).parent if Path(db_path).suffix == '.db' else Path(db_path)
        
        # Ensure directory exists
        db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize database manager
        self._db_mgr = initialize_ecan_database(str(db_path), auto_migrate=auto_migrate)
        
        # Initialize managers (lazy - created on first access)
        self._agents = None
        self._skills = None
        self._tasks = None
        self._vehicles = None
    
    @property
    def agents(self) -> AgentManager:
        """Access agent management operations."""
        if self._agents is None:
            self._agents = AgentManager(self._db_mgr)
        return self._agents
    
    @property
    def skills(self) -> SkillManager:
        """Access skill management operations."""
        if self._skills is None:
            self._skills = SkillManager(self._db_mgr)
        return self._skills
    
    @property
    def tasks(self) -> TaskManager:
        """Access task management operations."""
        if self._tasks is None:
            self._tasks = TaskManager(self._db_mgr)
        return self._tasks
    
    @property
    def vehicles(self) -> VehicleManager:
        """Access vehicle management operations."""
        if self._vehicles is None:
            self._vehicles = VehicleManager(self._db_mgr)
        return self._vehicles
    
    @property
    def db_manager(self):
        """Access the underlying database manager (advanced usage)."""
        return self._db_mgr
    
    def close(self):
        """Close database connections."""
        if self._db_mgr:
            self._db_mgr.close()
