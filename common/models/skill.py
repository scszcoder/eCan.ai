from sqlalchemy import Column, Integer, Text

from common.db_init import Base


class SkillModel(Base):
    __tablename__ = 'skills'
    skid = Column(Integer, primary_key=True)
    platform = Column(Text)
    app = Column(Text)
    applink = Column(Text)
    site = Column(Text)
    sitelink = Column(Text)
    name = Column(Text)
    path = Column(Text)
    runtime = Column(Text)
    price_model = Column(Text)
    price = Column(Integer)
    privacy = Column(Text)
    createon = Column(Text)

    def to_dict(self):
        return {
            'skid': self.skid,
            'platform': self.platform,
            'app': self.app,
            'applink': self.applink,
            'site': self.site,
            'sitelink': self.sitelink,
            'name': self.name,
            'path': self.path,
            'runtime': self.runtime,
            'price_model': self.price_model,
            'price': self.price,
            'privacy': self.privacy,
            'createon': self.createon,
        }
