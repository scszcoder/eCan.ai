import json
from datetime import datetime, timedelta

from sqlalchemy import MetaData,  inspect, delete, or_, Table, Column, Integer, String, Text, text

from Cloud import send_query_missions_request_to_cloud
import traceback
from bot.Logger import log3
from common.models.mission import MissionModel


class MissionService:
    def __init__(self, main_win, session):
        self.main_win = main_win
        self.session = session

    def find_missions_by_createon(self):
        current_time = datetime.now()
        three_days_ago = current_time - timedelta(days=3)
        missions = self.session.query(MissionModel).filter(MissionModel.createon >= three_days_ago).all()
        return missions

    def find_missions_by_mids(self, mids) -> [MissionModel]:
        results = self.session.query(MissionModel).filter(MissionModel.mid.in_(mids)).all()
        dict_results = [result.to_dict() for result in results]
        self.main_win.showMsg("Found Local DB Mission Row(s) by mids: " + json.dumps(dict_results), "debug")
        return results

    def find_missions_by_mid(self, mid) -> MissionModel:
        result: MissionModel = self.session.query(MissionModel).filter(MissionModel.mid == mid).first()
        if result is not None:
            self.main_win.showMsg("Found Local DB Mission Row(s) by mid: " + json.dumps(result.to_dict()), "debug")
        return result

    def find_missions_by_ticket(self, ticket) -> MissionModel:
        result: MissionModel = self.session.query(MissionModel).filter(MissionModel.ticket == ticket).first()
        if result is not None:
            self.main_win.showMsg("Found Local DB Mission Row(s) by ticket: " + json.dumps(result.to_dict()), "debug")
        return result

    def insert_missions_batch_(self, missions: [MissionModel]):
        self.session.add_all(missions)
        self.session.commit()
        dict_results = [result.to_dict() for result in missions]
        self.main_win.showMsg("Mission fetchall after batch insertion" + json.dumps(dict_results))

    def find_all_missions(self) -> [MissionModel]:
        results = self.session.query(MissionModel).all()
        dict_results = [result.to_dict() for result in results]
        self.main_win.showMsg("Missions fetchall after find all" + json.dumps(dict_results))
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
            local_mission.variations = messions["variations"]
            local_mission.rating = messions["rating"]
            local_mission.feedbacks = messions["feedbacks"]
            local_mission.price = messions["price"]
            local_mission.customer = messions["customer"]
            local_mission.platoon = messions["platoon"]
            local_mission.result = messions["result"]
            self.session.add(local_mission)
            self.main_win.showMsg("Mission fetchall" + json.dumps(local_mission.to_dict()))
        self.session.commit()

    def update_missions_by_id(self, api_missions):
        for i, amission in enumerate(api_missions):
            result = self.session.query(MissionModel).filter(MissionModel.mid == amission["amission"]).first()
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
            result.variations = amission["variations"]
            result.rating = amission["rating"]
            result.feedbacks = amission["feedbacks"]
            result.price = amission["price"]
            result.customer = amission["customer"]
            result.platoon = amission["platoon"]
            result.result = amission["result"]
            self.session.commit()
            self.main_win.showMsg("update row: " + json.dumps(result.to_dict()))

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
        self.main_win.showMsg("Missions fetchall" + json.dumps(dict_results))
        return results

    def delete_missions_by_mid(self, mid):
        delete_stmt = delete(MissionModel).where(MissionModel.mid == mid)
        # 执行删除
        result = self.session.execute(delete_stmt)
        self.session.commit()
        if result.rowcount() > 0:
            print(f"Mission with mid {mid} deleted successfully.")
        else:
            print(f"No Mission found with mid {mid} to delete.")

    def delete_missions_by_ticket(self, ticket):
        mission_instance = self.session.query(MissionModel).filter(MissionModel.ticket == ticket).one()
        if mission_instance is not None:
            self.session.delete(mission_instance)
            self.session.commit()
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
                self.session.add(local_mission)
        self.session.commit()

    def describe_table(self):
        # Connect to the database
        with model.engine.connect() as conn:
            # Use the Inspector to get table information
            inspector = inspect(model.engine)

            # Specify the table name you want to describe
            table_name = 'missions'

            # Get the columns of the table
            columns = inspector.get_columns(table_name)

            # Print the column information
            log3("missions Table column definitions:")
            for column in columns:
                log3(
                    f"Column: {column['name']}, Type: {column['type']}, Nullable: {column['nullable']}, Default: {column['default']}")

            return columns

    # original_table = Table(
    #     'missions', metadata,
    #     Column('mid', Integer, primary_key=True),
    #     Column('ticket', Integer),
    #     Column('botid', Integer),
    #     Column('status', Text),
    #     Column('createon', Text),
    #     Column('esd', Text),
    #     Column('ecd', Text),
    #     Column('asd', Text),
    #     Column('abd', Text),
    #     Column('aad', Text),
    #     Column('afd', Text),
    #     Column('acd', Text),
    #     Column('actual_start_time', Text),
    #     Column('est_start_time', Text),
    #     Column('actual_runtime', Text),
    #     Column('est_runtime', Text),
    #     Column('n_retries', Integer),
    #     Column('cuspas', Text),
    #     Column('category', Text),
    #     Column('phrase', Text),
    #     Column('pseudoStore', Text),
    #     Column('pseudoBrand', Text),
    #     Column('pseudoASIN', Text),
    #     Column('type', Text),
    #     Column('config', Text),
    #     Column('skills', Text),
    #     Column('delDate', Text),
    #     Column('asin', Text),
    #     Column('brand', Text),
    #     Column('title', Text),
    #     Column('rating', Text),
    #     Column('feedbacks', Text),
    #     Column('customer', Text),
    #     Column('platoon', Text),
    #     Column('result', Text)
    # )
    def add_column(self, new_column_name, new_column_data_type, after_column_name):
        print("missions Table adding column....")
        # metadata = MetaData(bind=model.engine)
        table_name = "missions"
        try:
            columns_info = self.describe_table()

            # Create list of columns for the new table
            new_columns = []
            added_new_column = False

            for column_info in columns_info:
                new_columns.append(Column(column_info['name'], column_info['type']))
                if column_info['name'] == after_column_name:
                    new_columns.append(Column(new_column_name, new_column_data_type))
                    added_new_column = True

            if not added_new_column:
                raise ValueError(f"Column '{after_column_name}' not found in table '{table_name}'")

            # Define the new table schema
            table_name = "missions_old"
            new_table_name = "missions_new"
            new_table = Table(new_table_name, model.Base.metadata, *new_columns)

            # with model.engine.connect() as conn:
            # Rename the original table
            self.session.execute(text(f"DROP TABLE {table_name}"))
            original_table_name = "missions"
            self.session.execute(text(f"ALTER TABLE {original_table_name} RENAME TO {table_name}"))

            # Create the new table with the desired column order
            model.Base.metadata.create_all(model.engine, tables=[new_table])

            # Copy data from the old table to the new table
            columns_to_copy = [col.name for col in new_table.columns if col.name != new_column_name]
            columns_to_copy_str = ', '.join(columns_to_copy)
            self.session.execute(text(f"""
                INSERT INTO {new_table_name} ({columns_to_copy_str})
                SELECT {columns_to_copy_str} FROM {table_name}
            """))

            # Drop the old table
            self.session.execute(text("DROP TABLE missions_old;"))

            # Rename the new table to the original table name
            self.session.execute(text("ALTER TABLE missions_new RENAME TO missions;"))

            self.session.commit()

            self.describe_table()

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddColumnToMissionsTable:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddColumnToMissionsTable: traceback information not available:" + str(e)
            print(ex_stat)

    def drop_column(self, col_name):
        # metadata = MetaData(bind=model.engine)
        table_name = "missions"
        try:
            columns_info = self.describe_table()

            # Create list of columns for the new table
            new_columns = []

            for column_info in columns_info:
                new_columns.append(Column(column_info['name'], column_info['type']))
                if column_info['name'] != col_name:
                    new_columns.append(Column(column_info['name'], column_info['type']))
                    added_new_column = True

            if len(new_columns) == len(columns_info):
                raise ValueError(f"Column '{col_name}' not found in table '{table_name}'")

            # Define the new table schema
            table_name = "missions_old"
            new_table_name = "missions_new"
            new_table = Table(new_table_name, model.Base.metadata, *new_columns)

            with model.engine.connect() as conn:
                # Rename the original table
                self.session.execute(text("DROP TABLE missions_old;"))
                self.session.execute(text("ALTER TABLE missions RENAME TO missions_old;"))

                # Create the new table with the desired column order
                model.Base.metadata.create_all(model.engine, tables=[new_table])

                # Copy data from the old table to the new table
                columns_to_copy = [col.name for col in new_table.columns]
                columns_to_copy_str = ', '.join(columns_to_copy)
                self.session.execute(text(f"""
                            INSERT INTO {new_table_name} ({columns_to_copy_str})
                            SELECT {columns_to_copy_str} FROM {table_name}
                        """))

                # Drop the old table
                self.session.execute(text("DROP TABLE missions_old;"))

                # Rename the new table to the original table name
                self.session.execute(text("ALTER TABLE missions_new RENAME TO missions;"))

                self.session.commit()

                self.describe_table()

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDeleteColumnFromMissionsTable:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorDeleteColumnFromMissionsTable: traceback information not available:" + str(e)
            print(ex_stat)