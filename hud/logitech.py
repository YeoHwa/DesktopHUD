"""Logitech 무선 마우스 배터리 — 수신기(LIGHTSPEED / Unifying / Bolt)에 HID++ 2.0 으로 직접 묻는다.

G HUB 가 없는 PC (예: Logi Options+ 사용자) 에서도 배터리를 볼 수 있게 하기 위한 것.
  1) Root 기능(0x0000)에 'Unified Battery(0x1004)' 기능 번호를 묻고
  2) 그 기능의 getStatus(fn 1) → [잔량 %, 단계, 충전 상태, 외부 전원]
Unified Battery 가 없는 옛 장치는 'Battery Status(0x1000)' 로 대신 읽는다.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

from . import razer as hidutil   # HID 장치 열거/정보 도우미 재사용

log = logging.getLogger("hud")
LOGI_VID = 0x046D
SW_ID = 0x0A
k32 = ctypes.WinDLL("kernel32")
k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
k32.WriteFile.argtypes = k32.ReadFile.argtypes
k32.CreateEventW.restype = wintypes.HANDLE
k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
k32.ResetEvent.argtypes = [wintypes.HANDLE]
k32.CancelIo.argtypes = [wintypes.HANDLE]
k32.CloseHandle.argtypes = [wintypes.HANDLE]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


def _caps(handle):
    pp = ctypes.c_void_p()
    if not hidutil.hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)) or not pp.value:
        return None
    c = hidutil.HIDP_CAPS()
    hidutil.hid.HidP_GetCaps(pp, ctypes.byref(c))
    hidutil.hid.HidD_FreePreparsedData(pp)
    return c


class _Channel:
    """수신기의 HID++ long(20바이트) 통로."""

    def __init__(self, path):
        self.h = k32.CreateFileW(path, 0xC0000000, 0x3, None, 3, 0x40000000, None)  # RW, 공유, OVERLAPPED
        if not self.h or self.h == hidutil.INVALID:
            raise OSError("열기 실패")
        self.ev = k32.CreateEventW(None, True, False, None)

    def close(self):
        k32.CloseHandle(self.ev)
        k32.CloseHandle(self.h)

    def call(self, dev, feat, fn, params=b"", timeout=1.0):
        req = bytes([0x11, dev, feat, (fn << 4) | SW_ID]) + params.ljust(16, b"\0")
        buf = (ctypes.c_ubyte * 20)(*req)
        ov = OVERLAPPED(hEvent=self.ev)
        k32.ResetEvent(self.ev)
        k32.WriteFile(self.h, buf, 20, None, ctypes.byref(ov))
        if k32.WaitForSingleObject(self.ev, 500) != 0:
            k32.CancelIo(self.h)
            return None
        end = time.time() + timeout
        while time.time() < end:
            rb = (ctypes.c_ubyte * 20)()
            ov = OVERLAPPED(hEvent=self.ev)
            k32.ResetEvent(self.ev)
            k32.ReadFile(self.h, rb, 20, None, ctypes.byref(ov))
            if k32.WaitForSingleObject(self.ev, max(1, int((end - time.time()) * 1000))) != 0:
                k32.CancelIo(self.h)
                return None
            r = bytes(rb)
            if r[0] != 0x11 or r[1] != dev:
                continue                                   # 다른 장치/알림
            if r[2] == 0xFF and r[3] == feat:              # HID++ 2.0 오류 응답
                return None
            if r[2] == feat and r[3] == ((fn << 4) | SW_ID):
                return r[4:]
        return None


def _hidpp_paths():
    hidutil_vid = hidutil.RAZER_VID
    try:
        hidutil.RAZER_VID = LOGI_VID
        paths = hidutil._hid_paths()
    finally:
        hidutil.RAZER_VID = hidutil_vid
    out = []
    for p in paths:
        h = hidutil._open(p)
        if not h:
            continue
        try:
            c = _caps(h)
            if c and c.UsagePage == 0xFF00 and c.OutputReportByteLength == 20:
                out.append(p)
        finally:
            k32.CloseHandle(h)
    return out


def _read(ch, dev):
    """(잔량%, 충전중) 또는 None."""
    r = ch.call(dev, 0x00, 0, bytes([0x10, 0x04]))           # Unified Battery
    if r and r[0]:
        s = ch.call(dev, r[0], 1)
        if s:
            return s[0], s[2] in (1, 2)
    r = ch.call(dev, 0x00, 0, bytes([0x10, 0x00]))           # Battery Status (옛 장치)
    if r and r[0]:
        s = ch.call(dev, r[0], 0)
        if s:
            return s[0], s[2] in (1, 2, 3)
    return None


def _name(ch, dev):
    """장치 이름 (Device Name 0x0005)."""
    r = ch.call(dev, 0x00, 0, bytes([0x00, 0x05]))
    if not r or not r[0]:
        return ""
    idx = r[0]
    n = ch.call(dev, idx, 0)
    if not n:
        return ""
    total, name = n[0], b""
    while len(name) < total:
        part = ch.call(dev, idx, 1, bytes([len(name)]))
        if not part:
            break
        name += part[: total - len(name)]
    return name.decode("utf-8", "replace").strip("\0 ")


class LogitechBattery:
    source = "Logitech"

    def __init__(self):
        self.state = {"ok": False, "status": "nodevice", "source": self.source}
        self._found = None   # (path, dev, name)
        self.paused = lambda: False
        threading.Thread(target=self._run, daemon=True, name="logitech").start()

    def _scan(self):
        for path in _hidpp_paths():
            try:
                ch = _Channel(path)
            except OSError:
                continue
            try:
                for dev in (1, 2, 3, 4, 5, 6, 0xFF):        # 수신기에 짝지은 장치 번호 / 유선(0xFF)
                    res = _read(ch, dev)
                    if res:
                        name = _name(ch, dev) or "Logitech 마우스"
                        log.info("Logitech 장치 찾음: %s (dev %d)", name, dev)
                        return path, dev, name
            finally:
                ch.close()
        return None

    def _run(self):
        time.sleep(15)   # G HUB 가 먼저 연결될 기회를 준다
        idle = 30
        while True:
            if self.paused():
                self.state = {"ok": False, "status": "nodevice", "source": self.source}
                time.sleep(30)
                continue
            try:
                if self._found is None:
                    self._found = self._scan()
                    idle = 30 if self._found else min(300, idle * 2)   # 못 찾으면 점점 드물게
                if self._found:
                    path, dev, name = self._found
                    ch = _Channel(path)
                    try:
                        res = _read(ch, dev)
                    finally:
                        ch.close()
                    if res:
                        self.state = {"ok": True, "status": "ok", "source": self.source, "name": name,
                                      "percent": res[0], "charging": res[1], "hours": None, "updated": time.time()}
                    else:   # 마우스가 꺼졌거나 잠듦 → 다음에 다시 찾기
                        self._found = None
                        self.state = {"ok": False, "status": "nodevice", "source": self.source}
            except Exception as e:
                log.debug("Logitech 직접 읽기 실패: %s", e)
                self._found = None
            time.sleep(60 if self._found else idle)
