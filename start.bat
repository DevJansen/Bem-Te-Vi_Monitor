@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM =====================================================================
REM  Caminhos absolutos.
REM
REM  IMPORTANTE: o Bem-Te-Vi chama SEMPRE "%PY%" -m <modulo> — nunca
REM  "activate.bat", "pip.exe", "uvicorn.exe" ou "yolo.exe". Esses arquivos
REM  gravam o caminho absoluto da pasta em que o venv foi criado; se o
REM  projeto for movido/copiado (ex.: de Documentos para C:\DevJansen), eles
REM  continuam apontando para a pasta antiga e quebram a inicializacao.
REM  O python.exe do venv, ao contrario, funciona de qualquer pasta.
REM =====================================================================
set "ROOT=%~dp0"
set "PY=%ROOT%back\venv\Scripts\python.exe"
set "REQ_FILE=back\requirements.txt"
set "REQ_STAMP=back\venv\.requirements.sha256"
set "PKG_LOCK=front\package-lock.json"
set "NPM_STAMP=front\node_modules\.package-lock.sha256"
set "STARTUP_LOG=back\startup.log"

REM Saida UTF-8 no console (evita acentos corrompidos nos logs da IA).
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ========================================
echo   Bem-Te-Vi - inicializacao local
echo ========================================
echo.

REM =====================================================================
REM  1. Pre-requisitos (Python 3.11+ e Node.js/npm no PATH)
REM =====================================================================
where python >nul 2>&1
if errorlevel 1 goto :fail_python

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto :fail_python_version

where npm >nul 2>&1
if errorlevel 1 goto :fail_npm

REM =====================================================================
REM  2. Backend: ambiente virtual Python
REM =====================================================================
if not exist "%PY%" (
  echo [back] Criando ambiente virtual Python...
  python -m venv "back\venv"
  if errorlevel 1 goto :fail_venv
)

REM Sanidade: o interpretador do venv precisa executar de verdade.
"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [back] Ambiente virtual invalido; recriando em back\venv...
  rmdir /s /q "back\venv" 2>nul
  python -m venv "back\venv"
  if errorlevel 1 goto :fail_venv
  "%PY%" -c "import sys" >nul 2>&1
  if errorlevel 1 goto :fail_venv
)

REM =====================================================================
REM  3. Backend: dependencias Python
REM     Instala sempre que o requirements.txt mudar (comparacao por hash).
REM     Uma falha de rede no pip NAO aborta a inicializacao se os imports
REM     essenciais continuarem funcionando — o painel abre normalmente.
REM =====================================================================
set "REQ_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "if (Test-Path '%REQ_FILE%') { (Get-FileHash -Algorithm SHA256 '%REQ_FILE%').Hash }"`) do set "REQ_HASH=%%H"
set "REQ_HASH_OLD="
if exist "%REQ_STAMP%" set /p REQ_HASH_OLD=<"%REQ_STAMP%"

if not "%REQ_HASH%"=="" if /i "%REQ_HASH%"=="%REQ_HASH_OLD%" goto :backend_ok

echo [back] Instalando/atualizando dependencias Python ^(a primeira vez pode demorar^)...
"%PY%" -m pip install --upgrade pip --disable-pip-version-check
"%PY%" -m pip install -r "%REQ_FILE%" --disable-pip-version-check
if not errorlevel 1 >"%REQ_STAMP%" echo %REQ_HASH%
goto :backend_check

:backend_ok
echo [back] Dependencias Python OK.

REM Sanidade: garante que os imports essenciais resolvem de fato.
:backend_check
"%PY%" -c "import fastapi, uvicorn, cv2, dotenv, requests, cryptography, numpy, multipart, pydantic, slowapi, fpdf, imageio_ffmpeg" >nul 2>&1
if not errorlevel 1 goto :backend_ready

echo [back] Dependencias incompletas detectadas; reinstalando...
"%PY%" -m pip install -r "%REQ_FILE%" --disable-pip-version-check
if not errorlevel 1 >"%REQ_STAMP%" echo %REQ_HASH%

"%PY%" -c "import fastapi, uvicorn, cv2, dotenv, requests, cryptography, numpy, multipart, pydantic, slowapi, fpdf, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 goto :fail_pip

:backend_ready
REM A IA de deteccao (ultralytics) e opcional na subida da API: sem ela o painel
REM abre, mas a deteccao YOLO fica desativada. Avisa em vez de abortar.
"%PY%" -c "import ultralytics" >nul 2>&1
if not errorlevel 1 goto :backend_ultralytics_ok
echo [aviso] ultralytics nao instalou. O painel abre, mas a deteccao YOLO ficara off.
echo         Para tentar de novo: "%PY%" -m pip install ultralytics
:backend_ultralytics_ok

if not exist "back\.env" (
  if exist "back\.env.example" (
    copy /Y "back\.env.example" "back\.env" >nul
    echo [back] Arquivo .env criado a partir de .env.example
  )
)

REM FFmpeg: o sistema usa o do PATH/winget ou, se faltar, o embutido no pacote
REM Python (imageio-ffmpeg). Este aviso e apenas informativo.
where ffmpeg >nul 2>&1
if errorlevel 1 echo [info] FFmpeg do sistema nao encontrado no PATH; usando o embutido (audio/BirdNET).

REM =====================================================================
REM  4. Frontend: dependencias Node.js
REM     Mesma logica: reinstala quando o package-lock.json mudar.
REM =====================================================================
set "PKG_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "if (Test-Path '%PKG_LOCK%') { (Get-FileHash -Algorithm SHA256 '%PKG_LOCK%').Hash }"`) do set "PKG_HASH=%%H"
set "PKG_HASH_OLD="
if exist "%NPM_STAMP%" set /p PKG_HASH_OLD=<"%NPM_STAMP%"

if not exist "front\node_modules\vite" goto :npm_install
if "%PKG_HASH%"=="" goto :npm_install
if /i "%PKG_HASH%"=="%PKG_HASH_OLD%" goto :front_ok

:npm_install
echo [front] Instalando/atualizando dependencias Node.js ^(a primeira vez pode demorar^)...
pushd front
call npm install --no-audit --no-fund
set "NPM_EXIT=%errorlevel%"
popd
if "%NPM_EXIT%"=="0" goto :npm_done
if exist "front\node_modules\vite\bin\vite.js" (
  echo [aviso] npm install retornou erro, mas as dependencias ja estao presentes. Continuando.
  goto :front_ready
)
goto :fail_node

:npm_done
if not "%PKG_HASH%"=="" >"%NPM_STAMP%" echo %PKG_HASH%
goto :front_ready

:front_ok
echo [front] Dependencias Node.js OK.

:front_ready

REM =====================================================================
REM  5. Libera portas 8000 (API) e 5173 (painel), se estiverem ocupadas
REM =====================================================================
powershell -NoProfile -Command "try { $cs = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop; foreach ($c in $cs) { Write-Host ('[aviso] Encerrando PID ' + $c.OwningProcess + ' na porta 8000'); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch { }"

powershell -NoProfile -Command "try { $cs = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction Stop; foreach ($c in $cs) { Write-Host ('[aviso] Encerrando PID ' + $c.OwningProcess + ' na porta 5173'); Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch { }"

ping -n 2 127.0.0.1 >nul

echo.
echo [start] Iniciando uvicorn ^(API^) e Vite ^(UI^) simultaneamente...
echo.

REM Usa o python.exe do venv pelo caminho absoluto (sem activate.bat): assim a
REM janela funciona mesmo que o projeto tenha sido movido de pasta.
start "Bem-Te-Vi Backend" /D "%ROOT%back" cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Bem-Te-Vi Frontend" /D "%ROOT%front" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"

echo [check] Aguardando API em http://127.0.0.1:8000/api/health ...
set /a _tries=0

:wait_api
set /a _tries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto api_ok
if %_tries% GEQ 40 (
  echo [aviso] A API ainda nao respondeu. Veja a janela "Bem-Te-Vi Backend".
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
  echo [aviso] O frontend ainda nao respondeu. Veja a janela "Bem-Te-Vi Frontend".
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
echo   Bem-Te-Vi em execucao
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
echo   - Bem-Te-Vi Backend
echo   - Bem-Te-Vi Frontend
echo.
pause
endlocal
exit /b 0

REM =====================================================================
REM  Tratamento de erros (mensagens claras em pt-BR)
REM =====================================================================
:fail_python
echo [erro] Python nao encontrado no PATH.
echo        Instale Python 3.11+ em https://www.python.org/downloads/
echo        Marque a opcao "Add python.exe to PATH" na instalacao.
echo        Depois abra um terminal NOVO e rode o start.bat de novo.
goto :fail_end

:fail_python_version
echo [erro] A versao do Python encontrada e antiga.
python --version
echo        O Bem-Te-Vi exige Python 3.11 ou superior.
echo        Instale a versao atual em https://www.python.org/downloads/
goto :fail_end

:fail_npm
echo [erro] npm / Node.js nao encontrado no PATH.
echo        Instale Node.js 20+ LTS em https://nodejs.org/
echo        Depois abra um terminal NOVO e rode o start.bat de novo.
goto :fail_end

:fail_venv
echo [erro] Falha ao criar o ambiente virtual em back\venv.
echo        Verifique o espaco em disco e as permissoes da pasta.
goto :fail_end

:fail_pip
echo [erro] Dependencias Python ausentes e a instalacao falhou.
echo        Verifique sua conexao com a internet e tente de novo:
echo        "%PY%" -m pip install -r back\requirements.txt
echo        (dica: se o projeto foi movido, apague back\venv e rode de novo)
goto :fail_end

:fail_node
echo [erro] Falha ao instalar as dependencias Node.js.
echo        Verifique sua conexao com a internet e tente de novo:
echo        cd front ^&^& npm install
goto :fail_end

:fail_end
echo.
echo A inicializacao foi interrompida.
echo Se precisar de ajuda, copie a mensagem acima.
pause
endlocal
exit /b 1
