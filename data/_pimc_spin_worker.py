import time,os,sys
p=sys.argv[1]
while True:
    try:
        if open(p).read().strip()=='1': break
    except Exception: pass
    x=0
    for i in range(200000): x+=i*i
