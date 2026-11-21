"""'Desktop HUD 설치.exe' 를 더블클릭했을 때 설치 창을 띄운다.

배포 폴더 맨 위의 'Desktop HUD 설치.exe' 는 python.org 가 서명한 pythonw.exe 를 이름만 바꾼 것이다.
(.cmd 같은 스크립트는 인터넷에서 받으면 Windows '스마트 앱 컨트롤'이 막고, 서명된 exe 는 허용된다)
같은 이름의 ._pth 파일이 이 폴더(app\\setup_boot)를 경로에 넣어 두었기 때문에,
파이썬이 켜질 때 이 sitecustomize 가 자동으로 실행되고 → app\\installer.py 를 실행한다.
"""
import os
import sys
from pathlib import Path


def _unblock(root: Path):
    """인터넷에서 받은 압축을 풀면 모든 파일에 '인터넷 영역' 표시(Zone.Identifier)가 붙는다.
    .NET Framework 는 이 표시가 있는 .NET 라이브러리를 불러오지 않으므로(설치 창·HUD 가 안 열림) 먼저 지운다.
    (Windows 의 '차단 해제' 와 같음)"""
    for dirpath, _, files in os.walk(root):
        for f in files:
            try:
                os.remove(os.path.join(dirpath, f) + ":Zone.Identifier")
            except OSError:
                pass


def _run_installer():
    argv = getattr(sys, "orig_argv", sys.argv)
    if len(argv) > 1:          # 인수가 있으면(다른 용도로 실행) 아무것도 하지 않음
        return
    root = Path(sys.executable).resolve().parent
    installer = root / "app" / "installer.py"
    if not installer.exists():
        return
    _unblock(root)
    import runpy
    sys.argv = [str(installer)]
    try:
        runpy.run_path(str(installer), run_name="__main__")
    finally:
        os._exit(0)            # 대화형 모드로 넘어가지 않고 바로 끝냄


_run_installer()
