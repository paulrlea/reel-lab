@echo off
setlocal
cd /d "%~dp0"
call "%~dp0Reel Lab.cmd" tag-footage "C:\ReelLab\incoming" --watch >> "%~dp0.runtime\footage-tagging.log" 2>&1
