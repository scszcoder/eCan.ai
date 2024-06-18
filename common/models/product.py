from sqlalchemy import Column, Integer, Text, Float

from common.db_init import Base


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
