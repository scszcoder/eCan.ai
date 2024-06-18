import json

from sqlalchemy import MetaData,  inspect, delete, or_, Table, Column, Integer, String, Text, text

from Cloud import send_query_bots_request_to_cloud
from common.models.bot import BotModel
import traceback
from common.db_init import Base
from bot.Logger import log3

class BotService:
    def __init__(self, main_win, session, engine):
        self.main_win = main_win
        self.session = session
        self.engine = engine

    def delete_bots_by_botid(self, botid):
        # 构建删除表达式
        delete_stmt = delete(BotModel).where(BotModel.botid == botid)
        # 执行删除
        result = self.session.execute(delete_stmt)
        self.session.commit()
        if result.rowcount() > 0:
            print(f"Bot with botid {botid} deleted successfully.")
        else:
            print(f"No bot found with botid {botid} to delete.")

    def find_bots_by_search(self, start_time, end_time, search) -> [BotModel]:
        query = self.session.query(BotModel)
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
        self.main_win.showMsg("BOTS fetchall" + json.dumps(dict_results))
        return results

    def find_all_bots(self) -> [BotModel]:
        results = self.session.query(BotModel).all()
        dict_results = [result.to_dict() for result in results]
        self.main_win.showMsg("BOTS fetchall" + json.dumps(dict_results))
        return results

    def update_bots_batch(self, api_bots):
        for i, api_bot in enumerate(api_bots):
            result = self.session.query(BotModel).filter(BotModel.botid == api_bot["bid"]).first()
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
                self.session.commit()
                self.main_win.showMsg("update_bots_batch: " + json.dumps(result.to_dict()))

    def inset_bots_batch(self, bots, api_bots):
        for i, api_bot in enumerate(api_bots):
            bot = bots[i]
            local_bot = BotModel()
            local_bot.botid = bot["bid"]
            local_bot.owner = bot["owner"]
            local_bot.levels = bot["levels"]
            local_bot.gender = bot["gender"]
            local_bot.birthday = bot["birthday"]
            local_bot.interests = bot["interests"]
            local_bot.location = bot["location"]
            local_bot.roles = bot["roles"]
            local_bot.status = bot["status"]
            local_bot.delDate = bot["delDate"]
            local_bot.name = api_bot["name"]
            local_bot.pseudoname = api_bot["pseudoname"]
            local_bot.nickname = api_bot["nickname"]
            local_bot.addr = api_bot["addr"]
            local_bot.shipaddr = api_bot["shipaddr"]
            local_bot.phone = api_bot["phone"]
            local_bot.email = api_bot["email"]
            local_bot.epw = api_bot["epw"]
            local_bot.backemail = api_bot["backemail"]
            local_bot.backemail_site = api_bot["backemail_site"]
            local_bot.ebpw = api_bot["ebpw"]
            self.session.add(local_bot)
            self.session.commit()
            self.main_win.showMsg("Mission fetchall" + json.dumps(local_bot.to_dict()))

    def sync_cloud_bot_data(self, session, tokens):
        jresp = send_query_bots_request_to_cloud(session, tokens['AuthenticationResult']['IdToken'],
                                                 {"byowneruser": True})
        all_bots = json.loads(jresp['body'])
        for bot in all_bots:
            bid = bot['bid']
            result: BotModel = self.session.query(BotModel).filter(BotModel.botid == bid).first()
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
            # result.createon = bot['createon']
            if insert:
                self.session.add(result)
        self.session.commit()

    def describe_table(self):
        # Connect to the database
        with self.engine.connect() as conn:
            # Use the Inspector to get table information
            inspector = inspect(self.engine)

            # Specify the table name you want to describe
            table_name = 'bots'

            # Get the columns of the table
            columns = inspector.get_columns(table_name)

            # Print the column information
            log3("bots Table column definitions:")
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
        print("bots Table adding column....")
        # metadata = MetaData(bind=model.engine)
        table_name = "bots"
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
            table_name = "bots_old"
            new_table_name = "bots_new"
            new_table = Table(new_table_name, Base.metadata, *new_columns)

            # with model.engine.connect() as conn:
            # Rename the original table
            # self.session.execute(text(f"DROP TABLE {table_name}"))
            original_table_name = "bots"
            self.session.execute(text(f"ALTER TABLE {original_table_name} RENAME TO {table_name}"))

            # Create the new table with the desired column order
            Base.metadata.create_all(self.engine, tables=[new_table])

            # Copy data from the old table to the new table
            columns_to_copy = [col.name for col in new_table.columns if col.name != new_column_name]
            columns_to_copy_str = ', '.join(columns_to_copy)
            self.session.execute(text(f"""
                INSERT INTO {new_table_name} ({columns_to_copy_str})
                SELECT {columns_to_copy_str} FROM {table_name}
            """))

            # Drop the old table
            self.session.execute(text("DROP TABLE bots_old;"))

            # Rename the new table to the original table name
            self.session.execute(text("ALTER TABLE bots_new RENAME TO bots;"))

            self.session.commit()

            self.describe_table()

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddColumnToBotsTable:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddColumnToBotsTable: traceback information not available:" + str(e)
            print(ex_stat)

    def add_last_column(self, new_column_name, new_column_data_type):
        # Construct the SQL command to add a column
        try:
            sql_command = text(f"ALTER TABLE bots ADD COLUMN {new_column_name} {new_column_data_type}")
            self.session.execute(sql_command)
            self.session.commit()
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddLastColumnToBotsTable:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddLastColumnToBotsTable: traceback information not available:" + str(e)
            print(ex_stat)


    def drop_column(self, col_name):
        # metadata = MetaData(bind=model.engine)
        table_name = "bots"
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
            table_name = "bots_old"
            new_table_name = "bots_new"
            new_table = Table(new_table_name, Base.metadata, *new_columns)

            with self.engine.connect() as conn:
                # Rename the original table
                self.session.execute(text("DROP TABLE bots_old;"))
                self.session.execute(text("ALTER TABLE bots RENAME TO bots_old;"))

                # Create the new table with the desired column order
                Base.metadata.create_all(self.engine, tables=[new_table])

                # Copy data from the old table to the new table
                columns_to_copy = [col.name for col in new_table.columns]
                columns_to_copy_str = ', '.join(columns_to_copy)
                self.session.execute(text(f"""
                            INSERT INTO {new_table_name} ({columns_to_copy_str})
                            SELECT {columns_to_copy_str} FROM {table_name}
                        """))

                # Drop the old table
                self.session.execute(text("DROP TABLE bots_old;"))

                # Rename the new table to the original table name
                self.session.execute(text("ALTER TABLE bots_new RENAME TO bots;"))

                self.session.commit()

                self.describe_table()

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDeleteColumnFromBotsTable:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorDeleteColumnFromBotsTable: traceback information not available:" + str(e)
            print(ex_stat)