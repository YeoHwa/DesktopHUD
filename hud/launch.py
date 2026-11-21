"""프로그램 / 웹 주소 / 폴더 / shell: 경로 실행."""
import logging
import os
import subprocess
import webbrowser

log = logging.getLogger("hud")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def open_target(target: str, args: list | None = None, cwd: str | None = None) -> bool:
    target = os.path.expandvars((target or "").strip())
    if not target:
        return False
    try:
        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
        elif target.startswith("shell:") or target.startswith("steam://"):
            subprocess.Popen(["explorer.exe", target])
        elif args:
            subprocess.Popen([target, *args], cwd=cwd or os.path.dirname(target) or None)
        else:
            os.startfile(target)
        return True
    except Exception:
        log.exception("실행 실패: %s %s", target, args)
        return False


def run_powershell(script: str, *args: str, hidden=True, wait=False):
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    if hidden:
        cmd += ["-WindowStyle", "Hidden"]
    cmd += ["-File", script, *args]
    flags = NO_WINDOW if hidden else 0
    p = subprocess.Popen(cmd, creationflags=flags)
    if wait:
        p.wait(timeout=60)
    return p
