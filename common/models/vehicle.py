from sqlalchemy import Column, Integer, Text, Boolean

from common.db_init import Base

class VehicleModel(Base):
    __tablename__ = 'vehicle'
    id = Column(Integer, primary_key=True)
    agent_ids = Column(Text)
    arch = Column(Text)
    os = Column(Text)
    name = Column(Text)
    ip = Column(Text)
    status = Column(Text)
    mstats = Column(Text)
    field_link = Column(Text)
    daily_mids = Column(Text)
    cap = Column(Integer)
    last_update_time = Column(Text)

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'agent_ids': self.agent_ids,
            'arch': self.arch,
            'os': self.os,
            'name': self.name,
            'ip': self.ip,
            'mstats': self.mstats,
            'field_link': self.field_link,
            'daily_mids': self.daily_mids,
            'cap': self.cap,
            'last_update_time': self.last_update_time
        }