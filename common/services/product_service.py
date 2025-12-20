import json

from sqlalchemy import inspect

from common.db_init import sync_table_columns
from common.models.product import ProductsModel
from utils.logger_helper import logger_helper


class ProductService:
    def __init__(self, main_win, session, engine=None):
        self.main_win = main_win
        self.session = session
        self.engine = engine
        # Pass engine parameter to sync_table_columns
        sync_table_columns(ProductsModel, "products", engine)


    def find_all_products(self):
        results = self.session.query(ProductsModel)
        dict_results = [result.to_dict() for result in results]
        self.main_win.showMsg("fetchall" + json.dumps(dict_results))
        return results

    def describe_table(self):
        inspector = inspect(ProductsModel)
        # Print table structure information
        print(f"{ProductsModel.__tablename__} Table column definitions: ")
        columns = inspector.columns
        for column in columns:
            logger_helper.debug(
                f"Column: {column['name']}, Type: {column['type']}, Nullable: {column['nullable']}, Default: {column['default']}")
        return columns