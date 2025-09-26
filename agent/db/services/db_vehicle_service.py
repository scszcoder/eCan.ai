"""
Vehicle database service.

This module provides database service for agent vehicle management operations.
"""

from sqlalchemy.orm import sessionmaker, joinedload
from ..core import get_engine, get_session_factory, Base
from ..models.vehicle_model import DBAgentVehicle
from ..models.association_models import DBAgentTaskRel
from .base_service import BaseService

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import re


class DBVehicleService(BaseService):
    """Vehicle database service class providing all vehicle-related operations"""

    def __init__(self, engine=None, session=None):
        """
        Initialize vehicle service

        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        # Call parent class initialization
        super().__init__(engine, session)

    @classmethod
    def initialize(cls, db_manager) -> 'DBVehicleService':
        """
        Initialize vehicle database service instance with database manager.

        Args:
            db_manager: ECDBMgr instance (required)

        Returns:
            DBVehicleService: Initialized service instance

        Raises:
            ValueError: If db_manager is None or not properly initialized
        """
        if db_manager is None:
            raise ValueError("db_manager cannot be None")
        
        if not hasattr(db_manager, 'get_engine') or not hasattr(db_manager, 'get_session_factory'):
            raise ValueError("db_manager must have get_engine and get_session_factory methods")
        
        try:
            engine = db_manager.get_engine()
            session_factory = db_manager.get_session_factory()
            
            # Create service instance with engine
            service = cls(engine=engine)
            service.db_manager = db_manager
            
            return service
            
        except Exception as e:
            raise ValueError(f"Failed to initialize DBVehicleService: {e}")

    @contextmanager
    def session_scope(self):
        """Transaction manager ensuring thread safety"""
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== Generic CRUD operations =================================
    
    def _add(self, model, data):
        """Generic add operation"""
        try:
            with self.session_scope() as s:
                obj = model(**data)
                s.add(obj)
                s.flush()
                return {"success": True, "id": obj.id, "data": obj.to_dict(), "error": None}
        except SQLAlchemyError as e:
            return {"success": False, "id": data.get("id"), "data": None, "error": str(e)}

    def _delete(self, model, id_):
        """Generic delete operation"""
        try:
            with self.session_scope() as s:
                obj = s.get(model, id_)
                if obj:
                    s.delete(obj)
                    return {"success": True, "id": id_, "data": None, "error": None}
                else:
                    return {"success": False, "id": id_, "data": None, "error": "Object not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": id_, "data": None, "error": str(e)}

    def _update(self, model, id_, fields):
        """Generic update operation"""
        try:
            with self.session_scope() as s:
                obj = s.get(model, id_)
                if obj:
                    for k, v in fields.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    s.flush()
                    return {"success": True, "id": id_, "data": obj.to_dict(), "error": None}
                else:
                    return {"success": False, "id": id_, "data": None, "error": "Object not found"}
        except SQLAlchemyError as e:
            return {"success": False, "id": id_, "data": None, "error": str(e)}

    def _search(self, model, id_: str = None, name: str = None, desc_regex: str = None):
        """Generic search operation"""
        try:
            with self.session_scope() as s:
                q = s.query(model)
                if id_:
                    q = q.filter(model.id == id_)
                if name:
                    q = q.filter(model.name.ilike(f"%{name}%"))
                results = q.all()
                if desc_regex:
                    pattern = re.compile(desc_regex, re.IGNORECASE)
                    results = [r for r in results if pattern.search(getattr(r, 'description', '') or '')]
                return [r.to_dict() for r in results]
        except SQLAlchemyError as e:
            print(f"[SearchError] {e}")
            return []

    # ========== Vehicle CRUD operations =================================

    def add_vehicle(self, data):
        """Add a new vehicle"""
        return self._add(DBAgentVehicle, data)

    def delete_vehicle(self, vehicle_id):
        """Delete a vehicle"""
        return self._delete(DBAgentVehicle, vehicle_id)

    def update_vehicle(self, vehicle_id, fields):
        """Update a vehicle"""
        return self._update(DBAgentVehicle, vehicle_id, fields)

    def query_vehicles(self, id=None, name=None, description=None):
        """Query vehicles"""
        return {"success": True,
                "data": self._search(DBAgentVehicle, id, name, description),
                "error": None}

    def search_vehicles(self, id=None, name=None, description=None):
        """Alias for query_vehicles for compatibility"""
        result = self.query_vehicles(id, name, description)
        return result.get("data", [])

    # ========== Vehicle Status Management =================================

    def update_vehicle_status(self, vehicle_id: str, status: str, 
                             health_score: float = None) -> Dict[str, Any]:
        """Update vehicle status and health"""
        try:
            with self.session_scope() as s:
                vehicle = s.get(DBAgentVehicle, vehicle_id)
                if vehicle:
                    vehicle.status = status
                    if health_score is not None:
                        vehicle.health_score = health_score
                    vehicle.last_heartbeat = datetime.utcnow()
                    s.flush()
                    return {"success": True, "data": vehicle.to_dict(), "error": None}
                else:
                    return {"success": False, "data": None, "error": "Vehicle not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def update_heartbeat(self, vehicle_id: str, uptime_seconds: int = None) -> Dict[str, Any]:
        """Update vehicle heartbeat and uptime"""
        try:
            with self.session_scope() as s:
                vehicle = s.get(DBAgentVehicle, vehicle_id)
                if vehicle:
                    vehicle.last_heartbeat = datetime.utcnow()
                    if uptime_seconds is not None:
                        vehicle.uptime_seconds = uptime_seconds
                    s.flush()
                    return {"success": True, "data": vehicle.to_dict(), "error": None}
                else:
                    return {"success": False, "data": None, "error": "Vehicle not found"}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_online_vehicles(self) -> Dict[str, Any]:
        """Get all online vehicles"""
        try:
            with self.session_scope() as s:
                vehicles = s.query(DBAgentVehicle).filter(
                    DBAgentVehicle.status == 'online'
                ).all()
                return {"success": True, "data": [v.to_dict() for v in vehicles], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_available_vehicles(self) -> Dict[str, Any]:
        """Get vehicles available for new tasks"""
        try:
            with self.session_scope() as s:
                vehicles = s.query(DBAgentVehicle).filter(
                    and_(DBAgentVehicle.status.in_(['online', 'idle']),
                         DBAgentVehicle.health_score > 0.5)
                ).all()
                return {"success": True, "data": [v.to_dict() for v in vehicles], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_vehicles_by_type(self, vehicle_type: str) -> Dict[str, Any]:
        """Get vehicles by type"""
        try:
            with self.session_scope() as s:
                vehicles = s.query(DBAgentVehicle).filter(
                    DBAgentVehicle.vehicle_type == vehicle_type
                ).all()
                return {"success": True, "data": [v.to_dict() for v in vehicles], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_vehicles_by_platform(self, platform: str) -> Dict[str, Any]:
        """Get vehicles by platform"""
        try:
            with self.session_scope() as s:
                vehicles = s.query(DBAgentVehicle).filter(
                    DBAgentVehicle.platform == platform
                ).all()
                return {"success": True, "data": [v.to_dict() for v in vehicles], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    # ========== Vehicle Task Management =================================

    def get_vehicle_tasks(self, vehicle_id: str, status: str = None) -> Dict[str, Any]:
        """Get all tasks running on a vehicle"""
        try:
            with self.session_scope() as s:
                query = s.query(DBAgentTaskRel).filter(
                    DBAgentTaskRel.vehicle_id == vehicle_id
                )
                if status:
                    query = query.filter(DBAgentTaskRel.status == status)
                tasks = query.order_by(DBAgentTaskRel.created_at.desc()).all()
                return {"success": True, "data": [t.to_dict() for t in tasks], "error": None}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    def get_running_tasks_on_vehicle(self, vehicle_id: str) -> Dict[str, Any]:
        """Get currently running tasks on a vehicle"""
        return self.get_vehicle_tasks(vehicle_id, status='running')

    def get_vehicle_load(self, vehicle_id: str) -> Dict[str, Any]:
        """Get current load information for a vehicle"""
        try:
            with self.session_scope() as s:
                vehicle = s.get(DBAgentVehicle, vehicle_id)
                if not vehicle:
                    return {"success": False, "data": {}, "error": "Vehicle not found"}

                # Count running tasks
                running_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.status == 'running')
                ).count()

                # Calculate load percentage
                max_concurrent = vehicle.max_concurrent_tasks or 1
                load_percentage = (running_tasks / max_concurrent) * 100

                load_info = {
                    'vehicle_id': vehicle_id,
                    'vehicle_name': vehicle.name,
                    'status': vehicle.status,
                    'running_tasks': running_tasks,
                    'max_concurrent_tasks': max_concurrent,
                    'load_percentage': min(load_percentage, 100.0),
                    'health_score': vehicle.health_score,
                    'last_heartbeat': vehicle.last_heartbeat,
                    'is_available': vehicle.is_available()
                }

                return {"success": True, "data": load_info, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    def find_best_vehicle_for_task(self, task_requirements: Dict[str, Any] = None) -> Dict[str, Any]:
        """Find the best available vehicle for a task"""
        try:
            available_result = self.get_available_vehicles()
            if not available_result["success"]:
                return {"success": False, "data": None, "error": available_result["error"]}
            
            available_vehicles = available_result["data"]
            
            if not available_vehicles:
                return {"success": False, "data": None, "error": "No available vehicles"}

            # If no specific requirements, return the vehicle with lowest load
            if not task_requirements:
                best_vehicle = None
                lowest_load = float('inf')
                
                for vehicle_data in available_vehicles:
                    load_result = self.get_vehicle_load(vehicle_data['id'])
                    if load_result["success"]:
                        load_percentage = load_result["data"]['load_percentage']
                        if load_percentage < lowest_load:
                            lowest_load = load_percentage
                            best_vehicle = vehicle_data
                
                return {"success": True, "data": best_vehicle, "error": None}

            # Filter by requirements
            suitable_vehicles = []
            
            for vehicle_data in available_vehicles:
                # Check platform requirement
                if task_requirements.get('platform') and vehicle_data.get('platform') != task_requirements['platform']:
                    continue
                
                # Check vehicle type requirement
                if task_requirements.get('vehicle_type') and vehicle_data.get('vehicle_type') != task_requirements['vehicle_type']:
                    continue
                
                # Check minimum health score
                min_health = task_requirements.get('min_health_score', 0.5)
                if vehicle_data.get('health_score', 0) < min_health:
                    continue
                
                # Check capabilities
                required_capabilities = task_requirements.get('capabilities', [])
                vehicle_capabilities = vehicle_data.get('capabilities') or []
                if not all(cap in vehicle_capabilities for cap in required_capabilities):
                    continue
                
                suitable_vehicles.append(vehicle_data)

            if not suitable_vehicles:
                return {"success": False, "data": None, "error": "No suitable vehicles found"}

            # Return vehicle with lowest load among suitable ones
            best_vehicle = None
            lowest_load = float('inf')
            
            for vehicle_data in suitable_vehicles:
                load_result = self.get_vehicle_load(vehicle_data['id'])
                if load_result["success"]:
                    load_percentage = load_result["data"]['load_percentage']
                    if load_percentage < lowest_load:
                        lowest_load = load_percentage
                        best_vehicle = vehicle_data
            
            return {"success": True, "data": best_vehicle, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    # ========== Vehicle Statistics =================================

    def get_vehicle_statistics(self, vehicle_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive statistics for a vehicle"""
        try:
            with self.session_scope() as s:
                vehicle = s.get(DBAgentVehicle, vehicle_id)
                if not vehicle:
                    return {"success": False, "data": {}, "error": "Vehicle not found"}

                # Calculate date range
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)

                # Count tasks in the period
                total_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.created_at >= start_date)
                ).count()

                completed_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.status == 'completed',
                         DBAgentTaskRel.created_at >= start_date)
                ).count()

                failed_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.status == 'failed',
                         DBAgentTaskRel.created_at >= start_date)
                ).count()

                running_tasks = s.query(DBAgentTaskRel).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.status == 'running')
                ).count()

                # Calculate success rate
                success_rate = 0.0
                if completed_tasks + failed_tasks > 0:
                    success_rate = completed_tasks / (completed_tasks + failed_tasks)

                # Calculate average execution time
                avg_execution_time = s.query(func.avg(DBAgentTaskRel.execution_time)).filter(
                    and_(DBAgentTaskRel.vehicle_id == vehicle_id,
                         DBAgentTaskRel.status == 'completed',
                         DBAgentTaskRel.execution_time.isnot(None),
                         DBAgentTaskRel.created_at >= start_date)
                ).scalar() or 0.0

                # Get current load
                load_result = self.get_vehicle_load(vehicle_id)
                current_load = load_result["data"]["load_percentage"] if load_result["success"] else 0.0

                stats = {
                    'vehicle_id': vehicle_id,
                    'vehicle_name': vehicle.name,
                    'vehicle_type': vehicle.vehicle_type,
                    'platform': vehicle.platform,
                    'status': vehicle.status,
                    'health_score': vehicle.health_score,
                    'uptime_seconds': vehicle.uptime_seconds,
                    'last_heartbeat': vehicle.last_heartbeat,
                    'period_days': days,
                    'tasks': {
                        'total': total_tasks,
                        'completed': completed_tasks,
                        'failed': failed_tasks,
                        'running': running_tasks,
                        'success_rate': success_rate
                    },
                    'performance': {
                        'avg_execution_time': avg_execution_time,
                        'max_concurrent_tasks': vehicle.max_concurrent_tasks,
                        'current_load': current_load
                    }
                }

                return {"success": True, "data": stats, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": str(e)}

    def cleanup_stale_vehicles(self, heartbeat_timeout_minutes: int = 10) -> Dict[str, Any]:
        """Mark vehicles as offline if they haven't sent heartbeat recently"""
        try:
            with self.session_scope() as s:
                timeout_threshold = datetime.utcnow() - timedelta(minutes=heartbeat_timeout_minutes)
                
                stale_vehicles = s.query(DBAgentVehicle).filter(
                    and_(DBAgentVehicle.status.in_(['online', 'busy']),
                         or_(DBAgentVehicle.last_heartbeat < timeout_threshold,
                             DBAgentVehicle.last_heartbeat.is_(None)))
                ).all()

                count = 0
                for vehicle in stale_vehicles:
                    vehicle.status = 'offline'
                    vehicle.health_score = 0.0
                    count += 1

                s.flush()
                return {"success": True, "data": {"cleaned_count": count}, "error": None}
        except Exception as e:
            return {"success": False, "data": {"cleaned_count": 0}, "error": str(e)}
