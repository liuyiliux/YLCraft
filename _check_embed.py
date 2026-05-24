import psycopg2
pg = psycopg2.connect("host=localhost port=5432 dbname=ylcraft user=ylcraft password=ylcraft_dev")
cur = pg.cursor()

# 查 embedding
cur.execute("SELECT id, name, provider, provider_type, default_model, embedding_dimension, normalize_embeddings, is_active FROM ai_connectors WHERE provider_type = 'embedding'")
rows = cur.fetchall()
print(f"--- embedding 连接器 ({len(rows)} 条) ---")
if rows:
    for r in rows:
        print(f"  {r[1]} | provider={r[2]} | model={r[4]} | dim={r[5]} | active={r[7]}")
else:
    print("  (无)")

# 总数
cur.execute("SELECT count(*) FROM ai_connectors")
total = cur.fetchone()[0]
print(f"\n总记录数: {total}")

# 按类型统计
cur.execute("SELECT provider_type, count(*) FROM ai_connectors GROUP BY provider_type")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

cur.close()
pg.close()
