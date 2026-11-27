import httpx
r = httpx.get('https://hiro.matto.top/gkbench/api/leaderboard', params={'set': 'hif', 'kind': 'template'}, timeout=60)
rows = r.json()
rows = rows if isinstance(rows, list) else rows.get('rows', [])
rows.sort(key=lambda x: -(x.get('mean') or 0))
for x in rows[:12]:
    print(f"{x.get('mean'):>12,.0f}  n={x.get('n'):>4}  sees={x.get('sees_seed')}  {x.get('label')}")