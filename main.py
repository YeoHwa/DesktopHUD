"""Desktop HUD 실행 진입점.
개발:  pythonw main.py   (옵션: --debug, --panel=game, --theme=dark, --peek=초)
배포:  DesktopHUD.exe    (PyInstaller 로 묶은 것)
"""
import ctypes
import logging
import logging.handlers
import os
import sys
import threading
import traceback

from hud.config import APP_DIR, LOG_PATH, VERSION, WEB_DIR, load_config, save_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
    handlers=[logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
)
log = logging.getLogger("hud")


def _excepthook(t, v, tb):
    log.error("처리되지 않은 오류:\n%s", "".join(traceback.format_exception(t, v, tb)))


sys.excepthook = _excepthook
threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback)
log.info("시작 시도 v%s (exe=%s)", VERSION, sys.executable)

import webview  # noqa: E402

from hud import audio, desktop, games, icons, media, mode, players, system  # noqa: E402
from hud.chzzk import Chzzk, toast  # noqa: E402
from hud.mouse import MouseBattery  # noqa: E402
from hud.launch import open_target  # noqa: E402

COLLAPSED_W, EXPANDED_W = 316, 1180


def _arg(name, default=None):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), default)


class Api:
    def __init__(self):
        self._window = None
        self._width = COLLAPSED_W
        self._pinned = False
        cfg = load_config()
        self._height = desktop.fit_height(cfg["window"]["x"], cfg["window"]["y"])
        self._move_timer = None
        self._battery = MouseBattery()
        self._media = media.Media(players.current()["match"])
        self._chzzk = Chzzk()
        self._games = []
        self._games_lock = threading.Lock()

    # ---------- 초기 데이터 ----------
    def init(self):
        cfg = load_config()
        return {
            "version": VERSION,
            "games": self.games(False),
            "messengers": system.messengers(wait=0),
            "web": system.web_links(wait=0),
            "mode": mode.get_mode(),
            "audioFavs": audio.favorites(),
            "audio": audio.default_id(),
            "hasKeyboard": bool(cfg.get("keyboard_url")),
            "kbIcon": icons.favicon_data_url(cfg.get("keyboard_url", ""), wait=2),
            "chzzkIcon": icons.favicon_data_url("https://chzzk.naver.com/", wait=2),
            "player": self.player(),
            "menu": self._menu(cfg),
            "openPanel": _arg("panel"),
            "theme": _arg("theme", cfg.get("theme", "light")),
            "opacity": cfg.get("opacity", {}),
            "font": {**cfg.get("font", {}), **({"body": _arg("font")} if _arg("font") else {})},
        }

    @staticmethod
    def _menu(cfg):
        """왼쪽 메뉴 순서/표시. 설정에 없는 새 메뉴는 끝에 붙인다."""
        keys = ["game", "live", "msg", "file", "dev", "sys", "web"]
        menu = [m for m in cfg.get("menu", []) if m.get("key") in keys]
        menu += [{"key": k, "show": True} for k in keys if k not in {m["key"] for m in menu}]
        return menu

    def player(self):
        p = players.current()
        return {"id": p["id"], "name": p["name"], "icon": icons.official_icon({"target": p["target"]}, wait=2) if p["target"] else ""}

    def messengers(self):
        return system.messengers()

    def web_links(self):
        return system.web_links()

    def games(self, rescan=True):
        with self._games_lock:
            if rescan or not self._games:
                self._games = games.scan(load_config())
            return [{k: g[k] for k in ("id", "name", "source", "icon")} for g in self._games]

    def status(self):
        return {
            "stats": system.stats(),
            "battery": self._battery.state,
            "audio": audio.default_id(),
            "volume": media.get_volume(),
            "mode": mode.get_mode(),
            "quick": system.quick_state(),
            "live": sum(1 for s in self._chzzk.list() if s["live"]),
        }

    # ---------- 왼쪽 위 ----------
    def set_audio(self, device_id):
        audio.set_default(device_id)
        return audio.default_id()

    def set_mode(self, m):
        return mode.set_mode(m)

    def open_keyboard(self):
        return open_target(load_config().get("keyboard_url", ""))

    def open_mouse_app(self):
        target = self._battery.app_target()
        return open_target(target) if target else False

    # ---------- 실행 ----------
    def launch_game(self, game_id):
        g = next((g for g in self._games if g["id"] == game_id), None)
        return games.launch(g) if g else False

    def hide_game(self, game_id):
        cfg = load_config()
        if game_id.startswith("extra:"):
            cfg["games"]["extra"] = [e for e in cfg["games"]["extra"] if f"extra:{e['name']}" != game_id]
        elif game_id not in cfg["games"]["hidden"]:
            cfg["games"]["hidden"].append(game_id)
        save_config(cfg)
        return self.games(True)

    def add_game(self):
        res = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=("실행 파일 (*.exe;*.lnk;*.url)",))
        if not res:
            return None
        path = res[0] if isinstance(res, (list, tuple)) else res
        name = os.path.splitext(os.path.basename(path))[0]
        cfg = load_config()
        cfg["games"]["extra"].append({"name": name, "target": path, "source": "기타"})
        save_config(cfg)
        return self.games(True)

    def open(self, target, args=None):
        return open_target(target, args)

    def open_project(self, path, terminal=False):
        return system.open_project(path, terminal)

    # ---------- 패널 데이터 ----------
    def files(self):
        return system.files()

    def dev(self):
        return system.dev_items()

    def recycle_info(self):
        return system.recycle_info()

    def empty_recycle_bin(self):
        return system.empty_recycle_bin()

    def action(self, name):
        acts = {
            "ram": system.clean_ram, "focus": system.toggle_focus, "monitor": system.toggle_monitors,
            "wallpaper": system.toggle_wallpaper, "disk": system.disk_cleanup,
            "shutdown": lambda: system.shutdown(False), "cancel_shutdown": lambda: system.shutdown(True),
            "docker": system.toggle_docker, "empty_bin": system.empty_recycle_bin,
        }
        return acts[name]() if name in acts else None

    # ---------- 웹 바로가기 ----------
    def add_web(self, name, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        cfg = load_config()
        cfg["web"].append({"name": name or url, "target": url, "glyph": "E909"})
        save_config(cfg)
        return system.web_links()

    def remove_web(self, index):
        cfg = load_config()
        if 0 <= index < len(cfg["web"]):
            cfg["web"].pop(index)
            save_config(cfg)
        return system.web_links()

    # ---------- 음악 ----------
    def media(self):
        return self._media.info()

    def media_control(self, action):
        return self._media.control(action)

    def set_volume(self, level):
        return media.set_volume(level)

    def toggle_mute(self):
        return media.toggle_mute()

    def open_player(self):
        p = players.current()
        return open_target(p["target"]) if p["target"] else False

    def list_start_apps(self):
        return players.start_apps()

    # ---------- 치지직 ----------
    def chzzk_list(self):
        return self._chzzk.list()

    def chzzk_search(self, keyword):
        return self._chzzk.search(keyword)

    def chzzk_add(self, cid, name, image=""):
        return self._chzzk.add(cid, name, image)

    def chzzk_remove(self, cid):
        return self._chzzk.remove(cid)

    def chzzk_notify(self, cid, on):
        return self._chzzk.set_notify(cid, on)

    def chzzk_open(self, cid):
        return open_target(f"https://chzzk.naver.com/live/{cid}")

    def chzzk_test(self):
        return toast("Desktop HUD 알림 테스트", "스트리머가 방송을 켜면 이렇게 알려 드려요.", "https://chzzk.naver.com/", attribution="치지직")

    # ---------- 설정 ----------
    def get_settings(self):
        cfg = load_config()
        return {
            "version": VERSION,
            "autostart": system.autostart_enabled(),
            "theme": cfg.get("theme", "light"),
            "opacity": cfg.get("opacity", {}),
            "devices": audio.list_outputs(),
            "favorites": audio.favorites(),
            "keyboard_url": cfg.get("keyboard_url", ""),
            "mouse_provider": cfg.get("mouse", {}).get("provider", "auto"),
            "projects_dir": cfg["dev"].get("projects_dir", ""),
            "game_close": "\n".join(cfg["modes"]["game"].get("close", [])),
            "dev_close": "\n".join(cfg["modes"]["dev"].get("close", [])),
            "wsl_shutdown": cfg["modes"]["game"].get("wsl_shutdown", False),
            "mode_script": bool(cfg["modes"]["game"].get("script")),
            "players": players.choices(),
            "player": players.current()["id"],
            "player_custom": cfg.get("media", {}).get("custom", {}),
            "font": cfg.get("font", {}),
            "menu": self._menu(cfg),
        }

    def save_settings(self, s):
        cfg = load_config()
        if "theme" in s:
            cfg["theme"] = "dark" if s["theme"] == "dark" else "light"
        if "opacity" in s:
            cfg["opacity"] = s["opacity"]
        if "favorites" in s:
            cfg["audio"]["favorites"] = s["favorites"]
        if "keyboard_url" in s:
            cfg["keyboard_url"] = s["keyboard_url"].strip()
        if "projects_dir" in s:
            cfg["dev"]["projects_dir"] = s["projects_dir"].strip()
        if s.get("mouse_provider") in ("auto", "ghub", "logitech", "razer", "off"):
            cfg.setdefault("mouse", {})["provider"] = s["mouse_provider"]
        if "game_close" in s:
            cfg["modes"]["game"]["close"] = [x.strip() for x in s["game_close"].splitlines() if x.strip()]
        if "dev_close" in s:
            cfg["modes"]["dev"]["close"] = [x.strip() for x in s["dev_close"].splitlines() if x.strip()]
        if "wsl_shutdown" in s:
            cfg["modes"]["game"]["wsl_shutdown"] = bool(s["wsl_shutdown"])
        if isinstance(s.get("font"), dict):
            f = s["font"]
            cfg["font"] = {"body": f.get("body") if f.get("body") in ("pretendard", "suit", "system") else "pretendard",
                           "num": f.get("num") if f.get("num") in ("rajdhani", "body") else "rajdhani"}
        if "menu" in s:
            cfg["menu"] = [{"key": m["key"], "show": bool(m.get("show", True))} for m in s["menu"]]
        if "player" in s:
            media_cfg = cfg.setdefault("media", {})
            media_cfg["player"] = s["player"]
            if s["player"] == "custom" and s.get("player_custom", {}).get("target"):
                c = s["player_custom"]
                media_cfg["custom"] = players.custom_from_app(c.get("name", "앱"), c["target"])
        save_config(cfg)
        if "player" in s:
            self._media.set_prefer(players.current()["match"])
        return True

    def set_theme(self, theme):
        self.save_settings({"theme": theme})
        return "dark" if theme == "dark" else "light"

    def set_autostart(self, on):
        return system.set_autostart(bool(on))

    def pick_folder(self):
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return ""
        return res[0] if isinstance(res, (list, tuple)) else res

    def open_config(self):
        from hud.config import CONFIG_PATH
        return open_target(str(CONFIG_PATH))

    def open_log(self):
        return open_target(str(LOG_PATH))

    # ---------- 창 ----------
    def set_expanded(self, on):
        self._width = EXPANDED_W if on else COLLAPSED_W
        if self._pinned:
            desktop.set_size(self._window, self._width, self._height)
        return True

    def _pin(self):
        desktop.pin_to_desktop(self._window, self._width, self._height)
        self._pinned = True
        peek = _arg("peek")
        if peek:
            threading.Timer(4, desktop.peek_front, args=(self._window, float(peek))).start()

    def _on_moved(self, x, y):
        """끌어서 옮긴 뒤 0.6초 동안 더 움직이지 않으면 위치 저장 + 그 모니터 높이에 다시 맞춤."""
        if self._move_timer:
            self._move_timer.cancel()

        def settle():
            c = load_config()
            c["window"]["x"], c["window"]["y"] = int(x), int(y)
            save_config(c)
            h = desktop.fit_height(x, y)
            if h != self._height:
                self._height = h
                desktop.set_size(self._window, self._width, h)

        self._move_timer = threading.Timer(0.6, settle)
        self._move_timer.start()

    def quit(self):
        self._window.destroy()


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "DesktopHUD_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not single_instance():
        log.info("이미 실행 중이라 종료")
        return
    os.chdir(APP_DIR)
    cfg = load_config()
    api = Api()
    win = webview.create_window(
        "Desktop HUD", url=str(WEB_DIR / "index.html"), js_api=api,
        width=COLLAPSED_W, height=api._height, x=cfg["window"]["x"], y=cfg["window"]["y"],
        frameless=True, transparent=True, resizable=False, easy_drag=False, shadow=False,
        background_color="#000000",
    )
    api._window = win
    win.events.moved += api._on_moved
    win.events.shown += lambda: threading.Timer(0.8, api._pin).start()
    log.info("HUD 시작")
    from hud.config import LOCAL_DIR
    webview.start(debug="--debug" in sys.argv, private_mode=False, storage_path=str(LOCAL_DIR / "webview"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("HUD 실행 중 오류로 종료")
        raise
