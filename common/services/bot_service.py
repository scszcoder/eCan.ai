import json

from sqlalchemy import inspect, delete, or_

from Cloud import send_query_bots_request_to_cloud
from common.db_init import sync_table_columns
from common.models.bot import BotModel
from utils.logger_helper import logger_helper


class BotService:
    def __init__(self, main_win, session):
        self.main_win = main_win
        self.session = session
        sync_table_columns(BotModel, "bots")

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
                result.createon = api_bot["createon"]
                result.vehicle = api_bot["vehicle"]
                self.session.commit()
                self.main_win.showMsg("update_bots_batch: " + json.dumps(result.to_dict()))

    def insert_bots_batch(self, bots, api_bots):
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
            local_bot.createon = api_bot["createon"]
            local_bot.vehicle = api_bot["vehicle"]
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
            if insert:
                self.session.add(result)
        self.session.commit()

    def describe_table(self):
        inspector = inspect(BotModel)
        # 打印表结构信息
        print(f"{BotModel.__tablename__} Table column definitions:")
        for column in inspector.columns:
            logger_helper.debug(
                f"Column: {column['name']}, Type: {column['type']}, Nullable: {column['nullable']}, Default: {column['default']}")
        return inspector.columns
