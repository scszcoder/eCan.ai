import sqlite3
conn = sqlite3.connect('scszsj_gmail_com/ecan_base.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print('Tables:', tables)
print('Has token_usage:', 'token_usage' in tables)
conn.close()
