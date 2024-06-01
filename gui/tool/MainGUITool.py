import json
import os
import sqlite3


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
    return sqlite3.connect(dbfile)


class SqlProcessor:
    def __init__(self, parent):
        self.parent = parent
        self.dbcon = init_sql_file(parent.dbfile)
        self.dbCursor = self.dbcon.cursor()
        self.create_bots_table()
        self.create_skills_table()
        self.create_missions_table()
        self.create_products_table()

    def create_skills_table(self):
        sql = 'CREATE TABLE IF NOT EXISTS  skills (skid INTEGER PRIMARY KEY, owner TEXT, platform TEXT, app TEXT, applink TEXT, site TEXT, sitelink TEXT, name TEXT, path TEXT, runtime TEXT, price_model TEXT, price INTEGER, privacy TEXT)'
        self.dbCursor.execute(sql)

    def insert_skill(self, api_skills):
        sql = ''' INSERT INTO skills (skid, owner, platform, app, site, name, path, runtime, price_model, price, privacy)
                                                   VALUES(?,?,?,?,?,?,?,?,?,?,?); '''
        data_tuple = (
            api_skills["skid"], api_skills["owner"], api_skills["platform"],
            api_skills["app"], api_skills["site"], api_skills["name"],
            api_skills["path"], api_skills["runtime"], api_skills["price_model"],
            api_skills["price"], api_skills["privacy"])
        self.dbCursor.execute(sql, data_tuple)
        sql = 'SELECT * FROM skills'
        res = self.dbCursor.execute(sql)
        self.parent.showMsg("fetchall" + json.dumps(res.fetchall()))

    def create_products_table(self):
        sql = 'CREATE TABLE IF NOT EXISTS  products (pid INTEGER PRIMARY KEY, name TEXT, title TEXT, asin TEXT, variation TEXT, site TEXT, sku TEXT, size_in TEXT, weight_lbs REAL, condition TEXT, fullfiller TEXT, price INTEGER, cost INTEGER, inventory_loc TEXT, inventory_qty TEXT)'
        self.dbCursor.execute(sql)

    def find_all_products(self):
        sql = 'SELECT * FROM products'
        self.dbCursor.execute(sql)
        db_data = self.dbCursor.fetchall()
        self.parent.showMsg("fetchall" + json.dumps(db_data))
        return db_data

    def create_missions_table(self):
        sql = 'CREATE TABLE IF NOT EXISTS  missions (mid INTEGER PRIMARY KEY, ticket INTEGER, botid INTEGER, status TEXT, createon TEXT, esd TEXT, ecd TEXT, asd TEXT, abd TEXT, aad TEXT, afd TEXT, acd TEXT, actual_start_time TEXT, est_start_time TEXT, actual_runtime TEXT, est_runtime TEXT, n_retries INTEGER, cuspas TEXT, category TEXT, phrase TEXT, pseudoStore TEXT, pseudoBrand TEXT, pseudoASIN TEXT, type TEXT, config TEXT, skills TEXT, delDate TEXT, asin TEXT, store TEXT, brand TEXT, img TEXT, title TEXT, rating REAL, feedbacks INTEGER, price REAL, customer TEXT, platoon TEXT, result TEXT, FOREIGN KEY(botid) REFERENCES bots(botid))'
        self.dbCursor.execute(sql)

    def find_missions_by_createon(self):
        sql = """
                    SELECT * FROM missions
                    WHERE createon >= date('now', '-3 days')
                    """
        res = self.dbCursor.execute(sql)

        db_data = res.fetchall()
        return db_data

    def find_missions_by_mids(self, mids):
        result = ', '.join(map(str, mids))
        sql = f"SELECT * FROM missions WHERE mid IN ({result})"
        self.parent.showMsg("Select Missions by mid: " + sql, "debug")
        self.dbCursor.execute(sql)
        db_data = self.dbCursor.fetchall()
        self.parent.showMsg("Just Added Local DB Mission Row(s): " + json.dumps(db_data), "debug")

    def insert_missions_batch_(self, api_missions):
        sql = ''' INSERT INTO missions (mid, ticket, botid, status, createon, esd, ecd, asd, abd, aad, afd, 
                                                acd, actual_start_time, est_start_time, actual_runtime, est_runtime, n_retries, 
                                                cuspas, category, phrase, pseudoStore, pseudoBrand, pseudoASIN, type, config, 
                                                skills, delDate, asin, store, brand, img,  title, rating, feedbacks, price, customer, 
                                                platoon, result) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
        data_tuple = (api_missions[0]["mid"], api_missions[0]["ticket"], api_missions[0]["owner"],
                      api_missions[0]["botid"], api_missions[0]["status"],
                      api_missions[0]["createon"],
                      api_missions[0]["esd"], api_missions[0]["ecd"], api_missions[0]["asd"],
                      api_missions[0]["abd"], api_missions[0]["aad"],
                      api_missions[0]["afd"], api_missions[0]["acd"],
                      api_missions[0]["actual_start_time"],
                      api_missions[0]["esttime"], api_missions[0]["actual_runtime"],
                      api_missions[0]["runtime"],
                      api_missions[0]["n_retries"], api_missions[0]["cuspas"],
                      api_missions[0]["category"],
                      api_missions[0]["phrase"], api_missions[0]["pseudoStore"],
                      api_missions[0]["pseudoBrand"], api_missions[0]["pseudoASIN"],
                      api_missions[0]["type"], api_missions[0]["config"],
                      api_missions[0]["skills"], api_missions[0]["delDate"],
                      api_missions[0]["asin"],
                      api_missions[0]["store"], api_missions[0]["brand"],
                      api_missions[0]["image"], api_missions[0]["title"], api_missions[0]["rating"],
                      api_missions[0]["feedbacks"], api_missions[0]["price"],
                      api_missions[0]["customer"],
                      api_missions[0]["platoon"], api_missions[0]["result"])

        self.dbCursor.execute(sql, data_tuple)
        self.find_missions()

    def find_missions(self):
        sql = 'SELECT * FROM missions'
        self.dbCursor.execute(sql)
        db_data = self.dbCursor.fetchall()
        self.parent.showMsg("Missions fetchall" + json.dumps(db_data))
        return db_data

    def insert_missions_batch(self, jbody, api_missions):
        sql = ''' INSERT INTO missions (mid, ticket, botid, status, createon, esd, ecd, asd, abd, aad, afd, acd, actual_start_time, est_start_time, actual_runtime,
                            est_runtime, n_retries, cuspas, category, phrase, pseudoStore, pseudoBrand, pseudoASIN, type, config, skills, delDate, asin, store, brand, img, 
                            title, rating, feedbacks, price, customer, platoon, result) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''

        data_tuple = []
        for i, jb in enumerate(jbody):
            data_tuple.append(
                (jbody[i]["mid"], jbody[i]["ticket"], jbody[i]["botid"], jbody[i]["status"], jbody[i]["createon"],
                 jbody[i]["esd"], jbody[i]["ecd"], jbody[i]["asd"], jbody[i]["abd"], jbody[i]["aad"],
                 jbody[i]["afd"], jbody[i]["acd"], api_missions[i]["actual_start_time"], jbody[i]["esttime"],
                 api_missions[i]["actual_run_time"], jbody[i]["runtime"],
                 api_missions[i]["n_retries"], jbody[i]["cuspas"], jbody[i]["category"], jbody[i]["phrase"],
                 jbody[i]["pseudoStore"],
                 jbody[i]["pseudoBrand"], jbody[i]["pseudoASIN"], jbody[i]["type"], jbody[i]["config"],
                 jbody[i]["skills"], jbody[i]["delDate"], api_missions[i]["asin"], api_missions[i]["store"],
                 api_missions[i]["brand"],
                 api_missions[i]["image"], api_missions[i]["title"], api_missions[i]["rating"],
                 api_missions[i]["feedbacks"], api_missions[i]["price"],
                 api_missions[i]["customer"], api_missions[i]["platoon"], api_missions[i]["result"]))

        self.dbCursor.executemany(sql, data_tuple)
        if self.dbCursor.rowcount == len(jbody):
            self.parent.showMsg("New Mission SQLite DB Insertion successful.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("Insertion failed.")

    def update_missions_by_ticket(self, api_missions):
        # update local DB
        sql = ''' UPDATE missions SET ticket = ?, botid = ?, status = ?, createon = ?, esd = ?, ecd = ?, asd = ?, abd = ?, 
                                aad = ?, afd = ?, acd = ?, actual_start_time = ?, est_start_time = ?, actual_runtime = ?, est_runtime = ?, 
                                n_retries = ?, cuspas = ?, category = ?, phrase = ?, pseudoStore = ?, pseudoBrand = ?, 
                                pseudoASIN = ?, type = ?, config = ?, skills = ?, delDate = ?, asin = ?, store = ?, brand = ?, 
                                img = ?, title = ?, rating = ?, feedbacks = ?, price = ?, customer = ?, platoon = ?, result = ? WHERE mid = ?; '''
        data_tuple = []
        for i, amission in enumerate(api_missions):
            data_tuple.append((
                api_missions[i]["ticket"], api_missions[i]["botid"], api_missions[i]["status"],
                api_missions[i]["createon"],
                api_missions[i]["esd"], api_missions[i]["ecd"], api_missions[i]["asd"], api_missions[i]["abd"],
                api_missions[i]["aad"],
                api_missions[i]["afd"], api_missions[i]["acd"], api_missions[i]["actual_start_time"],
                api_missions[i]["est_start_time"], api_missions[i]["actual_run_time"],
                api_missions[i]["est_run_time"],
                api_missions[i]["n_retries"], api_missions[i]["cuspas"], api_missions[i]["search_cat"],
                api_missions[i]["search_kw"], api_missions[i]["pseudo_store"],
                api_missions[i]["pseudo_brand"], api_missions[i]["pseudo_asin"], api_missions[i]["type"],
                api_missions[i]["config"],
                api_missions[i]["skills"], api_missions[i]["delDate"], api_missions[i]["asin"],
                api_missions[i]["store"], api_missions[i]["brand"],
                api_missions[i]["image"], api_missions[i]["title"], api_missions[i]["rating"],
                api_missions[i]["feedbacks"], api_missions[i]["price"], api_missions[i]["customer"],
                api_missions[i]["platoon"], api_missions[i]["result"], api_missions[i]["mid"]))

        self.dbCursor.executemany(sql, data_tuple)
        # Check if the UPDATE query was successful
        self.parent.showMsg("data_tuple:" + ", ".join(str(x) for x in data_tuple) + ")")
        self.parent.showMsg("update row count: " + str(self.dbCursor.rowcount))
        if self.dbCursor.rowcount > 0:
            self.parent.showMsg(f"{self.dbCursor.rowcount} row(s) updated successfully.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("No rows were updated.", "warn")
    def find_missions_by_search(self, startTime, endTime, search):
        sql = 'SELECT * FROM missions where 1=1'
        if len(startTime) > 0 and len(endTime) > 0:
            sql += ' AND createon BETWEEN ' + startTime + ' AND ' + endTime
        if len(search)>0:
            sql += ' AND (asin LIKE "%' + search + '%" OR store LIKE "%' + search + '%" OR brand LIKE "%' + search + '%" OR title LIKE "%' + search + '%" OR pseudoStore LIKE "%' + search + '%" OR pseudoBrand LIKE "%' + search + '%" OR pseudoASIN LIKE "%' + search + '%")'
        res = self.dbCursor.execute(sql)
        data = res.fetchall()
        self.parent.showMsg("mission fetchall" + json.dumps(data))
        return data

    def delete_missions_by_mid(self, mid):
        sql = f"DELETE FROM missions WHERE mid = {mid}"
        self.dbCursor.execute(sql)
        # Check if the DELETE query was successful
        if self.dbCursor.rowcount > 0:
            self.parent.showMsg(f"{self.dbCursor.rowcount} mission row(s) deleted successfully.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("No mission rows were deleted.")

    def delete_missions_by_ticket(self, ticket):
        sql = f"DELETE FROM missions WHERE ticket = {ticket}"
        self.parent.showMsg("find_original_buy sql:" + sql, "debug")
        self.dbCursor.execute(sql)
        return self.dbCursor.fetchall()

    ### BOTS ####
    def create_bots_table(self):
        sql = "CREATE TABLE IF NOT EXISTS bots (botid INTEGER PRIMARY KEY, owner TEXT, levels TEXT, gender TEXT, birthday TEXT, interests TEXT, location TEXT, roles TEXT, status TEXT, delDate TEXT, name TEXT, pseudoname TEXT, nickname TEXT, addr TEXT, shipaddr TEXT, phone TEXT, email TEXT, epw TEXT, backemail TEXT, ebpw TEXT, backemail_site TEXT)"
        self.dbCursor.execute(sql)

    def delete_bots_by_botid(self, botid):
        sql = f"DELETE FROM bots WHERE botid = {botid};"
        self.dbCursor.execute(sql)
        # Check if the DELETE query was successful
        if self.dbCursor.rowcount > 0:
            self.parent.showMsg(f"{self.dbCursor.rowcount} row(s) deleted successfully.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("No rows were deleted.")

    def find_bot_by_botid(self, botid_list):
        result = ', '.join(map(str, botid_list))
        sql = f"SELECT * FROM bots WHERE botid IN ({result})"
        self.parent.showMsg("Select Bots by botid: " + sql, "debug")
        self.dbCursor.execute(sql)
        db_data = self.dbCursor.fetchall()
        self.parent.showMsg("Just Added Local DB Bot Row(s): " + json.dumps(db_data), "debug")
        return db_data
    def find_bots_by_search(self, startTime, endTime, search):
        sql = 'SELECT * FROM bots where 1=1'
        if len(startTime) > 0 and len(endTime) > 0:
            sql += ' AND createon BETWEEN ' + startTime + ' AND ' + endTime
        if len(search) > 0:
            sql += ' AND (name LIKE "%' + search + '%" OR pseudoname LIKE "%' + search + '%" OR nickname LIKE "%' + search + '%" OR email LIKE "%' + search + '%" OR phone LIKE "%' + search + '%" OR addr LIKE "%' + search + '%" OR shipaddr LIKE "%' + search + '%")'
        res = self.dbCursor.execute(sql)
        data = res.fetchall()
        self.parent.showMsg("BOTS fetchall" + json.dumps(data))
        return data

    def find_all_bots(self):
        sql = 'SELECT * FROM bots'
        res = self.dbCursor.execute(sql)
        data = res.fetchall()
        self.parent.showMsg("BOTS fetchall" + json.dumps(data))
        return data

    def update_bots_batch(self, api_bots):
        sql = ''' UPDATE bots SET owner = ?, levels = ?, gender = ?, birthday = ?, interests = ?, location = ?, roles = ?,
                                status = ?, delDate = ?, name = ?, pseudoname = ?, nickname = ?, addr = ?, shipaddr = ?, phone = ?, 
                                email = ?,  epw = ?, backemail = ?, ebpw = ? , backemail_site = ?WHERE botid = ?; '''

        data_tuple = []
        for i, api_bot in enumerate(api_bots):
            data_tuple.append(
                (api_bots[i]["owner"], api_bots[i]["levels"], api_bots[i]["gender"], api_bots[i]["birthday"],
                 api_bots[i]["interests"], api_bots[i]["location"], api_bots[i]["roles"], api_bots[i]["status"],
                 api_bots[i]["delDate"], api_bots[i]["name"], api_bots[i]["pseudoname"], api_bots[i]["nickname"],
                 api_bots[i]["addr"],
                 api_bots[i]["shipaddr"], api_bots[i]["phone"], api_bots[i]["email"], api_bots[i]["epw"],
                 api_bots[i]["backemail"],
                 api_bots[i]["ebpw"], api_bots[i]["backemail_site"], api_bots[i]["bid"]))

        self.dbCursor.executemany(sql, data_tuple)
        # Check if the UPDATE query was successful
        if self.dbCursor.rowcount > 0:
            self.parent.showMsg(f"{self.dbCursor.rowcount} row(s) updated successfully.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("No rows were updated.")

    def inset_bots_batch(self, bots, api_bots):
        sql = """INSERT INTO bots (botid, owner, levels, gender, birthday, interests, location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr, phone, email, epw, backemail, ebpw, backemail_site) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        data_tuple = []
        for j in range(len(bots)):
            newbot = bots[j]
            data_tuple.append(
                (newbot["bid"], newbot["owner"], newbot["levels"], newbot["gender"], newbot["birthday"],
                 newbot["interests"], newbot["location"], newbot["roles"], newbot["status"], newbot["delDate"],
                 api_bots[j]["name"], api_bots[j]["pseudoname"], api_bots[j]["nickname"], api_bots[j]["addr"],
                 api_bots[j]["shipaddr"],
                 api_bots[j]["phone"], api_bots[j]["email"], api_bots[j]["epw"], api_bots[j]["backemail"],
                 api_bots[j]["ebpw"], api_bots[j]["backemail_site"]))
        self.parent.showMsg("bot insert SQL:[" + sql + "] DATA TUPLE:(" + ", ".join(str(x) for x in data_tuple) + ")")
        self.dbCursor.executemany(sql, data_tuple)

        # Check if the INSERT query was successful
        if self.dbCursor.rowcount == len(bots):
            self.parent.showMsg("New Bot SQLite DB Insertion successful.")
            self.dbcon.commit()
        else:
            self.parent.showMsg("Insertion failed.", "error")
