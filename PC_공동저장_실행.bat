@echo off
chcp 65001 >nul
cd /d "%~dp0"
title HDC 인허가 검토 - PC 공동 저장
echo.
echo 인허가 검토관리 PC 서버를 시작합니다.
echo PC를 꺼도 이전 기록은 삭제되지 않습니다.
echo.
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 server\start_lan.py
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        python server\start_lan.py
    ) else (
        echo Python 3.10 이상이 필요합니다.
        echo 기존 V9 프로그램에서 사용한 Python을 설치 또는 연결해 주세요.
    )
)
echo.
echo 종료되었습니다. 창을 닫으셔도 됩니다.
pause
