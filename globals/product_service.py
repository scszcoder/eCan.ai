import json

from globals import model
from globals.model import ProductsModel


class ProductService:
    def __init__(self, parent):
        self.parent = parent

    def find_all_products(self):
        results = model.session.query(ProductsModel)
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("fetchall" + json.dumps(dict_results))
        return results
