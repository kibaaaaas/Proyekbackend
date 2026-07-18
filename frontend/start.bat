@echo off
echo Starting Frontend Server...
echo Buka http://localhost:3000 di browser
python -m http.server 3000 -d %~dp0..
