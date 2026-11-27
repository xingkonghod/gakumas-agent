import re, sys
from pathlib import Path
t = Path(r"%TEMP%\AppData\Local\Temp\dsh-spill-V03Zs9\session-77f45b917fb9\705a76897104-web_fetch.txt").read_text(encoding="utf-8", errors="replace")
names = list(dict.fromkeys(re.findall(r'"full_name":"matto49/([^"]+)"', t)))
rel = [n for n in names if any(k in n.lower() for k in ("gkms", "gakumas", "cli", "engine", "contest"))]
sys.stdout.buffer.write(("related: " + str(rel) + "\n").encode())
sys.stdout.buffer.write(("all(" + str(len(names)) + "): " + ", ".join(names) + "\n").encode())