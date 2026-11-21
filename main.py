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
import time
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

from hud import audio, desktop, games, icons, media, players, quick, system  # noqa: E402
from hud.chzzk import Chzzk, toast  # noqa: E402
from hud.mouse import MouseBattery  # noqa: E402
from hud.launch import open_target  # noqa: E402

COLLAPSED_W, PANEL_GAP = 316, 12          # 왼쪽 메뉴 열 너비, 메뉴 창과의 간격 (배율 100% 기준 CSS px)
DEFAULT_LAYOUT = {"monitor": 0, "side": "left", "margin_x": 24, "margin_y": 24, "scale": 1.0,
                  "panel_width": 852, "height_mode": "fit", "height": 900}


def _arg(name, default=None):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), default)


class Api:
    def __init__(self):
        self._window = None
        self._pinned = False
        self._expanded = False
        self._flip = False
        self._ignore_move_until = 0.0
        self._move_timer = None
        cfg = load_config()
        if "layout" not in cfg:   # 이전 버전: 창 좌표(window.x/y)만 있던 설정을 layout 으로 옮김
            mon = desktop.monitor_at(cfg["window"]["x"] + 10, cfg["window"]["y"] + 10)
            cfg["layout"] = {**DEFAULT_LAYOUT, "monitor": mon["index"],
                             "margin_x": max(0, cfg["window"]["x"] - mon["left"]), "margin_y": max(0, cfg["window"]["y"] - mon["top"])}
            save_config(cfg)
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
            "quickButtons": quick.buttons(),
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
            "quick": system.quick_state(),
            "quickButtons": quick.buttons(),
            "live": sum(1 for s in self._chzzk.list() if s["live"]),
        }

    # ---------- 왼쪽 위 ----------
    def set_audio(self, device_id):
        audio.set_default(device_id)
        return audio.default_id()

    def quick_run(self, action):
        return quick.run(action)

    def quick_buttons(self):
        return quick.buttons()

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
            "quick": quick.selected(),
            "quick_choices": quick.choices(),
            "players": players.choices(),
            "player": players.current()["id"],
            "player_custom": cfg.get("media", {}).get("custom", {}),
            "font": cfg.get("font", {}),
            "menu": self._menu(cfg),
            "layout": self._layout(),
            "monitors": [{"index": m["index"], "name": m["name"]} for m in desktop.monitors()],
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
        if isinstance(s.get("quick"), list):
            cfg["quick"] = [a for a in s["quick"] if a in quick.ACTIONS][:4] or quick.DEFAULT
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
        if isinstance(s.get("layout"), dict):
            self.apply_layout(s["layout"])
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

    # ---------- 창 위치·크기 ----------
    # 설정의 layout(모니터, 붙일 쪽, 여백, 배율, 메뉴 창 너비, 높이)으로 창 좌표를 계산한다.
    # '기준 위치'는 왼쪽 메뉴 열이 놓이는 곳. 메뉴 창을 펼칠 때 공간이 있는 쪽으로 펼친다.
    def _layout(self):
        L = {**DEFAULT_LAYOUT, **load_config().get("layout", {})}
        L["scale"] = min(1.6, max(0.7, float(L["scale"])))
        return L

    def _geometry(self, expanded: bool):
        L = self._layout()
        mons = desktop.monitors()
        mon = mons[L["monitor"]] if 0 <= L["monitor"] < len(mons) else mons[0]
        k = L["scale"] * (desktop.dpi_scale(self._window) if self._window and self._pinned else 1.0)
        col_w = round(COLLAPSED_W * k)
        exp_w = round((COLLAPSED_W + PANEL_GAP + L["panel_width"]) * k)
        mx, my = round(L["margin_x"] * k / L["scale"]), round(L["margin_y"] * k / L["scale"])
        work_h = mon["bottom"] - mon["top"]
        h = work_h - 2 * my if L["height_mode"] == "fit" else min(work_h - my, round(L["height"] * k / L["scale"]))
        h = max(round(480 * k), h)
        base_x = mon["left"] + mx if L["side"] == "left" else mon["right"] - mx - col_w
        y = mon["top"] + my
        if not expanded:
            return {"x": base_x, "y": y, "w": col_w, "h": h, "flip": False, "zoom": L["scale"]}
        # 오른쪽에 붙어 있거나 오른쪽 공간이 모자라면 왼쪽으로 펼친다
        flip = L["side"] == "right" or base_x + exp_w > mon["right"]
        x = base_x + col_w - exp_w if flip else base_x
        x = max(mon["left"], min(x, mon["right"] - exp_w))
        return {"x": x, "y": y, "w": exp_w, "h": h, "flip": flip, "zoom": L["scale"]}

    def _apply_geometry(self):
        g = self._geometry(self._expanded)
        self._flip = g["flip"]
        self._ignore_move_until = time.time() + 1.5
        desktop.set_bounds(self._window, g["x"], g["y"], g["w"], g["h"])
        # 메뉴 창이 열린 채로 붙일 쪽이 바뀌어도 화면 배치(메뉴 창이 어느 쪽에 있는지)를 바로 맞춘다
        try:
            self._window.evaluate_js(f"window.setFlip && window.setFlip({'true' if g['flip'] else 'false'})")
        except Exception as e:
            log.debug("배치 갱신 실패: %s", e)
        return g

    def set_expanded(self, on):
        self._expanded = bool(on)
        if self._pinned:
            g = self._apply_geometry()
            return {"flip": g["flip"]}
        return {"flip": False}

    def apply_layout(self, layout):
        """설정 화면의 '위치·크기 적용'."""
        cfg = load_config()
        cfg["layout"] = {**DEFAULT_LAYOUT, **{k: layout[k] for k in DEFAULT_LAYOUT if k in layout}}
        save_config(cfg)
        desktop.set_zoom(self._window, self._layout()["scale"])
        self._apply_geometry()
        return True

    def _pin(self):
        desktop.pin_to_desktop(self._window)
        self._pinned = True
        desktop.set_zoom(self._window, self._layout()["scale"])
        self._apply_geometry()
        desktop.watch_visibility(self._window, self._on_visibility)
        peek = _arg("peek")
        if peek:
            threading.Timer(4, desktop.peek_front, args=(self._window, float(peek))).start()

    def _on_visibility(self, visible: bool):
        """다른 창에 완전히 가려지면 화면 갱신을 멈추고 WebView2 를 메모리 절약 모드로 (치지직 알림 확인은 계속)."""
        log.info("HUD %s", "보임 → 갱신 재개" if visible else "가려짐 → 갱신 멈춤")
        try:
            self._window.evaluate_js(f"window.setVisible && window.setVisible({'true' if visible else 'false'})")
        except Exception as e:
            log.debug("보임 상태 전달 실패: %s", e)
        desktop.set_memory_saving(self._window, not visible)
        if not visible:
            # 가려진 동안은 HUD 본체가 쥐고 있던 안 쓰는 메모리도 Windows 에 돌려준다 (필요하면 다시 불러옴)
            threading.Timer(10, trim_own_memory).start()

    def _on_moved(self, x, y):
        """시계를 끌어 옮긴 뒤 0.6초 동안 멈추면, 그 위치를 설정(모니터·붙일 쪽·여백)으로 바꿔 저장하고 높이를 맞춘다."""
        if time.time() < self._ignore_move_until:
            return
        if self._move_timer:
            self._move_timer.cancel()

        def settle():
            L = self._layout()
            k = L["scale"] * desktop.dpi_scale(self._window)
            col_w = round(COLLAPSED_W * k)
            exp_w = round((COLLAPSED_W + PANEL_GAP + L["panel_width"]) * k)
            base_x = x + exp_w - col_w if (self._expanded and self._flip) else x
            mon = desktop.monitor_at(base_x + col_w // 2, y + 20)
            side = "left" if base_x + col_w / 2 < (mon["left"] + mon["right"]) / 2 else "right"
            mx = base_x - mon["left"] if side == "left" else mon["right"] - (base_x + col_w)
            L.update(monitor=mon["index"], side=side,
                     margin_x=max(0, round(mx * L["scale"] / k)), margin_y=max(0, round((y - mon["top"]) * L["scale"] / k)))
            c = load_config()
            c["layout"] = L
            save_config(c)
            self._apply_geometry()

        self._move_timer = threading.Timer(0.6, settle)
        self._move_timer.start()

    def quit(self):
        self._window.destroy()


def trim_own_memory():
    """이 프로세스의 작업 집합(실제 RAM 에 올라와 있는 양)을 비운다."""
    from ctypes import wintypes
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    ok = psapi.EmptyWorkingSet(k32.GetCurrentProcess())
    log.info("HUD 본체 메모리 정리: %s", "완료" if ok else "실패")


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "DesktopHUD_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not single_instance():
        log.info("이미 실행 중이라 종료")
        return
    os.chdir(APP_DIR)
    api = Api()
    g = api._geometry(False)
    win = webview.create_window(
        "Desktop HUD", url=str(WEB_DIR / "index.html"), js_api=api,
        width=g["w"], height=g["h"], x=g["x"], y=g["y"],
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
