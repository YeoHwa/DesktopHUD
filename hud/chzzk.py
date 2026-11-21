"""치지직 방송 상태 확인 + 방송 시작 시 Windows 알림."""
import logging
import threading
import time
import winreg
from xml.sax.saxutils import escape

import requests

from .config import CACHE_DIR, WEB_DIR, load_config, save_config

log = logging.getLogger("hud")
API = "https://api.chzzk.naver.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DesktopHUD"}
IMG_DIR = CACHE_DIR / "chzzk"
IMG_DIR.mkdir(exist_ok=True)
AUMID = "DesktopHUD"


def _get(path, **params):
    r = requests.get(API + path, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("content") or {}


def register_aumid():
    """알림에 'Desktop HUD' 이름과 아이콘이 나오도록 앱 ID 등록 (현재 사용자)."""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}") as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Desktop HUD")
            icon = WEB_DIR / "logo.png"
            if icon.exists():
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, str(icon))
    except OSError:
        log.exception("알림 앱 ID 등록 실패")


def toast(title: str, body: str, url: str, image: str = "", attribution: str = ""):
    try:
        img = f'<image placement="appLogoOverride" hint-crop="circle" src="{escape(image)}"/>' if image else ""
        attr = f'<text placement="attribution">{escape(attribution)}</text>' if attribution else ""
        xml = (f'<toast activationType="protocol" launch="{escape(url)}"><visual><binding template="ToastGeneric">'
               f'<text>{escape(title)}</text><text>{escape(body)}</text>{attr}{img}</binding></visual>'
               f'<actions><action content="시청하기" activationType="protocol" arguments="{escape(url)}"/></actions></toast>')
        # .NET(pythonnet) 으로 Windows 알림 API 호출 (hud/winrt_net.py 참고)
        import clr
        from System import Activator, Array, Object, String, Type
        from . import winrt_net
        Xml = winrt_net.winrt_type("Windows.Data.Xml.Dom.XmlDocument", "Windows.Data.Xml.Dom")
        Mgr = winrt_net.winrt_type("Windows.UI.Notifications.ToastNotificationManager", "Windows.UI.Notifications")
        Toast = winrt_net.winrt_type("Windows.UI.Notifications.ToastNotification", "Windows.UI.Notifications")
        doc = Activator.CreateInstance(Xml)
        doc.LoadXml(xml)
        create = Mgr.GetMethod("CreateToastNotifier", Array[Type]([clr.GetClrType(String)]))
        notifier = create.Invoke(None, Array[Object]([AUMID]))
        notifier.Show(Activator.CreateInstance(Toast, Array[Object]([doc])))
        return True
    except Exception:
        log.exception("알림 표시 실패")
        return False


def _image_file(channel_id: str, url: str) -> str:
    if not url:
        return ""
    path = IMG_DIR / f"{channel_id}.jpg"
    if not path.exists() or time.time() - path.stat().st_mtime > 86400 * 3:
        try:
            path.write_bytes(requests.get(url, headers=HEADERS, timeout=10).content)
        except Exception:
            return ""
    return path.as_uri()


class Chzzk:
    def __init__(self):
        self.status: dict[str, dict] = {}
        self._first = True
        self._wake = threading.Event()
        register_aumid()
        threading.Thread(target=self._run, daemon=True, name="chzzk").start()

    def refresh_now(self):
        self._wake.set()

    def _poll(self):
        cfg = load_config()
        changed = False
        for s in cfg["streamers"]:
            cid = s["id"]
            try:
                c = _get(f"/polling/v2/channels/{cid}/live-status")
            except Exception as e:
                log.info("치지직 확인 실패 %s: %s", s.get("name"), e)
                continue
            live = c.get("status") == "OPEN"
            prev = self.status.get(cid, {}).get("live")
            if not s.get("image"):
                try:
                    ch = _get(f"/service/v1/channels/{cid}")
                    s["image"] = ch.get("channelImageUrl") or ""
                    s["name"] = ch.get("channelName") or s.get("name")
                    changed = True
                except Exception:
                    pass
            self.status[cid] = {
                "live": live,
                "title": c.get("liveTitle") or "",
                "viewers": c.get("concurrentUserCount") or 0,
                "category": c.get("liveCategoryValue") or "",
                "since": self.status.get(cid, {}).get("since") if (prev and live) else (time.time() if live else None),
                "checked": time.time(),
            }
            if live and prev is False and s.get("notify", True) and not self._first:
                toast(f"{s.get('name')} 방송 시작", c.get("liveTitle") or "", f"https://chzzk.naver.com/live/{cid}",
                      _image_file(cid, s.get("image", "")), c.get("liveCategoryValue") or "치지직")
        if changed:
            save_config(cfg)
        self._first = False

    def _run(self):
        while True:
            try:
                self._poll()
            except Exception:
                log.exception("치지직 확인 중 오류")
            secs = max(30, int(load_config().get("chzzk_poll_seconds", 60)))
            self._wake.wait(secs)
            self._wake.clear()

    # ---- HUD 에서 부르는 기능 ----
    def list(self):
        cfg = load_config()
        out = []
        for s in cfg["streamers"]:
            st = self.status.get(s["id"], {})
            out.append({**s, **st, "live": bool(st.get("live"))})
        out.sort(key=lambda x: (not x["live"], x.get("name", "")))
        return out

    @staticmethod
    def search(keyword: str):
        try:
            data = _get("/service/v1/search/channels", keyword=keyword, size=8).get("data", [])
        except Exception:
            log.exception("치지직 검색 실패")
            return []
        return [{"id": d["channel"]["channelId"], "name": d["channel"]["channelName"],
                 "image": d["channel"].get("channelImageUrl") or "", "followers": d["channel"].get("followerCount", 0),
                 "live": bool(d["channel"].get("openLive"))} for d in data if d.get("channel")]

    def add(self, cid: str, name: str, image: str = ""):
        cfg = load_config()
        if not any(s["id"] == cid for s in cfg["streamers"]):
            cfg["streamers"].append({"id": cid, "name": name, "notify": True, "image": image})
            save_config(cfg)
        self.refresh_now()
        return True

    def remove(self, cid: str):
        cfg = load_config()
        cfg["streamers"] = [s for s in cfg["streamers"] if s["id"] != cid]
        save_config(cfg)
        self.status.pop(cid, None)
        return True

    def set_notify(self, cid: str, on: bool):
        cfg = load_config()
        for s in cfg["streamers"]:
            if s["id"] == cid:
                s["notify"] = bool(on)
        save_config(cfg)
        return True
