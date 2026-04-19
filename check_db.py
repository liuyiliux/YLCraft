import sqlite3
c = sqlite3.connect(r'F:\PycharmProjects\YLCraft\backend\data\ylcraft.db')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables:", tables)
for t in tables:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(f"  {t}: {cols}")
