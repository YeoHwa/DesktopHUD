"""Windows 알림 (토스트). 방송 시작 / 새 영상 알림에 쓴다."""
import hashlib
import logging
import time
import winreg
from xml.sax.saxutils import escape

import requests

from .config import CACHE_DIR, WEB_DIR

log = logging.getLogger("hud")
AUMID = "DesktopHUD"
IMG_DIR = CACHE_DIR / "live"
IMG_DIR.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


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


def image_file(url: str, max_age_days: float = 3) -> str:
    """알림에 넣을 그림은 로컬 파일이어야 해서 내려받아 둔다. 실패하면 ''."""
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    path = IMG_DIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
    if not path.exists() or time.time() - path.stat().st_mtime > 86400 * max_age_days:
        try:
            r = requests.get(url, headers=UA, timeout=10)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception:
            return ""
    return path.as_uri()


def toast(title: str, body: str, url: str, image: str = "", attribution: str = "", action: str = "시청하기",
          hero: str = ""):
    """image: 동그란 앱 로고 자리(프로필), hero: 위쪽 큰 그림(영상 썸네일). 둘 다 file:// 주소."""
    try:
        img = f'<image placement="appLogoOverride" hint-crop="circle" src="{escape(image)}"/>' if image else ""
        big = f'<image placement="hero" src="{escape(hero)}"/>' if hero else ""
        attr = f'<text placement="attribution">{escape(attribution)}</text>' if attribution else ""
        xml = (f'<toast activationType="protocol" launch="{escape(url)}"><visual><binding template="ToastGeneric">'
               f'<text>{escape(title)}</text><text>{escape(body)}</text>{attr}{img}{big}</binding></visual>'
               f'<actions><action content="{escape(action)}" activationType="protocol" arguments="{escape(url)}"/></actions></toast>')
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
