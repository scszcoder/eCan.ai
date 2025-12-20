"""
Agent vehicle database models.

This module contains database models for agent vehicle management:
- DBAgentVehicle: Agent vehicle model for tracking execution environments
"""

from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentVehicle(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent vehicles (execution environments)"""
    __tablename__ = 'agent_vehicles'

    # Primary key
    id = Column(String(64), primary_key=True)

    # Basic vehicle information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Vehicle properties
    vehicle_type = Column(String(64), default='desktop')  # desktop, mobile, cloud, server, etc.
    platform = Column(String(64))                         # windows, macos, linux, android, ios, etc.
    architecture = Column(String(32))                     # x86_64, arm64, etc.
    
    # Network and connection
    ip_address = Column(String(45))                       # IPv4 or IPv6 address
    hostname = Column(String(128))                        # computer hostname
    port = Column(Integer)                                # connection port
    url = Column(String(512))                             # vehicle endpoint URL

    # Hardware specifications
    cpu_cores = Column(Integer)                           # number of CPU cores
    memory_gb = Column(Float)                             # memory in GB
    storage_gb = Column(Float)                            # storage in GB
    gpu_info = Column(JSON)                               # GPU information

    # Vehicle status and health
    status = Column(String(32), default='offline')       # online, offline, busy, maintenance
    health_score = Column(Float, default=1.0)            # 0.0 to 1.0 health score
    last_heartbeat = Column(DateTime)                     # last heartbeat timestamp
    uptime_seconds = Column(Integer, default=0)          # uptime in seconds

    # Capabilities and limitations
    capabilities = Column(JSON)                           # List[str] - what this vehicle can do
    limitations = Column(JSON)                            # List[str] - vehicle limitations
    max_concurrent_tasks = Column(Integer, default=1)    # maximum concurrent tasks

    # Location and environment
    location = Column(String(128))                        # physical location
    timezone = Column(String(64))                         # timezone
    environment = Column(String(64), default='production') # production, staging, development, test

    # Security and access
    security_level = Column(String(32), default='standard') # low, standard, high, critical
    access_token = Column(String(512))                    # access token for authentication
    ssl_enabled = Column(Boolean, default=True)          # SSL/TLS enabled

    # Metadata and settings
    settings = Column(JSON)                               # flexible settings storage
    extra_metadata = Column(JSON)                         # additional metadata

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # Include related task executions if needed
            pass
        return d

    def is_online(self):
        """Check if vehicle is currently online"""
        return self.status == 'online'

    def is_available(self):
        """Check if vehicle is available for new tasks"""
        return self.status in ['online', 'idle'] and self.health_score > 0.5

    def get_load_percentage(self):
        """Get current load percentage (placeholder for future implementation)"""
        # This would be calculated based on current running tasks
        return 0.0

    def __repr__(self):
        return f"<DBAgentVehicle(id='{self.id}', name='{self.name}', type='{self.vehicle_type}', status='{self.status}')>"

    def __str__(self):
        return f"{self.name} ({self.vehicle_type}) - {self.status}"
