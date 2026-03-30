#!/bin/bash
# Offline 환경에서 단독 실행 가능한 파일 빌드 스크립트
# 사전 요구: pip install pyinstaller

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "filelist 단독 실행 파일 빌드 중..."
pyinstaller --onefile --name filelist filelist.py

echo ""
echo "빌드 완료: dist/filelist"
ls -lh dist/filelist
