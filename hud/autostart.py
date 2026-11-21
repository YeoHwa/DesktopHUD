"""Windows 로그인 시 자동 실행 (작업 스케줄러, 현재 사용자, 관리자 권한 불필요).

레지스트리 Run 항목은 Windows 가 앞쪽 항목을 건너뛰는 경우가 있어서 작업 스케줄러를 쓴다.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "DesktopHUD"
NO_WINDOW = 0x08000000
APP_DIR = Path(__file__).resolve().parent.parent


def launch_command() -> tuple[str, str, str]:
    """(실행 파일, 인수, 작업 폴더) — 서명된 pythonw.exe 로 main.py 실행."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pyw = Path(sys.executable)
    return str(pyw), f'"{APP_DIR / "main.py"}"', str(APP_DIR)


def enabled() -> bool:
    r = subprocess.run(["schtasks.exe", "/Query", "/TN", TASK_NAME], capture_output=True, creationflags=NO_WINDOW)
    return r.returncode == 0


def enable(delay_seconds: int = 10) -> bool:
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    exe, args, cwd = launch_command()
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Desktop HUD 자동 시작</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId><Delay>PT{int(delay_seconds)}S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(exe)}</Command><Arguments>{escape(args)}</Arguments><WorkingDirectory>{escape(cwd)}</WorkingDirectory></Exec></Actions>
</Task>"""
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        Path(path).write_text(xml, encoding="utf-16")
        r = subprocess.run(["schtasks.exe", "/Create", "/TN", TASK_NAME, "/XML", path, "/F"],
                           capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("cp949", "replace") or r.stdout.decode("cp949", "replace"))
    finally:
        os.remove(path)
    return enabled()


def disable() -> bool:
    subprocess.run(["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, creationflags=NO_WINDOW)
    return enabled()
