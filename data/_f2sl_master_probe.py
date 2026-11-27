import sqlite3, json, zlib, os
db = r'D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite'
con = sqlite3.connect(db)
print('tables:', [r[0] for r in con.execute("select name from sqlite_master where type='table'")])
print('schema:', [r for r in con.execute('pragma table_info(records)')])
row = con.execute("select row_id, variant, payload from records where table_name='ProduceCard' limit 1").fetchone()
print('row_id:', row[0], 'variant:', row[1])
p = json.loads(zlib.decompress(row[2]).decode('utf-8'))
print('payload keys:', list(p.keys())[:25])
print('has decoded?', 'decoded' in p, 'has outer?', 'outer' in p)
print(json.dumps(p, ensure_ascii=False)[:700])
print('n tables:', con.execute('select count(distinct table_name) from records').fetchone()[0])
names = [r[0] for r in con.execute('select distinct table_name from records order by 1')]
print('table names:', names)
# existing jsonl masters anywhere?
for root in (r'D:\Games\gakumas-agent\data', r'D:\Games\gakumas-agent\integrations'):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git', 'node_modules', '__pycache__', 'episodes', 'runs')]
        if 'ProduceCard.jsonl' in filenames:
            print('FOUND jsonl:', os.path.join(dirpath, 'ProduceCard.jsonl'))
