import os

from sqlalchemy import Column, Integer, MetaData, create_engine, Text, Float
from sqlalchemy.orm import declarative_base, sessionmaker

metadata = MetaData()
Base = declarative_base()


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


class ProductsModel(Base):
    __tablename__ = 'products'
    pid = Column(Integer, primary_key=True)
    name = Column(Text)
    title = Column(Text)
    asin = Column(Text)
    variation = Column(Text)
    site = Column(Text)
    sku = Column(Text)
    size_in = Column(Text)
    weight_lbs = Column(Float)
    condition = Column(Text)
    fullfiller = Column(Text)
    price = Column(Integer)
    cost = Column(Integer)
    inventory_loc = Column(Text)
    inventory_qty = Column(Text)
    createon = Column(Text)

    def to_dict(self):
        return {
            'pid': self.pid,
            'name': self.name,
            'title': self.title,
            'asin': self.asin,
            'variation': self.variation,
            'site': self.site,
            'sku': self.sku,
            'size_in': self.size_in,
            'weight_lbs': self.weight_lbs,
            'condition': self.condition,
            'fullfiller': self.fullfiller,
            'price': self.price,
            'cost': self.cost,
            'inventory_loc': self.inventory_loc,
            'inventory_qty': self.inventory_qty,
            'createon': self.createon,
        }


class MissionModel(Base):
    __tablename__ = 'missions'
    mid = Column(Integer, primary_key=True)
    ticket = Column(Integer)
    botid = Column(Integer)
    status = Column(Text)
    createon = Column(Text)
    owner = Column(Text)
    esd = Column(Text)
    ecd = Column(Text)
    asd = Column(Text)
    abd = Column(Text)
    aad = Column(Text)
    afd = Column(Text)
    acd = Column(Text)
    actual_start_time = Column(Text)
    est_start_time = Column(Text)
    actual_runtime = Column(Text)
    est_runtime = Column(Text)
    n_retries = Column(Text)
    cuspas = Column(Text)
    category = Column(Text)
    phrase = Column(Text)
    pseudoStore = Column(Text)
    pseudoBrand = Column(Text)
    pseudoASIN = Column(Text)
    type = Column(Text)
    config = Column(Text)
    skills = Column(Text)
    delDate = Column(Text)
    asin = Column(Text)
    store = Column(Text)
    brand = Column(Text)
    img = Column(Text)
    title = Column(Text)
    rating = Column(Text)
    feedbacks = Column(Text)
    price = Column(Text)
    customer = Column(Text)
    platoon = Column(Text)
    result = Column(Text)
    variations = Column(Text)

    def to_dict(self):
        return {
            "mid": self.mid,
            "ticket": self.ticket,
            "botid": self.botid,
            "status": self.status,
            "createon": self.createon,
            "esd": self.esd,
            "ecd": self.ecd,
            "asd": self.asd,
            "abd": self.abd,
            "aad": self.aad,
            "afd": self.afd,
            "acd": self.acd,
            "actual_start_time": self.actual_start_time,
            "est_start_time": self.est_start_time,
            "actual_runtime": self.actual_runtime,
            "est_runtime": self.est_runtime,
            "n_retries": self.n_retries,
            "cuspas": self.cuspas,
            "category": self.category,
            "phrase": self.phrase,
            "pseudoStore": self.pseudoStore,
            "pseudoBrand": self.pseudoBrand,
            "pseudoASIN": self.pseudoASIN,
            "type": self.type,
            "config": self.config,
            "skills": self.skills,
            "delDate": self.delDate,
            "asin": self.asin,
            "store": self.store,
            "brand": self.brand,
            "img": self.img,
            "title": self.title,
            "rating": self.rating,
            "feedbacks": self.feedbacks,
            "price": self.price,
            "customer": self.customer,
            "platoon": self.platoon,
            "result": self.result,
            "variations": self.variations,
        }


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
    backemail_site = Column(Text)
    epw = Column(Text)
    createon = Column(Text)

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
            "backemail_site": self.backemail_site,
            "epw": self.epw,
            "createon": self.createon,
        }


def init_db(dbfile):
    if not os.path.isfile(dbfile):
        # 获取文件所在目录
        dir_name = os.path.dirname(dbfile)
        # 确保目录存在
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(dbfile, 'w') as f:
            pass  # 创建一个空文件
    engine = create_engine("sqlite:///" + dbfile, echo=True)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """获取数据库会话"""
    Session = sessionmaker(bind=engine)
    return Session()
