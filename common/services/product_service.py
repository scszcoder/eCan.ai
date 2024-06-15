import json

from common.models.product import ProductsModel


class ProductService:
    def __init__(self, main_win, session):
        self.main_win = main_win
        self.session = session

    def find_all_products(self):
        results = self.session.query(ProductsModel)
        dict_results = [result.to_dict() for result in results]
        self.main_win.showMsg("fetchall" + json.dumps(dict_results))
        return results
