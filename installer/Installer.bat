@echo off
rem NAFTAL Badges - installation (Aymen)
rem Copie l'outil dans le profil de l'utilisateur et cree un raccourci sur le Bureau.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "try {" ^
  "  $src = (Get-Location).Path;" ^
  "  foreach ($f in 'naftal-badges-pro.html','naftal-badges.ico') { if (-not (Test-Path (Join-Path $src $f))) { throw ('Fichier manquant : ' + $f) } }" ^
  "  $dest = if ($env:NB_DEST) { $env:NB_DEST } else { Join-Path $env:LOCALAPPDATA 'NAFTAL Badges' };" ^
  "  $desk = if ($env:NB_DESK) { $env:NB_DESK } else { [Environment]::GetFolderPath('Desktop') };" ^
  "  New-Item -ItemType Directory -Force -Path $dest | Out-Null;" ^
  "  Copy-Item (Join-Path $src 'naftal-badges-pro.html') $dest -Force;" ^
  "  Copy-Item (Join-Path $src 'naftal-badges.ico') $dest -Force;" ^
  "  $lnk = Join-Path $desk 'NAFTAL Badges.lnk';" ^
  "  $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut($lnk);" ^
  "  $s.TargetPath = Join-Path $dest 'naftal-badges-pro.html'; $s.WorkingDirectory = $dest;" ^
  "  $s.IconLocation = (Join-Path $dest 'naftal-badges.ico') + ',0'; $s.Description = 'NAFTAL Badges - Aymen'; $s.Save();" ^
  "  Write-Host ''; Write-Host '  NAFTAL Badges est installe.' -ForegroundColor Green;" ^
  "  Write-Host ('  Outil    : ' + $dest); Write-Host ('  Raccourci: ' + $lnk);" ^
  "  Write-Host ''; Write-Host '  Pour recuperer vos badges : ouvrez l''outil puis Importer... (fichier .json).';" ^
  "} catch { Write-Host ''; Write-Host ('  Erreur : ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
set RC=%ERRORLEVEL%
echo.
if not defined NB_NOPAUSE pause
exit /b %RC%
