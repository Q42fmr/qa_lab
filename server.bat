@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title qa_lab server

rem ==== налаштування ====
set "PORT=8030"
set "APPDIR=%~dp0"
set "UVICORN=uvicorn"
set "ARGS=app:app --reload --port %PORT% --timeout-graceful-shutdown 3"

rem режим: server.bat [start|restart|stop|status], без аргументів -> меню
set "CMD=%~1"
if /i "%CMD%"=="start"   goto start
if /i "%CMD%"=="restart" goto restart
if /i "%CMD%"=="stop"    goto stop
if /i "%CMD%"=="status"  goto status
goto menu

:menu
cls
echo ==============================
echo   qa_lab server (порт %PORT%)
echo ==============================
call :isup
if "!UP!"=="1" (echo   статус: ПРАЦЮЄ  PID !PID!) else (echo   статус: зупинено)
echo.
echo   [1] Запустити
echo   [2] Рестарт
echo   [3] Зупинити
echo   [4] Оновити статус
echo   [0] Вийти
echo.
set /p "choice=Вибір: "
if "%choice%"=="1" goto start
if "%choice%"=="2" goto restart
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto menu
if "%choice%"=="0" exit /b 0
goto menu

rem ---- чи піднятий сервер: ставить UP=1 і PID ----
rem Лише ЖИВИЙ власник порту: Windows показує в netstat/Get-NetTCPConnection
rem записи вже мертвих процесів, тому власник додатково звіряється з
rem Get-Process — інакше статус брехав би після невдалого рестарту.
:isup
set "UP=0"
set "PID="
for /f %%p in ('powershell -NoProfile -Command "$c=@(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); foreach($x in $c){ if(Get-Process -Id $x.OwningProcess -ErrorAction SilentlyContinue){ $x.OwningProcess; break } }"') do (
  set "PID=%%p"
  set "UP=1"
)
exit /b

rem ---- надійно вбити ВСЕ, що стосується сервера ----
rem Старий варіант (netstat + taskkill /IM + wmic) на Win11 не працює:
rem wmic видалено (воркери spawn_main лишалися живими і тримали порт),
rem а netstat віддає мертвих власників. Тепер PowerShell збирає pid-и за
rem трьома ознаками: 1) uvicorn САМЕ цього застосунку (app:app + --port)
rem та всі його python-діти; 2) осиротілі spawn_main-воркери з мертвим
rem батьком; 3) живі власники порту. Після зачистки чекаємо, поки порт
rem реально звільниться.
:killall
echo Зупиняю все на порту %PORT%...
powershell -NoProfile -Command "$pids=@(); $all=@(Get-CimInstance Win32_Process); foreach($p in $all){ if(($p.Name -eq 'python.exe' -or $p.Name -eq 'uvicorn.exe') -and $p.CommandLine -match 'app:app' -and $p.CommandLine -match '--port %PORT%'){ $pids+=$p.ProcessId } }; foreach($p in $all){ if($p.Name -eq 'python.exe' -and $pids -contains $p.ParentProcessId){ $pids+=$p.ProcessId } }; foreach($p in $all){ if($p.Name -eq 'python.exe' -and $p.CommandLine -match 'spawn_main' -and -not (Get-Process -Id $p.ParentProcessId -ErrorAction SilentlyContinue)){ $pids+=$p.ProcessId } }; foreach($c in @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue)){ if(Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue){ $pids+=$c.OwningProcess } }; foreach($id in ($pids | Sort-Object -Unique)){ try{ Stop-Process -Id $id -Force -ErrorAction Stop; Write-Host ('  killed PID ' + $id) }catch{} }"
for /l %%i in (1,1,10) do (
  call :isup
  if "!UP!"=="0" exit /b
  ping -n 2 127.0.0.1 >nul
)
exit /b

:start
call :isup
if "!UP!"=="1" (
  echo Вже працює  PID !PID!  http://127.0.0.1:%PORT%/
  goto done
)
echo Запускаю сервер...
cd /d "%APPDIR%"
start "" /b "%UVICORN%" %ARGS%
ping -n 5 127.0.0.1 >nul
call :isup
if "!UP!"=="1" (echo OK  PID !PID!  http://127.0.0.1:%PORT%/) else (echo НЕ піднявся - глянь помилки)
goto done

:restart
call :killall
echo Піднімаю заново...
cd /d "%APPDIR%"
start "" /b "%UVICORN%" %ARGS%
ping -n 5 127.0.0.1 >nul
call :isup
if "!UP!"=="1" (echo OK  PID !PID!  http://127.0.0.1:%PORT%/) else (echo НЕ піднявся)
goto done

:stop
call :killall
echo Зупинено.
goto done

:status
call :isup
if "!UP!"=="1" (echo ПРАЦЮЄ  PID !PID!) else (echo зупинено)
goto done

:done
if "%CMD%"=="" (echo. & pause & goto menu)
exit /b 0
