# Desktop HUD 배포 파일 만들기
#   결과: dist\DesktopHUD-<버전>.zip  (압축을 풀고 '설치.cmd' 더블클릭)
#
# 새 exe 를 만들지 않는 이유: Windows 11 '스마트 앱 컨트롤'이 서명 안 된 새 exe/설치 파일을 막기 때문.
# 대신 python.org 의 서명된 Python 과 PyPI 공식 라이브러리 파일만 사용한다.
#
# 준비물: python.org 에서 설치한 Python 3.12 (서명된 공식 설치본), uv
# 사용법: .\build_dist.ps1                       (py 런처로 Python 3.12 를 자동으로 찾음)
#         .\build_dist.ps1 -PythonHome C:\Python312
param([string]$PythonHome = '')
$ErrorActionPreference = 'Stop'
if (-not $PythonHome) {
    $PythonHome = (& py -3.12 -c "import sys; print(sys.base_prefix)" 2>$null)
    if (-not $PythonHome) { throw 'Python 3.12 을 찾지 못했습니다. python.org 에서 설치하거나 -PythonHome 으로 경로를 지정하세요.' }
}
$root = $PSScriptRoot
$ver = ([regex]::Match((Get-Content "$root\hud\config.py" -Raw), 'VERSION = "([^"]+)"')).Groups[1].Value
$name = "DesktopHUD-$ver"
$out = Join-Path $root "dist\$name"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force "$out\runtime", "$out\app" | Out-Null

if ((Get-AuthenticodeSignature "$PythonHome\pythonw.exe").Status -ne 'Valid') { throw "$PythonHome\pythonw.exe 에 유효한 서명이 없습니다 (python.org 설치본을 지정하세요)" }

Write-Host '1/4 Python 런타임 복사'
Copy-Item "$PythonHome\*.exe", "$PythonHome\*.dll", "$PythonHome\LICENSE.txt" "$out\runtime" -ErrorAction SilentlyContinue
Remove-Item "$out\runtime\pythonw_d.exe", "$out\runtime\python_d.exe" -ErrorAction SilentlyContinue
robocopy "$PythonHome\DLLs" "$out\runtime\DLLs" /E /NFL /NDL /NJH /NJS /XF _tkinter.pyd tcl86t.dll tk86t.dll *_d.pyd *.pdb | Out-Null
robocopy "$PythonHome\Lib" "$out\runtime\Lib" /E /NFL /NDL /NJH /NJS /XD __pycache__ site-packages test tests idlelib tkinter turtledemo ensurepip lib2to3 /XF *.pyc | Out-Null
New-Item -ItemType Directory -Force "$out\runtime\Lib\site-packages" | Out-Null

Write-Host '2/4 라이브러리 설치'
Push-Location $root
$req = Join-Path $env:TEMP 'desktophud-req.txt'
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt -o $req | Out-Null
uv pip install --python "$PythonHome\python.exe" --target "$out\runtime\Lib\site-packages" -r $req --quiet
Pop-Location
Get-ChildItem "$out\runtime\Lib\site-packages" -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item "$out\runtime\Lib\site-packages\bin" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '3/4 앱 파일 복사'
Copy-Item "$root\main.py", "$root\installer.py" "$out\app"
robocopy "$root\hud" "$out\app\hud" *.py /NFL /NDL /NJH /NJS | Out-Null
robocopy "$root\web" "$out\app\web" /E /NFL /NDL /NJH /NJS | Out-Null

$cmd = @'
@echo off
cd /d "%~dp0"
if not exist "%~dp0runtime\pythonw.exe" (
  echo 압축을 먼저 풀어 주세요. ^(zip 안에서 바로 실행하면 설치할 수 없어요^)
  pause
  exit /b 1
)
start "" "%~dp0runtime\pythonw.exe" "%~dp0app\installer.py"
'@
[IO.File]::WriteAllText("$out\설치.cmd", "chcp 65001 >nul`r`n" + ($cmd -replace "`r?`n", "`r`n"), (New-Object Text.UTF8Encoding $false))

$readme = @"
Desktop HUD $ver
================

바탕화면에 깔리는 게임/파일/음악 런처예요.

설치
  1. 이 zip 파일의 압축을 풉니다.
  2. '설치.cmd'를 더블클릭합니다.
     (Windows 보호 창이 뜨면 '추가 정보' → '실행')
  3. 설치가 끝나면 HUD가 바로 켜지고, 다음부터는 컴퓨터를 켤 때 자동으로 켜집니다.
  관리자 권한은 필요 없고, 현재 사용자에게만 설치됩니다.
  설치 위치: %LOCALAPPDATA%\Programs\DesktopHUD

사용
  • 시계 부분을 끌면 위치를 옮길 수 있어요.
  • 톱니바퀴 → 설정: 소리 출력 장치 2개, 투명도, 테마, 키보드 버튼 링크, 프로젝트 폴더, 자동 실행
  • 게임은 Steam / Riot / Nexon / Battle.net / Epic 에서 자동으로 찾고, '게임 추가'로 직접 넣을 수도 있어요.
  • 치지직: 스트리머를 검색해 추가하면 방송이 켜질 때 Windows 알림이 와요.
  • 마우스 배터리: Logitech(G HUB 필요), Razer 무선 마우스(Synapse 없어도 됨)를 지원해요.
  • GPU 사용률은 NVIDIA 그래픽카드에서만 보여요.

제거
  설정 → 앱 → 설치된 앱 → 'Desktop HUD' → 제거

필요한 것
  Windows 10 (1803 이상) / Windows 11, Microsoft Edge WebView2 런타임 (Windows 11 에는 기본 포함)
"@
[IO.File]::WriteAllText("$out\읽어보기.txt", $readme, (New-Object Text.UTF8Encoding $true))

Write-Host '4/4 압축'
$zip = Join-Path $root "dist\$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $out -DestinationPath $zip -CompressionLevel Optimal
"{0}  ({1:N1} MB, 압축 전 {2:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB), ((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)

