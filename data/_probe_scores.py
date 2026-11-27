import json, urllib.request, sys
for kind, setname in [("template", "hif"), ("template", "hajime")]:
    url = f"https://hiro.matto.top/gkbench/api/leaderboard?set={setname}&kind={kind}"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "p"}), timeout=60).read())
    sys.stdout.buffer.write((f"=== {setname} {kind} ===\n").encode())
    for r in d:
        lab = str(r.get("label", ""))
        if "gkagent" in lab.lower():
            mean = r.get("mean") or 0
            sys.stdout.buffer.write((f"  {lab:30s} mean={mean:>12,.0f} n={r.get('n')} over={r.get('over')} err={r.get('errors')} sees={r.get('about',{}).get('sees')}\n").encode())