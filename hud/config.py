"""설정(config.json)과 실행 상태(state.json) 읽기/쓰기.

- 프로그램 파일(web 폴더 등): 설치 폴더 (PyInstaller 로 묶이면 sys._MEIPASS)
- 사용자 설정:   %APPDATA%\\DesktopHUD\\config.json, state.json
- 캐시/로그:     %LOCALAPPDATA%\\DesktopHUD\\
"""
import json
import logging
import os
import sys
import threading
from pathlib import Path

APP_NAME = "DesktopHUD"
VERSION = "1.4.0"
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = APP_DIR / "web"
EXE_PATH = Path(sys.executable) if FROZEN else None

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
LOCAL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CACHE_DIR = LOCAL_DIR / "cache"
LOG_PATH = LOCAL_DIR / "hud.log"
for d in (DATA_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"

log = logging.getLogger("hud")
_lock = threading.RLock()

DEFAULT_CONFIG = {
    "window": {"x": 24, "y": 24},
    "theme": "light",
    "font": {"body": "pretendard", "num": "rajdhani"},   # body: pretendard / suit / system,  num: rajdhani / body
    "opacity": {"light": {"panel": 0.70, "glass": 0.40}, "dark": {"panel": 0.62, "glass": 0.45}},
    "keyboard_url": "",
    "ghub_exe": "",
    "razer_app": "",
    "mouse": {"provider": "auto"},   # auto / ghub / razer / off
    "media": {"player": "youtube_music", "custom": {}},   # youtube_music / spotify / apple_music / melon / genie / any / custom
    "menu": [{"key": k, "show": True} for k in ("game", "live", "msg", "file", "dev", "sys", "web")],
    "audio": {"favorites": []},
    "quick": ["mic", "capture", "lock", "ram"],   # 왼쪽 위 빠른 버튼 4개 (hud/quick.py 의 ACTIONS 중에서)
    "wallpaper_engine_exe": "",
    "docker": {"desktop": "", "cli": ""},
    "games": {"hidden": ["steam:431960", "steam:228980"], "extra": [], "rename": {}},
    "streamers": [],          # 라이브 알림: [{platform: chzzk/soop/youtube/twitch, id, name, image, notify}]
    "chzzk_poll_seconds": 60,  # 치지직 · SOOP · Twitch 방송 확인 간격 (YouTube 는 3분)
    "youtube": {"hide_shorts": False, "hide_channels": True},   # hide_channels: 라이브 '전체'에서 YouTube 채널 줄 숨기기
    "hotkey": "Ctrl+Alt+H",    # HUD 를 맨 앞으로 띄우는 단축키 (빈 값이면 끔)
    "messengers": [],           # 메신저·커뮤니티 (처음 실행 때 설치된 메신저만 자동으로)
    "messengers_hidden": [],    # 사용자가 지운 자동 감지 메신저 (다시 넣지 않음)
    "files": [
        {"name": "다운로드", "target": r"%USERPROFILE%\Downloads", "glyph": "E896", "stat": "count"},
        {"name": "스크린샷", "target": r"%USERPROFILE%\Pictures\Screenshots", "glyph": "E722", "stat": "today"},
        {"name": "동영상 캡처", "target": r"%USERPROFILE%\Videos\Captures", "glyph": "E714", "stat": "today"},
        {"name": "문서", "target": r"%USERPROFILE%\Documents", "glyph": "E8A5"},
        {"name": "바탕화면", "target": r"%USERPROFILE%\Desktop", "glyph": "E7F4"},
        {"name": "사진", "target": r"%USERPROFILE%\Pictures", "glyph": "E8B9"},
        {"name": "휴지통", "target": "shell:RecycleBinFolder", "glyph": "E74D", "stat": "recycle"},
    ],
    "drives": [],
    "dev": {"projects_dir": "", "tools": []},
    "web": [
        {"name": "네이버", "target": "https://www.naver.com/", "glyph": "E909"},
        {"name": "Google", "target": "https://www.google.com/", "glyph": "E909"},
        {"name": "YouTube", "target": "https://www.youtube.com/", "glyph": "E714"},
        {"name": "나무위키", "target": "https://namu.wiki/", "glyph": "E82D"},
    ],
}


def _merge(default, user):
    """사용자 설정에 없는 키는 기본값으로 채운다."""
    if isinstance(default, dict) and isinstance(user, dict):
        out = dict(default)
        for k, v in user.items():
            out[k] = _merge(default.get(k), v) if k in default else v
        return out
    return user if user is not None else default


def _first_run_defaults() -> dict:
    """처음 실행할 때 이 PC 에 설치된 프로그램을 찾아 기본 설정을 만든다."""
    from . import detect
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["ghub_exe"] = detect.ghub_exe()
    cfg["razer_app"] = detect.razer_app()
    cfg["wallpaper_engine_exe"] = detect.wallpaper_engine_exe()
    desk, cli = detect.docker_paths()
    cfg["docker"] = {"desktop": desk, "cli": cli}

    from . import catalog, links
    cfg["messengers"] = catalog.detect_messengers()
    for cand in (r"%USERPROFILE%\source\repos", r"%USERPROFILE%\Projects", r"%USERPROFILE%\Documents\GitHub"):
        if os.path.isdir(os.path.expandvars(cand)):
            cfg["dev"]["projects_dir"] = cand
            break
    cfg["workspace"] = links.default_workspace(cfg["dev"]["projects_dir"])
    return cfg


_cache = {"cfg": None, "mtime": None}


def load_config():
    with _lock:
        mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None
        if _cache["cfg"] is not None and mtime == _cache["mtime"]:
            return json.loads(json.dumps(_cache["cfg"]))
        if mtime is None:
            cfg = _first_run_defaults()
            save_config(cfg)
            log.info("처음 실행: 기본 설정을 만들었습니다 (%s)", CONFIG_PATH)
        else:
            try:
                user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                log.exception("config.json 을 읽지 못해 기본값을 씁니다")
                user = {}
            cfg = _merge(DEFAULT_CONFIG, user)
        _cache["cfg"], _cache["mtime"] = cfg, CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None
        return json.loads(json.dumps(cfg))


def save_config(cfg):
    with _lock:
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
        _cache["cfg"], _cache["mtime"] = None, None


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(**kw):
    with _lock:
        st = load_state()
        st.update(kw)
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
