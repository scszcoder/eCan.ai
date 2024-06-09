import json

from globals import model
from globals.model import SkillModel


class SkillService:

    def __init__(self, parent):
        self.parent = parent

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
        model.session.add(local_skill)
        model.session.commit()
        self.parent.showMsg("Skill fetchall" + json.dumps(local_skill.to_dict()))
