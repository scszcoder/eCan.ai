import json
import os
import sqlite3
from datetime import timedelta, datetime

from sqlalchemy import or_, delete, func

from Cloud import send_query_missions_request_to_cloud, send_query_bots_request_to_cloud
from globals import model
from globals.model import BotModel, SkillModel, ProductsModel, MissionModel


class FileResource:
    def __init__(self, homepath):
        self.bot_icon_path = homepath + '/resource/images/icons/c_robot64_1.png'
        self.sell_icon_path = homepath + '/resource/images/icons/c_robot64_0.png'
        self.buy_bot_icon_path = homepath + '/resource/images/icons/c_robot64_1.png'
        self.mission_icon_path = homepath + '/resource/images/icons/c_mission96_1.png'
        self.mission_success_icon_path = homepath + '/resource/images/icons/successful_launch0_48.png'
        self.mission_failed_icon_path = homepath + '/resource/images/icons/failed_launch0_48.png'
        self.skill_icon_path = homepath + '/resource/images/icons/skills_78.png'
        self.product_icon_path = homepath + '/resource/images/icons/product80_0.png'
        self.vehicle_icon_path = homepath + '/resource/images/icons/vehicle_128.png'
        self.commander_icon_path = homepath + '/resource/images/icons/general1_4.png'
        self.BOTS_FILE = homepath + "/resource/bots.json"
        self.MISSIONS_FILE = homepath + "/resource/missions.json"


def init_sql_file(dbfile):
    if not os.path.isfile(dbfile):
        # 获取文件所在目录
        dir_name = os.path.dirname(dbfile)
        # 确保目录存在
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(dbfile, 'w') as f:
            pass  # 创建一个空文件
    model.init_sqlalchemy(dbfile)
    return sqlite3.connect(dbfile)


class SqlProcessor:
    def __init__(self, parent):
        self.parent = parent
        self.dbcon = init_sql_file(parent.dbfile)
        self.dbCursor = self.dbcon.cursor()

    def insert_skill(self, api_skills):
        insert_data = {
            "botid": api_skills["skid"],
            "owner": api_skills["owner"],
            "platform": api_skills["platform"],
            "app": api_skills["app"],
            "applink": api_skills["applink"],
            "appargs": api_skills["appargs"],
            "site": api_skills["site"],
            "sitelink": api_skills["sitelink"],
            "name": api_skills["name"],
            "path": api_skills["path"],
            "main": api_skills["main"],
            "createdon": api_skills["createdon"],
            "extensions": api_skills["extensions"],
            "runtime": api_skills["runtime"],
            "price_model": api_skills["price_model"],
            "price": api_skills["price"],
            "privacy": api_skills["privacy"]
        }
        new_skill_instance = SkillModel(**insert_data)
        model.session.add(new_skill_instance)
        model.session.commit()
        self.parent.showMsg("Skill fetchall" + json.dumps(new_skill_instance.to_dict()))

    def find_all_products(self):
        results = model.session.query(ProductsModel)
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("fetchall" + json.dumps(dict_results))
        return results

    def find_missions_by_createon(self):
        current_time = datetime.now()
        three_days_ago = current_time - timedelta(days=3)
        missions = model.session.query(MissionModel).filter(MissionModel.createon >= three_days_ago).all()
        return missions

    def find_missions_by_mids(self, mids) -> [BotModel]:
        results = model.session.query(MissionModel).filter(MissionModel.mid.in_(mids)).all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("Just Added Local DB Mission Row(s): " + json.dumps(dict_results), "debug")
        return results

    def find_missions_by_mid(self, mid) -> BotModel:
        result: BotModel = model.session.query(MissionModel).filter(MissionModel.mid == mid).first()
        if result is not None:
            self.parent.showMsg("Just Added Local DB Mission Row(s): " + json.dumps(result.to_dict()), "debug")
        return result

    def insert_missions_batch_(self, api_missions):
        insert_data = {
            "mid": api_missions["mid"],
            "ticket": api_missions["ticket"],
            "botid": api_missions["botid"],
            "status": api_missions["status"],
            "createon": api_missions["createon"],
            "esd": api_missions["esd"],
            "ecd": api_missions["ecd"],
            "asd": api_missions["asd"],
            "abd": api_missions["abd"],
            "aad": api_missions["aad"],
            "afd": api_missions["afd"],
            "acd": api_missions["acd"],
            "actual_start_time": api_missions["actual_start_time"],
            "est_start_time": api_missions["est_start_time"],
            "actual_runtime": api_missions["actual_runtime"],
            "est_runtime": api_missions["est_runtime"],
            "n_retries": api_missions["n_retries"],
            "cuspas": api_missions["cuspas"],
            "category": api_missions["category"],
            "phrase": api_missions["phrase"],
            "pseudoStore": api_missions["pseudoStore"],
            "pseudoBrand": api_missions["pseudoBrand"],
            "pseudoASIN": api_missions["pseudoASIN"],
            "type": api_missions["type"],
            "config": api_missions["config"],
            "skills": api_missions["skills"],
            "delDate": api_missions["delDate"],
            "asin": api_missions["asin"],
            "store": api_missions["store"],
            "brand": api_missions["brand"],
            "img": api_missions["img"],
            "title": api_missions["title"],
            "rating": api_missions["rating"],
            "feedbacks": api_missions["feedbacks"],
            "price": api_missions["price"],
            "customer": api_missions["customer"],
            "platoon": api_missions["platoon"],
            "result": api_missions["result"]
        }
        new_mission_instance = MissionModel(**insert_data)
        model.session.add(new_mission_instance)
        model.session.commit()
        self.parent.showMsg("Mission fetchall" + json.dumps(new_mission_instance.to_dict()))

    def find_all_missions(self) -> [MissionModel]:
        results = model.session.query(MissionModel).all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("Missions fetchall" + json.dumps(dict_results))
        return results

    def insert_missions_batch(self, jbody, api_missions):
        for i, jb in enumerate(jbody):
            messions = api_missions[i]
            insert_data = {
                "mid": jb["mid"],
                "ticket": jb["ticket"],
                "botid": jb["botid"],
                "status": jb["status"],
                "createon": jb["createon"],
                "esd": jb["esd"],
                "ecd": jb["ecd"],
                "asd": jb["asd"],
                "abd": jb["abd"],
                "aad": jb["aad"],
                "afd": jb["afd"],
                "acd": jb["acd"],
                "actual_start_time": messions["actual_start_time"],
                "est_start_time": jb["esttime"],
                "actual_runtime": messions["actual_run_time"],
                "est_runtime": jb["runtime"],
                "n_retries": messions["n_retries"],
                "cuspas": jb["cuspas"],
                "category": jb["category"],
                "phrase": jb["phrase"],
                "pseudoStore": jb["pseudoStore"],
                "pseudoBrand": jb["pseudoBrand"],
                "pseudoASIN": jb["pseudoASIN"],
                "type": jb["type"],
                "config": str(jb["config"]),
                "skills": jb["skills"],
                "delDate": jb["delDate"],
                "asin": messions["asin"],
                "store": messions["store"],
                "brand": messions["brand"],
                "img": messions["image"],
                "title": messions["title"],
                "rating": messions["rating"],
                "feedbacks": messions["feedbacks"],
                "price": messions["price"],
                "customer": messions["customer"],
                "platoon": messions["platoon"],
                "result": messions["result"]
            }
            new_mission_instance = MissionModel(**insert_data)
            model.session.add(new_mission_instance)
            self.parent.showMsg("Mission fetchall" + json.dumps(new_mission_instance.to_dict()))
        model.session.commit()

    def update_missions_by_ticket(self, api_missions):
        for i, amission in enumerate(api_missions):
            result = model.session.query(MissionModel).filter(MissionModel.mid == amission["amission"]).first()
            result.ticket = amission["ticket"]
            result.botid = amission["botid"]
            result.status = amission["status"]
            result.createon = amission["createon"]
            result.esd = amission["esd"]
            result.ecd = amission["ecd"]
            result.asd = amission["asd"]
            result.abd = amission["abd"]
            result.aad = amission["aad"]
            result.afd = amission["afd"]
            result.acd = amission["acd"]
            result.actual_start_time = datetime.strptime(amission['actual_start_time'], '%Y-%m-%d')
            result.est_start_time = datetime.strptime(amission['est_start_time'], '%Y-%m-%d')
            result.actual_run_time = datetime.strptime(amission['actual_run_time'], '%Y-%m-%d')
            result.est_run_time = amission['est_run_time']
            result.n_retries = amission["n_retries"]
            result.cuspas = amission["cuspas"]
            result.search_cat = amission["search_cat"]
            result.search_kw = amission["search_kw"]
            result.pseudo_store = amission["pseudo_store"]
            result.pseudo_brand = amission["pseudo_brand"]
            result.pseudo_asin = amission["pseudo_asin"]
            result.type = amission["type"]
            result.config = amission["config"]
            result.skills = amission["skills"]
            result.delDate = amission["delDate"]
            result.asin = amission["asin"]
            result.store = amission["store"]
            result.brand = amission["brand"]
            result.image = amission["image"]
            result.title = amission["title"]
            result.rating = amission["rating"]
            result.feedbacks = amission["feedbacks"]
            result.price = amission["price"]
            result.customer = amission["customer"]
            result.platoon = amission["platoon"]
            result.result = amission["result"]
            model.session.commit()
            self.parent.showMsg("update row: " + json.dumps(result.to_dict()))

    def find_missions_by_search(self, start_time, end_time, search) -> [MissionModel]:
        query = model.session.query(MissionModel)
        if len(start_time) > 0 and len(end_time) > 0:
            query = query.filter(MissionModel.createon.between(start_time, end_time))
        if len(search) > 0:
            conditions = [
                MissionModel.asin.like('%' + search + '%'),
                MissionModel.store.like('%' + search + '%'),
                MissionModel.brand.like('%' + search + '%'),
                MissionModel.title.like('%' + search + '%'),
                MissionModel.pseudoStore.like('%' + search + '%'),
                MissionModel.pseudoBrand.like('%' + search + '%'),
                MissionModel.pseudoASIN.like('%' + search + '%')
            ]
            query = query.filter(or_(conditions))
        results = query.all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("Missions fetchall" + json.dumps(dict_results))
        return results

    def delete_missions_by_mid(self, mid):
        delete_stmt = delete(MissionModel).where(MissionModel.mid == mid)
        # 执行删除
        result = model.session.execute(delete_stmt)
        model.session.commit()
        if result.rowcount > 0:
            print(f"Mission with mid {mid} deleted successfully.")
        else:
            print(f"No Mission found with mid {mid} to delete.")

    def delete_missions_by_ticket(self, ticket):
        mission_instance = model.session.query(MissionModel).filter(MissionModel.ticket == ticket).one()
        if mission_instance is not None:
            model.session.delete(mission_instance)
            model.session.commit()
        return mission_instance

    ### BOTS ####
    def delete_bots_by_botid(self, botid):
        # 构建删除表达式
        delete_stmt = delete(BotModel).where(BotModel.botid == botid)
        # 执行删除
        result = model.session.execute(delete_stmt)
        model.session.commit()
        if result.rowcount > 0:
            print(f"Bot with botid {botid} deleted successfully.")
        else:
            print(f"No bot found with botid {botid} to delete.")

    def find_bots_by_search(self, start_time, end_time, search) -> [BotModel]:
        query = model.session.query(BotModel)
        if len(start_time) > 0 and len(end_time) > 0:
            query = query.filter(BotModel.createon.between(start_time, end_time))
        if len(search) > 0:
            conditions = [
                BotModel.name.like('%' + search + '%'),
                BotModel.pseudoname.like('%' + search + '%'),
                BotModel.nickname.like('%' + search + '%'),
                BotModel.email.like('%' + search + '%'),
                BotModel.phone.like('%' + search + '%'),
                BotModel.addr.like('%' + search + '%'),
                BotModel.shipaddr.like('%' + search + '%')
            ]
            query = query.filter(or_(*conditions))
        results = query.all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("BOTS fetchall" + json.dumps(dict_results))
        return results

    def find_all_bots(self) -> [BotModel]:
        results = model.session.query(BotModel).all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("BOTS fetchall" + json.dumps(dict_results))
        return results

    def update_bots_batch(self, api_bots):
        for i, api_bot in enumerate(api_bots):
            result = model.session.query(BotModel).filter(BotModel.botid == api_bot["bid"]).first()
            if result is not None:
                result.owner = api_bot["owner"]
                result.levels = api_bot["levels"]
                result.gender = api_bot["gender"]
                result.birthday = api_bot["birthday"]
                result.interests = api_bot["interests"]
                result.location = api_bot["location"]
                result.roles = api_bot["roles"]
                result.status = api_bot["status"]
                result.delDate = api_bot["delDate"]
                result.name = api_bot["name"]
                result.pseudoname = api_bot["pseudoname"]
                result.nickname = api_bot["nickname"]
                result.addr = api_bot["addr"]
                result.shipaddr = api_bot["shipaddr"]
                result.phone = api_bot["phone"]
                result.email = api_bot["email"]
                result.ebpw = api_bot["ebpw"]
                result.backemail = api_bot["backemail"]
                result.backemail_site = api_bot["backemail_site"]
                result.epw = api_bot["epw"]
                model.session.commit()
                self.parent.showMsg("update_bots_batch: " + json.dumps(result.to_dict()))

    def inset_bots_batch(self, bots, api_bots):
        for i, api_bot in enumerate(api_bots):
            bot = bots[i]
            insert_data = {
                "botid": bot["bid"],
                "owner": bot["owner"],
                "levels": bot["levels"],
                "gender": bot["gender"],
                "birthday": bot["birthday"],
                "interests": bot["interests"],
                "location": bot["location"],
                "roles": bot["roles"],
                "status": bot["status"],
                "delDate": bot["delDate"],
                "name": api_bot["name"],
                "pseudoname": api_bot["pseudoname"],
                "nickname": api_bot["nickname"],
                "addr": api_bot["addr"],
                "shipaddr": api_bot["shipaddr"],
                "phone": api_bot["phone"],
                "email": api_bot["email"],
                "epw": api_bot["epw"],
                "backemail": api_bot["backemail"],
                "ebpw": api_bot["ebpw"],
                "backemail_site": api_bot["backemail_site"]
            }
            new_mission_instance = MissionModel(**insert_data)
            model.session.add(new_mission_instance)
            model.session.commit()
            self.parent.showMsg("Mission fetchall" + json.dumps(new_mission_instance.to_dict()))

    def sync_cloud_bot_data(self, session, tokens):
        jresp = send_query_bots_request_to_cloud(session, tokens['AuthenticationResult']['IdToken'],
                                                 {"byowneruser": True})
        all_bots = json.loads(jresp['body'])
        for bot in all_bots:
            bid = bot['bid']
            result: BotModel = model.session.query(BotModel).filter(BotModel.botid == bid).first()
            insert = False
            if result is None:
                result = BotModel()
                insert = True
            result.botid = bot['bid']
            result.owner = bot['owner']
            result.levels = bot['levels']
            result.gender = bot['gender']
            result.birthday = bot['birthday']
            result.interests = bot['interests']
            result.location = bot['location']
            result.roles = bot['roles']
            result.status = bot['status']
            result.createon = bot['birthday']
            if insert:
                model.session.add(result)
        model.session.commit()

    def sync_cloud_mission_data(self, session, tokens):
        jresp = send_query_missions_request_to_cloud(session, tokens['AuthenticationResult']['IdToken'],
                                                     {"byowneruser": True})
        all_missions = json.loads(jresp['body'])
        for mission in all_missions:
            mid = mission['mid']
            local_mission = self.find_missions_by_mid(mid)
            insert = False
            if local_mission is None:
                local_mission = MissionModel()
                insert = True
            local_mission.mid = mid
            local_mission.ticket = mission['ticket']
            local_mission.botid = mission['botid']
            local_mission.status = mission['status']
            local_mission.createon = mission['createon']
            local_mission.esd = mission['esd']
            local_mission.ecd = mission['ecd']
            local_mission.asd = mission['asd']
            local_mission.abd = mission['abd']
            local_mission.aad = mission['aad']
            local_mission.afd = mission['afd']
            local_mission.acd = mission['acd']
            local_mission.est_start_time = mission['esttime']
            local_mission.est_runtime = mission['runtime']
            local_mission.owner = mission['owner']
            local_mission.cuspas = mission['cuspas']
            local_mission.category = mission['category']
            local_mission.phrase = mission['phrase']
            local_mission.pseudoStore = mission['pseudoStore']
            local_mission.pseudoBrand = mission['pseudoBrand']
            local_mission.pseudoASIN = mission['pseudoASIN']
            local_mission.type = mission['type']
            local_mission.config = str(mission['config'])
            local_mission.skills = mission['skills']
            local_mission.delDate = mission['delDate']
            if insert:
                model.session.add(local_mission)
        model.session.commit()
