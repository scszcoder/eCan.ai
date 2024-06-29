from sqlalchemy import Integer, Text, Column

from common.db_init import Base


class MissionModel(Base):
    __tablename__ = 'missions'
    mid = Column(Integer, primary_key=True)
    ticket = Column(Integer)
    botid = Column(Integer)
    status = Column(Text)
    createon = Column(Text)
    # owner = Column(Text)
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
    variations = Column(Text)
    rating = Column(Text)
    feedbacks = Column(Text)
    price = Column(Text)
    customer = Column(Text)
    platoon = Column(Text)
    result = Column(Text)
    follow_seller = Column(Text)
    follow_price = Column(Text)

    def to_dict(self):
        return {
            "mid": self.mid,
            "ticket": self.ticket,
            "botid": self.botid,
            "status": self.status,
            "createon": self.createon,
            # "owner": self.owner,
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
            "variations": self.variations,
            "rating": self.rating,
            "feedbacks": self.feedbacks,
            "price": self.price,
            "customer": self.customer,
            "platoon": self.platoon,
            "result": self.result,
            "follow_seller": self.follow_seller,
            "follow_price": self.follow_price,
        }
