"""왼쪽 위 '빠른 버튼' — 설정에서 고른 기능을 버튼 하나로 (게임/개발 모드를 대신함)."""
import ctypes
import logging
import os
import subprocess
import time

from . import system
from .config import load_config
from .launch import NO_WINDOW

log = logging.getLogger("hud")

# id: (이름, 아이콘 글리프, 켜짐 상태 아이콘 or None, 확인 문구 or None)
ACTIONS = {
    "mic":       ("마이크", "E720", "F781", None),
    "capture":   ("화면 캡처", "E924", None, None),
    "lock":      ("화면 잠금", "E72E", None, None),
    "monitor":   ("화면 끄기", "E7F4", None, None),
    "sleep":     ("절전", "E708", None, "PC를 절전 모드로 바꿀까요?"),
    "ram":       ("RAM 청소", "E950", None, None),
    "clipboard": ("클립보드", "E77F", None, None),
    "focus":     ("집중 모드", "E7ED", "E7ED", None),
    "mute":      ("음소거", "E767", "E74F", None),
    "wallpaper": ("배경 멈춤", "E8B9", "E8B9", None),
    "taskmgr":   ("작업 관리자", "E9D9", None, None),
    "calc":      ("계산기", "E8EF", None, None),
    "settings":  ("Windows 설정", "E713", None, None),
    "empty_bin": ("휴지통 비우기", "E74D", None, None),   # 확인은 화면에서 개수/용량과 함께
}
DEFAULT = ["mic", "capture", "lock", "ram"]


# ---------------- 마이크 (기본 녹음 장치) ----------------
def _mic_endpoint():
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    comtypes.CoInitialize()
    dev = AudioUtilities.GetMicrophone()
    if dev is None:
        return None
    if hasattr(dev, "EndpointVolume"):
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return iface.QueryInterface(IAudioEndpointVolume)


def mic_muted():
    try:
        ep = _mic_endpoint()
        return None if ep is None else bool(ep.GetMute())
    except Exception as e:
        log.debug("마이크 상태 확인 실패: %s", e)
        return None


def toggle_mic():
    ep = _mic_endpoint()
    if ep is None:
        return None
    ep.SetMute(0 if ep.GetMute() else 1, None)
    return bool(ep.GetMute())


# ---------------- 기타 ----------------
def _win_combo(vk):
    """Win + 키 누르기 (예: Win+V 클립보드 기록)."""
    k = ctypes.windll.user32.keybd_event
    k(0x5B, 0, 0, 0)
    k(vk, 0, 0, 0)
    k(vk, 0, 2, 0)
    k(0x5B, 0, 2, 0)


def run(action: str):
    if action == "mic":
        return {"on": toggle_mic()}
    if action == "capture":
        os.startfile("ms-screenclip:")
    elif action == "lock":
        ctypes.windll.user32.LockWorkStation()
    elif action == "monitor":
        time.sleep(0.5)   # 클릭 직후 마우스 움직임으로 바로 켜지지 않도록
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)   # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 끄기
    elif action == "sleep":
        ctypes.windll.powrprof.SetSuspendState(False, False, False)
    elif action == "ram":
        return system.clean_ram()
    elif action == "clipboard":
        _win_combo(0x56)
    elif action == "focus":
        return {"on": system.toggle_focus()}
    elif action == "mute":
        from . import media
        media.toggle_mute()
        return {"on": media.get_volume().get("muted")}
    elif action == "wallpaper":
        return {"on": system.toggle_wallpaper()}
    elif action == "taskmgr":
        subprocess.Popen(["taskmgr.exe"])
    elif action == "calc":
        subprocess.Popen(["calc.exe"])
    elif action == "settings":
        os.startfile("ms-settings:")
    elif action == "empty_bin":
        return system.empty_recycle_bin()
    else:
        return None
    return {"ok": True}


def selected() -> list[str]:
    q = [a for a in load_config().get("quick", DEFAULT) if a in ACTIONS]
    return q or DEFAULT


def buttons() -> list[dict]:
    """화면에 그릴 버튼 목록 + 켜짐 상태."""
    st = system.quick_state()
    out = []
    for a in selected():
        name, glyph, on_glyph, confirm = ACTIONS[a]
        on = None
        if a == "mic":
            m = mic_muted()
            on = m      # 음소거되어 있으면 '켜짐(강조)' 으로 표시
        elif a == "focus":
            on = st["focus"]
        elif a == "wallpaper":
            on = st["wallpaperPaused"]
        elif a == "mute":
            from . import media
            on = media.get_volume().get("muted")
        out.append({"id": a, "name": name, "glyph": on_glyph if (on and on_glyph) else glyph, "on": bool(on),
                    "confirm": confirm or ""})
    return out


def choices() -> list[dict]:
    hide_wall = not load_config().get("wallpaper_engine_exe")
    return [{"id": k, "name": v[0]} for k, v in ACTIONS.items() if not (k == "wallpaper" and hide_wall)]
