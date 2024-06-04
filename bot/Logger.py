from datetime import datetime
from bot.envi import getECBotDataHome
import os

# con = sqlite3.connect("mylog.db")
# cur = con.cursor()
# res = cur.execute("CREATE TABLE runHis(action, bid, mid)")
# con.commit()
# cur.executemany()
#
# sql_statement = "INSERT INTO *** VALUES (), (), ()"
# sql_statement = "SELECT score, abc FROM movies ORDER BY year"
#
# res.fetchone()
# res.fetchall()
# res.fetchmany()
# con.close()

LOG_SWITCH_BOARD = {
    "all": True
}

# log messages into console, file, and GUI
def log3(msg, category='None', mask='all',gui_main=None):
    log_enabled = False
    if LOG_SWITCH_BOARD["all"]:
        log_enabled = True
    elif mask in LOG_SWITCH_BOARD:
        if LOG_SWITCH_BOARD[mask]:
            log_enabled = True

    if log_enabled:
        ecb_data_homepath = getECBotDataHome()
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dailyLogDir = ecb_data_homepath + "/runlogs/{}".format(year)
        dailyLogFile = ecb_data_homepath + "/runlogs/{}/log{}{}{}.txt".format(year, year, month, day)
        time = now.strftime("%H:%M:%S - ")
        if os.path.isfile(dailyLogFile):
            file1 = open(dailyLogFile, "a")  # append mode

            file1.write(time + msg + "\n")
            file1.close()
        else:
            if not os.path.exists(dailyLogDir):
                os.makedirs(dailyLogDir)

            file1 = open(dailyLogFile, "w")  # append mode

            file1.write(time + msg + "\n")
            file1.close()

        # read details from the page.
        print(msg)

        if gui_main:
            gui_main.appendNetLogs([msg])


def log2file(msg, category='None', mask='None', file='None'):
    # read details from the page.
    if file == 'None':
        print(msg)
    else:
        file1 = open(file, "a")
        print(msg)
        file1.write(msg)
        file1.close()