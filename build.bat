@echo off
REM Offline 환경에서 단독 실행 가능한 파일 빌드 스크립트 (Windows)
REM 사전 요구: pip install pyinstaller

echo filelist.exe 단독 실행 파일 빌드 중...
pyinstaller --onefile --name filelist filelist.py

echo.
echo 빌드 완료: dist\filelist.exe
dir dist\filelist.exe
