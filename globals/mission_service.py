import json
from datetime import datetime, timedelta

from sqlalchemy import delete, or_

from Cloud import send_query_missions_request_to_cloud
from globals import model
from globals.model import MissionModel


class MissionService:
    def __init__(self, parent):
        self.parent = parent

    def find_missions_by_createon(self):
        current_time = datetime.now()
        three_days_ago = current_time - timedelta(days=3)
        missions = model.session.query(MissionModel).filter(MissionModel.createon >= three_days_ago).all()
        return missions

    def find_missions_by_mids(self, mids) -> [MissionModel]:
        results = model.session.query(MissionModel).filter(MissionModel.mid.in_(mids)).all()
        dict_results = [result.to_dict() for result in results]
        self.parent.showMsg("Just Added Local DB Mission Row(s): " + json.dumps(dict_results), "debug")
        return results

    def find_missions_by_mid(self, mid) -> MissionModel:
        result: MissionModel = model.session.query(MissionModel).filter(MissionModel.mid == mid).first()
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
            local_mission = MissionModel()
            local_mission.mid = jb["mid"]
            local_mission.ticket = jb["ticket"]
            local_mission.botid = jb["botid"]
            local_mission.status = jb["status"]
            local_mission.createon = jb["createon"]
            local_mission.esd = jb["esd"]
            local_mission.ecd = jb["ecd"]
            local_mission.asd = jb["asd"]
            local_mission.abd = jb["abd"]
            local_mission.aad = jb["aad"]
            local_mission.afd = jb["afd"]
            local_mission.acd = jb["acd"]
            local_mission.actual_start_time = messions["actual_start_time"]
            local_mission.est_start_time = jb["esttime"]
            local_mission.actual_runtime = messions["actual_run_time"]
            local_mission.est_runtime = jb["runtime"]
            local_mission.n_retries = messions["n_retries"]
            local_mission.cuspas = jb["cuspas"]
            local_mission.category = jb["category"]
            local_mission.phrase = jb["phrase"]
            local_mission.pseudoStore = jb["pseudoStore"]
            local_mission.pseudoBrand = jb["pseudoBrand"]
            local_mission.pseudoASIN = jb["pseudoASIN"]
            local_mission.type = jb["type"]
            local_mission.config = str(jb["config"])
            local_mission.skills = str(jb["skills"])
            local_mission.delDate = jb["delDate"]
            local_mission.asin = messions["asin"]
            local_mission.store = messions["store"]
            local_mission.brand = messions["brand"]
            local_mission.img = messions["image"]
            local_mission.title = messions["title"]
            local_mission.rating = messions["rating"]
            local_mission.feedbacks = messions["feedbacks"]
            local_mission.price = messions["price"]
            local_mission.customer = messions["customer"]
            local_mission.platoon = messions["platoon"]
            local_mission.result = messions["result"]
            model.session.add(local_mission)
            self.parent.showMsg("Mission fetchall" + json.dumps(local_mission.to_dict()))
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
            result.actual_start_time = amission['actual_start_time']
            result.est_start_time = amission['est_start_time']
            result.actual_run_time = amission['actual_run_time']
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
