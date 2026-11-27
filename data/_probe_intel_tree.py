"""解析 auto-gakumas 仓库树 spill 文件：非图片文件清单（只读情报）。"""
import json, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
t = io.open(r"%TEMP%\AppData\Local\Temp\dsh-spill-OsVGe4\session-b5dd753ea583\f9bb192bd56b-web_fetch.txt", encoding="utf-8").read()
s = t.find('{"sha"')
e = t.rfind("}")
d = json.loads(t[s:e + 1])
paths = [x["path"] for x in d["tree"] if x["type"] == "blob"]
print("total blobs:", len(paths), "truncated:", d.get("truncated"))
nonimg = [p for p in paths if not p.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
print("non-image:", len(nonimg))
for p in nonimg:
    print(p)
tops = sorted({p.split("/")[0] for p in paths})
print("top-level:", tops)