"""게임 모드 / 개발 모드 전환 (내장).  설정에 script 가 있으면 그 PowerShell 스크립트를 대신 실행한다."""
import logging
import os
import subprocess
import threading
import time

import psutil

from .config import load_config, load_state, save_state
from .launch import NO_WINDOW, open_target, run_powershell

log = logging.getLogger("hud")


def _norm(name: str) -> str:
    n = name.strip().lower()
    return n[:-4] if n.endswith(".exe") else n


def _kill(names: list[str]) -> list[str]:
    wanted = {_norm(n) for n in names if n.strip()}
    killed = []
    for p in psutil.process_iter(["name"]):
        if _norm(p.info["name"] or "") in wanted:
            try:
                p.kill()
                killed.append(p.info["name"])
            except psutil.Error:
                pass
    return sorted(set(killed))


def _run(mode: str):
    cfg = load_config()
    m = cfg["modes"].get(mode.lower(), {})
    if m.get("script") and os.path.isfile(os.path.expandvars(m["script"])):
        run_powershell(os.path.expandvars(m["script"]), "-Mode", "Game" if mode.lower() == "game" else "Dev", hidden=False)
        return
    close = m.get("close", [])
    docker_cli = cfg["docker"].get("cli")
    if docker_cli and any("docker" in _norm(n) for n in close):
        try:
            subprocess.run([docker_cli, "desktop", "stop"], timeout=60, creationflags=NO_WINDOW, capture_output=True)
        except Exception as e:
            log.info("docker desktop stop 실패: %s", e)
    killed = _kill(close)
    if m.get("wsl_shutdown"):
        subprocess.run(["wsl.exe", "--shutdown"], timeout=30, creationflags=NO_WINDOW, capture_output=True)
    for t in m.get("start", []):
        if isinstance(t, dict):
            open_target(t.get("target", ""), t.get("args"))
        elif t:
            open_target(t)
    log.info("%s 모드 전환: 종료 %s", mode, killed)


def get_mode() -> str:
    return load_state().get("mode", "Game")


def set_mode(mode: str) -> str:
    mode = "Dev" if mode.lower() == "dev" else "Game"
    save_state(mode=mode)
    threading.Thread(target=_run, args=(mode,), daemon=True).start()
    return mode
