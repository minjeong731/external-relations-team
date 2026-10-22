@echo off
setlocal EnableExtensions
chcp 65001 >nul
title HDC 인허가 검토 - HTTPS 웹 공유
set "HDC_SHARED_ROOT=%LOCALAPPDATA%\HDC_Permit_SharedWeb"
echo.
echo ===========================================================
echo 인허가 검토관리 - HTTPS 웹주소 연결
echo 직원들은 BAT 실행 / 별도 설치 필요 없음
echo 이 PC에서 한 번 실행하고 고정 HTTPS 주소를 확인하세요.
echo ===========================================================
echo.
where py >nul 2>&1
if not errorlevel 1 (
 set "PYEXE=py"
 set "PYOPT=-3"
 goto :download
)
where python >nul 2>&1
if not errorlevel 1 (
 set "PYEXE=python"
 set "PYOPT="
 goto :download
)
echo [오류] Python 3.10 이상을 찾지 못했습니다.
echo 기존 공동저장 프로그램을 실행했던 PC에서 실행해 주세요.
pause
exit /b 1

:download
echo 기존 GitHub 프로젝트의 최신 코드를 이 PC에 동기화합니다...
"%PYEXE%" %PYOPT% -c "import os,pathlib,urllib.request; base='https://raw.githubusercontent.com/minjeong731/external-relations-team/main/'; root=pathlib.Path(os.environ['HDC_SHARED_ROOT']); files=('server/app.py','server/start_lan.py','server/lan_app.py','server/start_https.py','docs/index.html','docs/live-api.js','docs/runtime-config.js'); [(p.parent.mkdir(parents=True,exist_ok=True),urllib.request.urlretrieve(base+name,p)) for name in files for p in (root/pathlib.Path(name),)]; print('프로그램 코드 동기화 완료:', root)"
if errorlevel 1 (
 echo [오류] 프로그램 코드를 다운로드하지 못했습니다.
 echo 회사 네트워크에서 githubusercontent.com 접속이 허용되는지 확인하세요.
 pause
 exit /b 1
)
echo.
echo 이 PC를 HTTPS 저장 서버로 실행합니다.
echo 기존 접수 기록은 그대로 유지됩니다.
echo.
"%PYEXE%" %PYOPT% "%HDC_SHARED_ROOT%\server\start_https.py"
echo.
echo HTTPS 저장 서버가 종료됐습니다.
pause
endlocal
