"""시스템 상태(CPU/GPU/RAM/드라이브), 빠른 기능, 파일/개발 항목, 자동 시작."""
import ctypes
import datetime as dt
import logging
import os
import subprocess
import time
from ctypes import wintypes

import psutil

from .config import load_config, load_state, save_state
from .icons import icon_data_url
from .launch import NO_WINDOW, open_target

log = logging.getLogger("hud")
psutil.cpu_percent(None)

# ---------------- GPU (NVIDIA 만, 없으면 '-') ----------------
try:
    import pynvml
    pynvml.nvmlInit()
    _gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    _gpu = None


def stats():
    vm = psutil.virtual_memory()
    gpu = None
    if _gpu is not None:
        try:
            gpu = pynvml.nvmlDeviceGetUtilizationRates(_gpu).gpu
        except Exception:
            pass
    return {"cpu": round(psutil.cpu_percent(None)), "gpu": gpu,
            "ramUsed": round(vm.used / 2**30, 1), "ramTotal": round(vm.total / 2**30), "ramPct": round(vm.percent)}


# ---------------- 빠른 기능 ----------------
def clean_ram():
    before = psutil.virtual_memory().available
    psapi, k32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = wintypes.HANDLE
    count = 0
    for p in psutil.process_iter(["pid"]):
        h = k32.OpenProcess(0x0400 | 0x0100, False, p.info["pid"])  # QUERY_INFORMATION | SET_QUOTA
        if h:
            if psapi.EmptyWorkingSet(h):
                count += 1
            k32.CloseHandle(h)
    time.sleep(1.5)
    freed = (psutil.virtual_memory().available - before) / 2**30
    return {"freedGB": round(max(0.0, freed), 1), "processes": count}


def toggle_focus():
    """집중 모드: 메신저 목록의 프로그램을 끄고, 다시 누르면 켠다."""
    on = not load_state().get("focus", False)
    msgs = [m for m in load_config()["messengers"] if not m["target"].startswith(("http", "shell:"))]
    if on:
        names = set()
        for m in msgs:
            exe = os.path.basename(os.path.expandvars(m["target"])).lower()
            names.add("discord.exe" if exe == "update.exe" else exe)
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() in names:
                try:
                    p.kill()
                except psutil.Error:
                    pass
    else:
        for m in msgs:
            open_target(m["target"], m.get("args"))
    save_state(focus=on)
    return on


def monitor_count():
    return ctypes.windll.user32.GetSystemMetrics(80)  # SM_CMONITORS


def toggle_monitors():
    single = monitor_count() > 1
    subprocess.Popen(["DisplaySwitch.exe", "/internal" if single else "/extend"], creationflags=NO_WINDOW)
    return "single" if single else "dual"


def toggle_wallpaper():
    exe = load_config().get("wallpaper_engine_exe")
    if not exe or not os.path.isfile(exe):
        return None
    paused = not load_state().get("wallpaperPaused", False)
    subprocess.Popen([exe, "-control", "pause" if paused else "play"], creationflags=NO_WINDOW)
    save_state(wallpaperPaused=paused)
    return paused


def disk_cleanup():
    subprocess.Popen(["cleanmgr.exe"])
    return True


def shutdown(cancel=False):
    subprocess.Popen(["shutdown.exe", "/a"] if cancel else ["shutdown.exe", "/s", "/t", "60"], creationflags=NO_WINDOW)
    save_state(shutdownAt=None if cancel else time.time() + 60)
    return not cancel


def quick_state():
    st = load_state()
    sd = st.get("shutdownAt")
    cfg = load_config()
    return {
        "focus": st.get("focus", False),
        "wallpaperPaused": st.get("wallpaperPaused", False),
        "hasWallpaper": bool(cfg.get("wallpaper_engine_exe")),
        "monitors": monitor_count(),
        "shutdownIn": max(0, round(sd - time.time())) if sd and sd > time.time() else None,
    }


# ---------------- 내 파일 ----------------
class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]


def _recycle():
    info = SHQUERYRBINFO(ctypes.sizeof(SHQUERYRBINFO), 0, 0)
    ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    return info.i64Size, info.i64NumItems


def _fmt_size(b):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.0f}{unit}" if unit in ("B", "KB") else f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}PB"


def recycle_info():
    size, n = _recycle()
    return {"count": n, "size": size, "sizeText": _fmt_size(size)}


def empty_recycle_bin():
    """휴지통 영구 비우기. HUD 쪽에서 확인을 받은 뒤에만 호출된다."""
    before = recycle_info()
    if before["count"] == 0:
        return {"ok": True, **before}
    hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)  # 확인창/진행창/소리 없이
    log.info("휴지통 비우기: %d개 %s (hr=%s)", before["count"], before["sizeText"], hr)
    return {"ok": hr == 0, **before}


def _drives(cfg):
    if cfg.get("drives"):
        return cfg["drives"]
    out = []
    for p in psutil.disk_partitions(all=False):
        if "fixed" in p.opts or p.fstype in ("NTFS", "ReFS", "exFAT", "FAT32"):
            if "cdrom" not in p.opts and p.mountpoint not in out:
                out.append(p.mountpoint)
    return out


def files():
    cfg = load_config()
    items = []
    today = dt.date.today()
    for f in cfg["files"]:
        target = os.path.expandvars(f["target"])
        if not target.startswith("shell:") and not os.path.exists(target):
            continue
        sub = ""
        try:
            if f.get("stat") == "count" and os.path.isdir(target):
                entries = list(os.scandir(target))
                size = sum(e.stat().st_size for e in entries if e.is_file())
                sub = f"{len(entries)}개 · {_fmt_size(size)}"
            elif f.get("stat") == "today" and os.path.isdir(target):
                n = sum(1 for e in os.scandir(target) if e.is_file() and dt.date.fromtimestamp(e.stat().st_mtime) == today)
                sub = f"오늘 {n}개"
            elif f.get("stat") == "recycle":
                size, n = _recycle()
                sub = f"{n}개 · {_fmt_size(size)}" if n else "비어 있음"
        except OSError:
            pass
        items.append({"name": f["name"], "target": f["target"], "glyph": f.get("glyph", "E8B7"), "sub": sub,
                      "stat": f.get("stat", "")})
    drives = []
    for d in _drives(cfg):
        try:
            u = psutil.disk_usage(d)
            drives.append({"name": d.rstrip("\\"), "pct": round(u.percent), "free": _fmt_size(u.free), "target": d})
        except OSError:
            pass
    return {"items": items, "drives": drives, "recycle": recycle_info()}


# ---------------- 메신저 / 웹 / 개발 ----------------
def _with_icon(item):
    out = dict(item)
    if not item.get("glyph"):
        out["icon"] = icon_data_url(item.get("icon") or item["target"])
    return out


def messengers():
    return [_with_icon(m) for m in load_config()["messengers"]]


def web_links():
    return load_config()["web"]


def docker_running():
    return any((p.info["name"] or "") == "com.docker.backend.exe" for p in psutil.process_iter(["name"]))


def toggle_docker():
    d = load_config()["docker"]
    running = docker_running()
    if d.get("cli"):
        subprocess.Popen([d["cli"], "desktop", "stop" if running else "start"], creationflags=NO_WINDOW)
    elif not running and d.get("desktop"):
        open_target(d["desktop"])
    return not running


def dev_items():
    cfg = load_config()["dev"]
    root = os.path.expandvars(cfg.get("projects_dir") or "")
    projects = []
    if root and os.path.isdir(root):
        dirs = [e for e in os.scandir(root) if e.is_dir() and not e.name.startswith(".")]
        dirs.sort(key=lambda e: e.stat().st_mtime, reverse=True)
        projects = [{"name": e.name, "target": e.path} for e in dirs[:40]]
    tools = []
    for t in cfg["tools"]:
        t = _with_icon(t) if not t.get("action") else dict(t)
        if t.get("action") == "docker":
            t["sub"] = "실행 중" if docker_running() else "꺼짐"
        tools.append(t)
    return {"projects": projects, "tools": tools, "projectsDir": root}


def open_project(path: str, terminal=False):
    if terminal:
        import shutil
        if shutil.which("wt"):
            subprocess.Popen(["wt.exe", "-d", path])
        else:
            subprocess.Popen(["powershell.exe", "-NoExit", "-Command", f"Set-Location -LiteralPath '{path}'"], cwd=path)
    else:
        os.startfile(path)
    return True


# ---------------- 자동 시작 ----------------
def autostart_enabled() -> bool:
    from . import autostart
    return autostart.enabled()


def set_autostart(on: bool) -> bool:
    from . import autostart
    try:
        return autostart.enable() if on else autostart.disable()
    except Exception:
        log.exception("자동 시작 설정 실패")
        return autostart.enabled()
