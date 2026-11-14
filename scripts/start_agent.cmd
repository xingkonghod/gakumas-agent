@echo off
schtasks /Run /TN GDEAgent
echo GDEAgent started (admin, no UAC)
