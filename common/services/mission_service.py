import json
from datetime import datetime, timedelta

from sqlalchemy import MetaData,  inspect, delete, or_, tuple_, Table, Column, Integer, String, Text, text, TEXT, REAL, INTEGER

from agent.cloud_api.cloud_api import send_query_missions_by_time_request_to_cloud, send_query_manager_missions_request_to_cloud
from common.db_init import sync_table_columns
from common.models.mission import MissionModel
from utils.logger_helper import logger_helper as logger

MISSION_TABLE_DEF = [ {'name': 'mid', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'ticket', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'botid', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'status', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'createon', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'esd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'ecd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'asd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'abd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'aad', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'afd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'acd', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'actual_start_time', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'est_start_time', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'actual_runtime', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'est_runtime', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                          {'name': 'n_retries', 'type': 'INTEGER', 'nullable': True, 'default': 3},
                          {'name': 'cuspas', 'type': 'TEXT', 'nullable': True, 'default': "win,ads,amz"},
                          {'name': 'category', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'phrase', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'pseudoStore', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'pseudoBrand', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'pseudoASIN', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'type', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'config', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'skills', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'delDate', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'asin', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'stores', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'follow_seller', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'brand', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'img', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'title', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'variations', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'rating', 'type': 'REAL', 'nullable': True, 'default': 0.0},
                          {'name': 'feedbacks', 'type': 'INTEGER', 'nullable': True, 'default': -1},
                          {'name': 'price', 'type': 'REAL', 'nullable': True, 'default': 0.0},
                          {'name': 'follow_price', 'type': 'REAL', 'nullable': True, 'default': 0.0},
                          {'name': 'fingerprint_profile', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'customer', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'platoon', 'type': 'TEXT', 'nullable': True, 'default': ""},
                          {'name': 'result', 'type': 'TEXT', 'nullable': True, 'default': ""},
                        {'name': 'as_server', 'type': 'INTEGER', 'nullable': True, 'default': 0},
                        {'name': 'original_req_file', 'type': 'TEXT', 'nullable': True, 'default': ""}
                     ]


class MissionService:
    def __init__(self, main_win, session, engine=None):
        self.main_win = main_win
        self.session = session
        self.engine = engine
        # Pass engine parameter to sync_table_columns
        sync_table_columns(MissionModel, 'missions', engine)

    def find_missions_by_createon(self):
        current_time = datetime.now()
        some_days_ago = current_time - timedelta(days=7)
        missions = self.session.query(MissionModel).filter(MissionModel.createon >= some_days_ago).all()
        #by default we need to get manager missions too....
        manager_missions = self.session.query(MissionModel).filter(or_(
                MissionModel.type.ilike("%manage%"),
                MissionModel.type.ilike("%admin%")
            )).all()

        # ✅ Merge both lists, ensuring uniqueness by `mid`
        merged_missions = {mission.mid: mission for mission in missions}  # Store existing missions
        for mission in manager_missions:
            merged_missions[mission.mid] = mission  # Overwrite if already present

        # Convert dictionary back to a list
        final_missions = list(merged_missions.values())

        return final_missions

    def find_missions_by_mids(self, mids) -> [MissionModel]:
        results = self.session.query(MissionModel).filter(MissionModel.mid.in_(mids)).all()
        dict_results = [result.to_dict() for result in results]
        # self.main_win.showMsg("Found Local DB Mission Row(s) by mids: " + json.dumps(dict_results), "debug")
        return results

    def find_missions_by_mid(self, mid) -> MissionModel:
        result: MissionModel = self.session.query(MissionModel).filter(MissionModel.mid == mid).first()
        if result is not None:
            junk =0
            # self.main_win.showMsg("Found Local DB Mission Row(s) by mid: " + json.dumps(result.to_dict()), "debug")
        return result

    def find_missions_by_asin_srcs(self, m_asin_srcs) -> [MissionModel]:
        """
            Queries the MISSIONS table to find rows matching the given list of dictionaries.
            Each dictionary must have 'asin' and 'src' keys.
            """
        logger.debug("find_missions_by_asin_srcs...")
        if not m_asin_srcs:
            logger.warning("❌ No input data provided.")
            return []

        # Convert the input JSON list into a query filter
        filters = [(item["asin"], item["src"]) for item in m_asin_srcs]

        # Query using SQLAlchemy ORM
        results = self.session.query(MissionModel).filter(
            tuple_(
                MissionModel.asin, MissionModel.original_req_file
            ).in_(filters)
        ).all()

        # Convert results to a list of dictionaries
        mrows = [mission.to_dict() for mission in results]
        logger.debug("mrows...", mrows)
        return mrows

    def find_missions_by_ticket(self, ticket) -> MissionModel:
        result: MissionModel = self.session.query(MissionModel).filter(MissionModel.ticket == ticket).first()
        if result is not None:
            junk = 0
            # self.main_win.showMsg("Found Local DB Mission Row(s) by ticket: " + json.dumps(result.to_dict()), "debug")
        return result.to_dict()

    def find_missions_by_orders(self, order_files) -> [MissionModel]:
        results: [MissionModel] = self.session.query(MissionModel).filter(MissionModel.original_req_file.in_(order_files)).all()
        dict_results = [result.to_dict() for result in results]
        if results is not None:
            junk = 0
            # self.main_win.showMsg("Found Local DB Mission Row(s) by order files: " + json.dumps(dict_results), "debug")
        return dict_results

    def insert_missions_batch_(self, missions: [MissionModel]):
        self.session.add_all(missions)
        self.session.commit()
        dict_results = [result.to_dict() for result in missions]
        if len(dict_results) > 3:
            logger.debug("type of dict_results:", type(dict_results))
            self.main_win.showMsg("Mission fetchall after batch insertion" + json.dumps(dict_results[:2]) + ".........")
        else:
            self.main_win.showMsg("Mission fetchall after batch insertion" + json.dumps(dict_results))

    def find_all_missions(self) -> [MissionModel]:
        results = self.session.query(MissionModel).all()
        dict_results = [result.to_dict() for result in results]
        if len(dict_results) > 3:
            self.main_win.showMsg("Mission fetchall after batch insertion" + json.dumps(dict_results[:2])) + "........."
        else:
            self.main_win.showMsg("Mission fetchall after batch insertion" + json.dumps(dict_results))
        return dict_results

    def insert_missions_batch(self, jbody, api_missions):
        for i, jb in enumerate(jbody):
            mission = api_missions[i]
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
            local_mission.actual_start_time = mission["actual_start_time"]
            local_mission.est_start_time = jb["esttime"]
            local_mission.actual_runtime = mission["actual_run_time"]
            local_mission.est_runtime = jb["runtime"]
            local_mission.n_retries = mission["n_retries"]
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
            local_mission.asin = mission["asin"]
            local_mission.store = mission["stores"]
            local_mission.brand = mission["brand"]
            local_mission.img = mission["image"]
            local_mission.title = mission["title"]
            local_mission.variations = mission["variations"]
            local_mission.rating = mission["rating"]
            local_mission.feedbacks = mission["feedbacks"]
            local_mission.price = mission["price"]
            local_mission.customer = mission["customer"]
            local_mission.platoon = mission["platoon"]
            local_mission.result = mission["result"]
            local_mission.follow_seller = mission["follow_seller"]
            local_mission.follow_price = mission["follow_price"]
            local_mission.fingerprint_profile = mission["fingerprint_profile"]
            local_mission.as_server = mission["as_server"]
            local_mission.original_req_file = mission["original_req_file"]
            self.session.add(local_mission)
            # self.main_win.showMsg("Mission fetchall" + json.dumps(local_mission.to_dict()))
        self.session.commit()


    def update_missions_by_id(self, api_missions):
        for i, amission in enumerate(api_missions):
            result = self.session.query(MissionModel).filter(MissionModel.mid == amission["mid"]).first()
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
            result.store = amission["stores"]
            result.brand = amission["brand"]
            result.image = amission["image"]
            result.title = amission["title"]
            result.variations = amission["variations"]
            result.rating = amission["rating"]
            result.feedbacks = amission["feedbacks"]
            result.price = amission["price"]
            result.customer = amission["customer"]
            result.platoon = amission["platoon"]
            result.result = amission["result"]
            result.follow_seller = amission["follow_seller"]
            result.follow_price = amission["follow_price"]
            result.fingerprint_profile = amission["fingerprint_profile"]
            result.as_server = amission["as_server"]
            result.original_req_file = amission["original_req_file"]
            self.session.commit()
            # self.main_win.showMsg("update row: " + json.dumps(result.to_dict()))

    def find_missions_by_search(self, start_time, end_time, search) -> [MissionModel]:
        query = self.session.query(MissionModel)
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
        # self.main_win.showMsg("Missions fetchall" + json.dumps(dict_results))
        return results

    def delete_missions_by_mid(self, mid):
        delete_stmt = delete(MissionModel).where(MissionModel.mid == mid)
        # Execute deletion
        result = self.session.execute(delete_stmt)
        logger.debug("result:", result)
        self.session.commit()
        if result.rowcount > 0:
            logger.debug(f"Mission with mid {mid} deleted successfully.")
        else:
            logger.debug(f"No Mission found with mid {mid} to delete.")

    def delete_missions_by_ticket(self, ticket):
        mission_instance = self.session.query(MissionModel).filter(MissionModel.ticket == ticket).one()
        if mission_instance is not None:
            self.session.delete(mission_instance)
            self.session.commit()
        return mission_instance

    def delete_missions_by_order(self, order_files):
        mission_instances = self.session.query(MissionModel).filter(MissionModel.original_req_file.in_(order_files)).all()
        if mission_instances:
            deleted_count = self.session.query(MissionModel).filter(MissionModel.original_req_file.in_(order_files)).delete(synchronize_session=False)
            self.session.commit()
        return mission_instances

    def sync_cloud_mission_data(self, session, auth_token, mwin):

        logger.debug("sending query missions.....")
        jresp = send_query_missions_by_time_request_to_cloud(session, auth_token,
                                                     [{"byowneruser": True}], mwin.getWanApiEndpoint())
        logger.debug("jresp:", type(jresp), jresp)
        
        # Handle different response formats
        if isinstance(jresp, list):
            # New format: direct list (empty list for no data)
            all_missions = jresp
        elif isinstance(jresp, dict) and 'body' in jresp:
            # Old format: dict with 'body' key
            if jresp['body']:
                if isinstance(jresp['body'], str):  # If it's a string, parse it
                    all_missions = json.loads(jresp['body'])
                else:  # If it's already a list, use it as is
                    all_missions = jresp['body']
            else:
                all_missions = []
        else:
            # Fallback: empty list
            logger.warning(f"Unexpected jresp format: {type(jresp)}, using empty list")
            all_missions = []

        jresp = send_query_manager_missions_request_to_cloud(session, auth_token,
                                                     [{"byowneruser": True}], mwin.getWanApiEndpoint())
        logger.debug("manager missions::", jresp)
        
        # Handle manager missions response format
        if isinstance(jresp, list):
            manager_missions = jresp
        elif isinstance(jresp, dict) and 'body' in jresp:
            manager_missions = jresp['body'] if jresp['body'] else []
        else:
            logger.warning(f"Unexpected manager missions format: {type(jresp)}, using empty list")
            manager_missions = []
            
        allmids = [m["mid"] for m in all_missions]
        for m in manager_missions:
            if m not in allmids:
                all_missions.append(m)

        # print("all missions:", all_missions)
        # all_missions = jresp['body']

        for mi, mission in enumerate(all_missions):
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
            # print("midx:", mi, mission["mid"])
            # if mi == 84:
            #     print("mm:", mission)
            local_mission.as_server = mission['as_server']
            if insert:
                self.session.add(local_mission)
        self.session.commit()

    def describe_table(self):
        inspector = inspect(MissionModel)
        # Print table structure information
        logger.debug(f"{MissionModel.__tablename__} Table column definitions: ")
        columns = inspector.columns
        for column in columns:
            logger.debug(
                f"Column: {column.name}, Type: {column.type}, Nullable: {column.nullable}, Default: {column.default}")
        return columns