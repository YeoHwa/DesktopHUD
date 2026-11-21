"""어느 PC 에서든 동작하도록 설치된 프로그램 위치를 찾아내는 도우미."""
import json
import logging
import os
import re
import shutil
import subprocess
import winreg
from functools import lru_cache

log = logging.getLogger("hud")
NO_WINDOW = 0x08000000
UNINSTALL_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _val(key, name):
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return ""


def uninstall_entries():
    """(레지스트리 키 이름, {DisplayName, DisplayIcon, InstallLocation, UninstallString})"""
    out = []
    for hive, path in UNINSTALL_KEYS:
        try:
            base = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(base)[0]):
            try:
                sub = winreg.EnumKey(base, i)
                with winreg.OpenKey(base, sub) as k:
                    out.append((sub, {n: _val(k, n) for n in ("DisplayName", "DisplayIcon", "InstallLocation", "UninstallString")}))
            except OSError:
                continue
    return out


def find_installed(name_pattern: str, key_pattern: str = "") -> dict | None:
    rx = re.compile(name_pattern, re.I)
    krx = re.compile(key_pattern, re.I) if key_pattern else None
    for sub, e in uninstall_entries():
        if (krx and krx.search(sub)) or (not krx and rx.search(e["DisplayName"])):
            return e
    return None


def exe_near(entry: dict | None, exe_name: str) -> str:
    """앱 제거 항목의 설치 폴더/아이콘 경로 근처에서 실행 파일을 찾는다."""
    if not entry:
        return ""
    cands = []
    if entry["InstallLocation"]:
        cands.append(entry["InstallLocation"].strip('"'))
    icon = entry["DisplayIcon"].split(",")[0].strip('"')
    if icon:
        cands += [os.path.dirname(icon), os.path.dirname(os.path.dirname(icon))]
    for d in cands:
        for p in (os.path.join(d, exe_name), os.path.join(d, "bin", exe_name)):
            if os.path.isfile(p):
                return p
    return ""


@lru_cache(maxsize=1)
def start_apps() -> list[dict]:
    """시작 메뉴 앱 목록 (스토어 앱/웹 앱 포함). [{Name, AppID}]"""
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, timeout=20, creationflags=NO_WINDOW)
        data = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
        return data if isinstance(data, list) else [data]
    except Exception as e:
        log.warning("시작 메뉴 앱 목록 실패: %s", e)
        return []


def find_start_app(*names: str) -> str:
    """이름이 정확히 일치하는 시작 메뉴 앱의 shell:AppsFolder 경로."""
    wanted = [n.lower() for n in names]
    for a in start_apps():
        if (a.get("Name") or "").lower() in wanted:
            return "shell:AppsFolder\\" + a["AppID"]
    return ""


def youtube_music():
    """YouTube Music 웹 앱(크롬/엣지/웨일 설치형)이 있으면 그 앱, 없으면 웹 주소."""
    app = find_start_app("YouTube Music")
    if app:
        m = re.search(r"_crx_([a-z]+)", app)
        return app, (m[1] if m else "")
    return "https://music.youtube.com/", ""


def wallpaper_engine_exe() -> str:
    e = find_installed("", r"^Steam App 431960$")
    return exe_near(e, "wallpaper64.exe")


def docker_paths() -> tuple[str, str]:
    e = find_installed(r"^Docker Desktop$")
    desktop = exe_near(e, "Docker Desktop.exe") or (r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
                                                   if os.path.isfile(r"C:\Program Files\Docker\Docker\Docker Desktop.exe") else "")
    cli = shutil.which("docker") or ""
    if desktop and not cli:
        p = os.path.join(os.path.dirname(desktop), "resources", "bin", "docker.exe")
        cli = p if os.path.isfile(p) else ""
    return desktop, cli


def kakaotalk_exe() -> str:
    return exe_near(find_installed(r"카카오톡|KakaoTalk"), "KakaoTalk.exe")


def vscode_exe() -> str:
    for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
              r"C:\Program Files\Microsoft VS Code\Code.exe"):
        if os.path.isfile(p):
            return p
    return ""


def terminal_cmd() -> str:
    return "wt.exe" if shutil.which("wt") else "powershell.exe"


def ghub_exe() -> str:
    p = r"C:\Program Files\LGHUB\lghub.exe"
    return p if os.path.isfile(p) else ""


def razer_app() -> str:
    """Razer Synapse (3 또는 4)."""
    app = find_start_app("Razer Synapse", "Razer Synapse 4", "Razer Synapse 3")
    if app:
        return app
    for p in (r"%ProgramFiles(x86)%\Razer\Synapse3\WPFUI\Framework\Razer Synapse 3 Host\Razer Synapse 3.exe",
              r"%ProgramFiles%\Razer\RazerAppEngine\RazerAppEngine.exe",
              r"%ProgramFiles(x86)%\Razer\RazerAppEngine\RazerAppEngine.exe"):
        p = os.path.expandvars(p)
        if os.path.isfile(p):
            return p
    return ""


def wsl_installed() -> bool:
    return os.path.isfile(os.path.expandvars(r"%WINDIR%\System32\wsl.exe"))
