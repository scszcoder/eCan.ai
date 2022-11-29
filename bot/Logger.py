import sqlite3

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


def log_1(msg, category='None', mask='None', file='None'):
    # read details from the page.
    if file == 'None':
        print(msg)
    else:
        file1 = open(file, "a")
        file1.write(msg)
        file1.close()


def log2file(msg, category='None', mask='None', file='None'):
    # read details from the page.
    if file == 'None':
        print(msg)
    else:
        file1 = open(file, "a")
        print(msg)
        file1.write(msg)
        file1.close()