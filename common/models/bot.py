from sqlalchemy import Column, Integer, Text

from common.db_init import Base


class BotModel(Base):
    __tablename__ = 'bots'
    botid = Column(Integer, primary_key=True)
    owner = Column(Text)
    levels = Column(Text)
    birthday = Column(Text)
    interests = Column(Text)
    location = Column(Text)
    roles = Column(Text)
    status = Column(Text)
    delDate = Column(Text)
    name = Column(Text)
    pseudoname = Column(Text)
    nickname = Column(Text)
    gender = Column(Text)
    addr = Column(Text)
    shipaddr = Column(Text)
    phone = Column(Text)
    email = Column(Text)
    ebpw = Column(Text)
    backemail = Column(Text)
    backemailpw = Column(Text)
    backemail_site = Column(Text)
    epw = Column(Text)
    createon = Column(Text)
    vehicle = Column(Text)
    org = Column(Text)

    def to_dict(self):
        return {
            "botid": self.botid,
            "owner": self.owner,
            "levels": self.levels,
            "birthday": self.birthday,
            "interests": self.interests,
            "location": self.location,
            "roles": self.roles,
            "status": self.status,
            "delDate": self.delDate,
            "name": self.name,
            "pseudoname": self.pseudoname,
            "nickname": self.nickname,
            "gender": self.gender,
            "addr": self.addr,
            "shipaddr": self.shipaddr,
            "phone": self.phone,
            "email": self.email,
            "ebpw": self.ebpw,
            "backemail": self.backemail,
            "backemailpw": self.backemailpw,
            "backemail_site": self.backemail_site,
            "epw": self.epw,
            "createon": self.createon,
            "vehicle": self.vehicle,
            "org": self.org
        }