"""P1-7：p_items.json 改前/改后逐条 diff + implemented 统计（不提交）。"""
import json
import io
import collections

old = {it["id"]: it for it in json.load(open("data/_p17_pitems_head.json", encoding="utf-8"))["items"]}
new_d = json.load(open("data/knowledge/p_items.json", encoding="utf-8"))
new = {it["id"]: it for it in new_d["items"]}
out = io.open("data/_p17_diff_out.txt", "w", encoding="utf-8")

import sys
sys.path.insert(0, "src")
from gkagent.sim.p_items import record_to_specs

def impl_count(items):
    return sum(sum(1 for s in record_to_specs(it) if s.implemented) for it in items.values())

out.write(f"implemented old={impl_count(old)} new={impl_count(new)} / specs {sum(len(it['effects']) for it in new.values())}\n")
out.write(f"stats.effects_modifier old={json.load(open('data/_p17_pitems_head.json',encoding='utf-8'))['stats'].get('effects_modifier')} new={new_d['stats'].get('effects_modifier')}\n")

changed = []
delay_added = []
for iid, nit in new.items():
    oit = old.get(iid)
    if oit is None:
        changed.append((iid, "NEW ITEM"))
        continue
    if oit != nit:
        changed.append((iid, nit.get("name")))
    # delay annotations
    for e in nit.get("effects", []):
        if e.get("delay_turns"):
            delay_added.append((iid, nit.get("name"), e["type"], e["delay_turns"]))

out.write(f"\nchanged records: {len(changed)}\n")
for iid, name in changed:
    out.write(f"  {iid} | {name}\n")
    oit = old.get(iid, {})
    nit = new[iid]
    oe = oit.get("effects", [])
    ne = nit.get("effects", [])
    for i, e in enumerate(ne):
        o = oe[i] if i < len(oe) else {}
        if o != e:
            out.write(f"    [{i}] {e['type']}: old target={o.get('target')!r} values={json.dumps(o.get('values',{}),ensure_ascii=False)} delay={o.get('delay_turns')}\n")
            out.write(f"        new target={e.get('target')!r} values={json.dumps(e.get('values',{}),ensure_ascii=False)} delay={e.get('delay_turns')}\n")

out.write(f"\ndelay_turns annotated segments: {len(delay_added)}\n")
for row in delay_added:
    out.write(f"  {row}\n")
out.close()
print("written data/_p17_diff_out.txt")
