@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   AviaWatch - inicializacao local
echo ========================================
echo.

REM --- Pre-requisitos ---
where python >nul 2>&1
if errorlevel 1 (
  echo [erro] Python nao encontrado no PATH.
  echo        Instale Python 3.11+ em https://www.python.org/downloads/
  echo        Marque a opcao "Add python.exe to PATH" na instalacao.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [erro] npm / Node.js nao encontrado no PATH.
  echo        Instale Node.js 20+ LTS em https://nodejs.org/
  pause
  exit /b 1
)

REM --- Backend: venv ---
if not exist "back\venv\Scripts\python.exe" (
  echo [back] Criando ambiente virtual Python...
  python -m venv "back\venv"
  if errorlevel 1 (
    echo [erro] Falha ao criar venv.
    pause
    exit /b 1
  )
)

call "back\venv\Scripts\activate.bat"

REM Instala deps so se faltar pacote essencial (evita demora a cada start)
back\venv\Scripts\python.exe -c "import fastapi,uvicorn,cv2,dotenv,requests,cryptography,numpy,multipart" >nul 2>&1
if errorlevel 1 (
  echo [back] Instalando dependencias Python ^(primeira vez pode demorar^)...
  python -m pip install --upgrade pip
  pip install -r "back\requirements.txt"
  if errorlevel 1 (
    echo [erro] Falha ao instalar dependencias do backend.
    pause
    exit /b 1
  )
) else (
  echo [back] Dependencias Python OK.
)

REM ultralytics e opcional na subida da API; tenta instalar se faltar
back\venv\Scripts\python.exe -c "import ultralytics" >nul 2>&1
if errorlevel 1 (
  echo [back] Instalando ultralytics ^(IA^)...
  pip install "ultralytics>=8.3.0"
  if errorlevel 1 (
    echo [aviso] ultralytics nao instalou. A API sobe, mas a deteccao YOLO ficara off.
  )
)

if not exist "back\.env" (
  if exist "back\.env.example" (
    copy /Y "back\.env.example" "back\.env" >nul
    echo [back] Arquivo .env criado a partir de .env.example
  )
)

REM --- Frontend ---
if not exist "front\node_modules\vite" (
  echo [front] Instalando dependencias Node.js ^(primeira vez^)...
  pushd front
  call npm install
  if errorlevel 1 (
    echo [erro] Falha ao instalar dependencias do frontend.
    popd
    pause
    exit /b 1
  )
  popd
) else (
  echo [front] Dependencias Node.js OK.
)

REM --- Libera porta 8000 se outro processo estiver ocupando ---
powershell -NoProfile -Command "try { $cs = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop; foreach ($c in $cs) { Write-Host ('[aviso] Encerrando PID ' + $c.OwningProcess + ' na porta 8000'); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch { }"

REM --- Libera porta 5173 se necessario ---
powershell -NoProfile -Command "try { $cs = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction Stop; foreach ($c in $cs) { Write-Host ('[aviso] Encerrando PID ' + $c.OwningProcess + ' na porta 5173'); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch { }"

ping -n 2 127.0.0.1 >nul

echo.
echo [start] Iniciando uvicorn ^(API^) e Vite ^(UI^) simultaneamente...
echo.

start "AviaWatch Backend" /D "%~dp0back" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "AviaWatch Frontend" /D "%~dp0front" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"

echo [check] Aguardando API em http://127.0.0.1:8000/api/health ...
set /a _tries=0

:wait_api
set /a _tries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto api_ok
if %_tries% GEQ 40 (
  echo [aviso] A API ainda nao respondeu. Veja a janela "AviaWatch Backend".
  goto wait_front
)
ping -n 3 127.0.0.1 >nul
goto wait_api

:api_ok
echo [check] API OK.

:wait_front
echo [check] Aguardando frontend em http://127.0.0.1:5173 ...
set /a _tries=0

:wait_ui
set /a _tries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto ui_ok
if %_tries% GEQ 30 (
  echo [aviso] O frontend ainda nao respondeu. Veja a janela "AviaWatch Frontend".
  goto print_urls
)
ping -n 3 127.0.0.1 >nul
goto wait_ui

:ui_ok
echo [check] Frontend OK.
start "" "http://127.0.0.1:5173"

:print_urls
echo.
echo ========================================
echo   AviaWatch em execucao
echo ========================================
echo   PAINEL ^(abra este^):  http://127.0.0.1:5173
echo   Backend API:          http://127.0.0.1:8000/api/health
echo   Docs da API:          http://127.0.0.1:8000/docs
echo ========================================
echo.
echo IMPORTANTE: o painel e a porta 5173 ^(nao a 8000^).
echo A porta 8000 e so a API.
echo.
echo Duas janelas precisam ficar abertas:
echo   - AviaWatch Backend
echo   - AviaWatch Frontend
echo.
pause
endlocal
