import ast
import json
from typing import List

from sqlalchemy import inspect

from common.db_init import sync_table_columns
from common.models.vehicle import VehicleModel
from utils.logger_helper import logger_helper


class VehicleService:

    def __init__(self, main_win, session, engine=None):
        self.main_win = main_win
        self.session = session
        self.engine = engine
        # Pass engine parameter to sync_table_columns
        sync_table_columns(VehicleModel, 'vehicle', engine)

    def insert_vehicle(self, vehicle: VehicleModel):
        self.session.add(vehicle)
        self.session.commit()
        self.main_win.showMsg("Skill fetchall" + json.dumps(vehicle.to_dict()))

    def update_vehicle(self, vehicle: VehicleModel):
        self.session.query(VehicleModel).filter(VehicleModel.ip == vehicle.ip).update(vehicle.to_dict())
        self.session.commit()

    def remove_bot_from_current_vehicle(self, botid: str, vehicle: VehicleModel):
        if vehicle is not None:
            bot_ids = ast.literal_eval(vehicle.bot_ids)
            bot_ids.remove(botid)
            vehicle.bot_ids = str(bot_ids)
            self.session.commit()

    def find_vehicle_by_botid(self, botid: str) -> VehicleModel:
        return self.session.query(VehicleModel).filter(VehicleModel.bot_ids.like(f"%{botid}%")).first()

    def find_vehicle_by_ip(self, ip: str) -> VehicleModel:
        return self.session.query(VehicleModel).filter(VehicleModel.ip == ip).first()

    def find_vehicle_by_name(self, name: str) -> VehicleModel:
        return self.session.query(VehicleModel).filter(VehicleModel.name == name).first()

    def findAllVehicle(self) -> List[VehicleModel]:
        return self.session.query(VehicleModel).all()

    def describe_table(self):
        inspector = inspect(VehicleModel)
        # Print table structure information
        print(f"{VehicleModel.__tablename__} Table column definitions: ")
        columns = inspector.columns
        for column in columns:
            logger_helper.debug(
                f"Column: {column['name']}, Type: {column['type']}, Nullable: {column['nullable']}, Default: {column['default']}")
        return columns
