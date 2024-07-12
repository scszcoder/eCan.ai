from sqlalchemy import Column, Integer, Text, Boolean

from common.db_init import Base

class VehicleModel(Base):
    __tablename__ = 'vehicle'
    id = Column(Integer, primary_key=True)
    bot_ids = Column(Text)
    arch = Column(Text)
    os = Column(Text)
    name = Column(Text)
    ip = Column(Text)
    status = Column(Text)
    mstats = Column(Text)
    field_link = Column(Text)
    daily_mids = Column(Text)
    cap = Column(Integer)

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'bot_ids': self.bot_ids,
            'arch': self.arch,
            'os': self.os,
            'name': self.name,
            'ip': self.ip,
            'mstats': self.mstats,
            'field_link': self.field_link,
            'daily_mids': self.daily_mids,
            'cap': self.cap
        }