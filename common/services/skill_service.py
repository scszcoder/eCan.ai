import json

from sqlalchemy import inspect

from common.db_init import sync_table_columns
from common.models.skill import SkillModel
from utils.logger_helper import logger_helper


class SkillService:

    def __init__(self, main_win, session, engine=None):
        self.main_win = main_win
        self.session = session
        self.engine = engine
        # Pass engine parameter to sync_table_columns
        sync_table_columns(SkillModel, 'skills', engine)

    def insert_skill(self, api_skills):
        local_skill = SkillModel()
        local_skill.skid = api_skills["skid"]
        local_skill.owner = api_skills["owner"]
        local_skill.platform = api_skills["platform"]
        local_skill.app = api_skills["app"]
        local_skill.applink = api_skills["applink"]
        local_skill.site = api_skills["site"]
        local_skill.sitelink = api_skills["sitelink"]
        local_skill.name = api_skills["name"]
        local_skill.path = api_skills["path"]
        local_skill.main = api_skills["main"]
        local_skill.createdon = api_skills["createdon"]
        local_skill.extensions = api_skills["extensions"]
        local_skill.appargs = api_skills["appargs"]
        local_skill.runtime = api_skills["runtime"]
        local_skill.price_model = api_skills["price_model"]
        local_skill.price = api_skills["price"]
        local_skill.privacy = api_skills["privacy"]
        self.session.add(local_skill)
        self.session.commit()
        self.main_win.showMsg("Skill fetchall" + json.dumps(local_skill.to_dict()))

    def describe_table(self):
        inspector = inspect(SkillModel)
        # Print table structure information
        print(f"{SkillModel.__tablename__} Table column definitions: ")
        columns = inspector.columns
        for column in columns:
            logger_helper.debug(
                f"Column: {column['name']}, Type: {column['type']}, Nullable: {column['nullable']}, Default: {column['default']}")
        return columns