"""전역 단축키 (RegisterHotKey). 어느 창에 있든 단축키를 누르면 콜백을 부른다.

단축키 문자열 예: "Ctrl+Alt+H", "Win+Shift+Space", "F9".
RegisterHotKey / UnregisterHotKey 는 같은 스레드에서 불러야 해서, 전용 스레드가 메시지 루프를 돌며 등록/해제를 맡는다.
"""
import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger("hud")
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_APP = 0x0312, 0x8000
HOTKEY_ID = 0xB0D

MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
MOD_ORDER = ["Ctrl", "Alt", "Shift", "Win"]
KEYS = {"space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "pause": 0x13, "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE,
        ",": 0xBC, ".": 0xBE, "/": 0xBF}
KEYS.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
KEYS.update({str(d): 0x30 + d for d in range(10)})
KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})
KEYS.update({f"num{d}": 0x60 + d for d in range(10)})

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]


def parse(spec: str):
    """'Ctrl+Alt+H' → (modifiers, vk, 정리된 문자열). 잘못된 문자열이면 None."""
    parts = [p.strip() for p in (spec or "").split("+") if p.strip()]
    if not parts:
        return None
    mods, key = 0, None
    for p in parts:
        low = p.lower()
        if low in ("control",):
            low = "ctrl"
        if low in MODS:
            mods |= MODS[low]
        elif key is None and low in KEYS:
            key = low
        else:
            return None
    if key is None:
        return None
    # 수식키 없이 쓸 수 있는 건 F 키, Pause 뿐 (글자 키만 등록하면 그 글자를 칠 수 없게 된다)
    if not mods and not (key.startswith("f") and key[1:].isdigit()) and key != "pause":
        return None
    names = [m for m in MOD_ORDER if mods & MODS[m.lower()]]
    return mods, KEYS[key], "+".join(names + [_label(key)])


PRETTY = {"pageup": "PageUp", "pagedown": "PageDown", "esc": "Esc"}


def _label(key: str) -> str:
    if key in PRETTY:
        return PRETTY[key]
    if len(key) == 1:
        return key.upper()
    if key.startswith("num"):
        return f"Num{key[3:]}"
    if key[0] == "f" and key[1:].isdigit():
        return key.upper()
    return key.capitalize()


class Hotkey:
    def __init__(self, callback):
        self._callback = callback
        self._tid = 0
        self._ready = threading.Event()
        self._pending = None          # (spec, Event, 결과 dict)
        self.spec = ""
        threading.Thread(target=self._run, daemon=True, name="hotkey").start()
        self._ready.wait(3)

    def set(self, spec: str) -> dict:
        """단축키를 바꾼다. 빈 문자열이면 끔. 결과: {ok, spec, error}."""
        done, result = threading.Event(), {}
        self._pending = (spec or "", done, result)
        user32.PostThreadMessageW(self._tid, WM_APP + 1, 0, 0)
        done.wait(3)
        return result or {"ok": False, "spec": self.spec, "error": "단축키를 등록하지 못했어요"}

    def suspend(self, on: bool):
        """설정 화면에서 새 단축키를 입력받는 동안 잠시 끈다."""
        user32.PostThreadMessageW(self._tid, WM_APP + 2, 1 if on else 0, 0)

    def _register(self, spec: str) -> dict:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        if not spec:
            self.spec = ""
            return {"ok": True, "spec": ""}
        parsed = parse(spec)
        if not parsed:
            return {"ok": False, "spec": self.spec, "error": "Ctrl / Alt / Shift / Win 중 하나와 함께 눌러 주세요"}
        mods, vk, label = parsed
        if not user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            old = parse(self.spec)
            if old:   # 실패하면 원래 단축키를 되살린다
                user32.RegisterHotKey(None, HOTKEY_ID, old[0] | MOD_NOREPEAT, old[1])
            return {"ok": False, "spec": self.spec, "error": f"{label} 은(는) 다른 프로그램이 이미 쓰고 있어요"}
        self.spec = label
        log.info("단축키 등록: %s", label)
        return {"ok": True, "spec": label}

    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # 이 스레드의 메시지 큐 만들기
        self._ready.set()
        suspended_spec = None
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            try:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    threading.Thread(target=self._callback, daemon=True).start()
                elif msg.message == WM_APP + 1 and self._pending:
                    spec, done, result = self._pending
                    self._pending = None
                    suspended_spec = None
                    result.update(self._register(spec))
                    done.set()
                elif msg.message == WM_APP + 2:
                    if msg.wParam and suspended_spec is None:
                        suspended_spec = self.spec
                        user32.UnregisterHotKey(None, HOTKEY_ID)
                    elif not msg.wParam and suspended_spec is not None:
                        self._register(suspended_spec)
                        suspended_spec = None
            except Exception:
                log.exception("단축키 처리 중 오류")
