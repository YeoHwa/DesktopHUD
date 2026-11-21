# Desktop HUD 배포 파일 만들기
#   결과: dist\DesktopHUD-<버전>.zip  (압축을 풀고 'Desktop HUD 설치.exe' 더블클릭)
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

# 설치 실행 파일: .cmd 는 인터넷에서 받으면 스마트 앱 컨트롤이 막으므로("Dangerous file extension from the web"),
# python.org 가 서명한 pythonw.exe 를 이름만 바꿔 맨 위에 둔다. (이름을 바꿔도 디지털 서명은 그대로 유효)
# 같은 이름의 ._pth 파일이 runtime 과 app\setup_boot 를 경로로 잡고, setup_boot\sitecustomize.py 가 설치 창을 연다.
$setupName = 'Desktop HUD 설치'
robocopy "$root\setup_boot" "$out\app\setup_boot" *.py /NFL /NDL /NJH /NJS | Out-Null
Copy-Item "$out\runtime\pythonw.exe" "$out\$setupName.exe"
foreach ($dll in 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') {   # exe 옆에 있어야 실행됨
    if (Test-Path "$out\runtime\$dll") { Copy-Item "$out\runtime\$dll" "$out\$dll" }
}
$pth = "runtime\Lib`r`nruntime\DLLs`r`nruntime\Lib\site-packages`r`napp\setup_boot`r`nimport site`r`n"
[IO.File]::WriteAllText("$out\$setupName._pth", $pth, (New-Object Text.UTF8Encoding $false))
if ((Get-AuthenticodeSignature "$out\$setupName.exe").Status -ne 'Valid') { throw "설치 실행 파일의 서명이 유효하지 않습니다" }

$readme = @"
Desktop HUD $ver
================

바탕화면에 깔리는 게임/파일/음악 런처예요.

설치
  1. 이 zip 파일의 압축을 풉니다.
  2. 'Desktop HUD 설치.exe' 를 더블클릭하면 설치 창이 열립니다.
     (파이썬 모양 아이콘이지만 정상이에요. python.org 가 서명한 실행 파일을 이름만 바꾼 것이라
      Windows 스마트 앱 컨트롤에도 막히지 않아요.)
     함께 들어 있는 python*.dll, vcruntime*.dll, ._pth 파일은 설치 실행에 필요하니 지우지 마세요.
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
# Compress-Archive 는 백신이 방금 복사된 DLL 을 검사하는 동안 '사용 중' 오류로 실패하므로 Python zipfile 사용
& "$PythonHome\python.exe" -c "import zipfile,os,sys; src,dst=sys.argv[1],sys.argv[2]; base=os.path.dirname(src); z=zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED,compresslevel=9); [z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f), base)) for r,_,fs in os.walk(src) for f in fs]; z.close()" $out $zip
"{0}  ({1:N1} MB, 압축 전 {2:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB), ((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)

