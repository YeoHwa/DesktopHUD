"""Razer 무선 마우스 배터리 — USB HID 로 직접 읽는다 (Razer Synapse 없이도 동작).

Razer 장치는 90바이트 'feature report' 로 명령을 주고받는다 (openrazer 프로젝트에 공개된 형식).
  배터리 잔량: command_class 0x07, command_id 0x80  → arguments[1] = 0~255
  충전 여부:  command_class 0x07, command_id 0x84  → arguments[1] = 0/1
장치마다 transaction id 가 달라서 0x1F → 0x3F → 0xFF 순서로 시도한다.
"""
import ctypes
import logging
import re
import threading
import time
from ctypes import wintypes

log = logging.getLogger("hud")
RAZER_VID = 0x1532
REPORT_LEN = 90
TRANSACTION_IDS = (0x1F, 0x3F, 0xFF)
MOUSE_HINT = re.compile(r"mouse|viper|deathadder|basilisk|naga|orochi|cobra|mamba|lancehead|atheris|pro click|"
                        r"hyperspeed|dongle|wireless", re.I)

setupapi = ctypes.WinDLL("setupapi")
hid = ctypes.WinDLL("hid")
k32 = ctypes.WinDLL("kernel32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wintypes.DWORD),
                ("Reserved", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT), ("ProductID", wintypes.USHORT),
                ("VersionNumber", wintypes.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT), ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT), ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17), ("rest", wintypes.USHORT * 10)]


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
                                                 ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                            wintypes.DWORD, wintypes.HANDLE]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
for fn in ("HidD_SetFeature", "HidD_GetFeature"):
    getattr(hid, fn).argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
INVALID = wintypes.HANDLE(-1).value


def _hid_paths():
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devs = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x10 | 0x02)  # INTERFACE | PRESENT
    paths, i = [], 0
    try:
        while True:
            data = SP_DEVICE_INTERFACE_DATA(ctypes.sizeof(SP_DEVICE_INTERFACE_DATA))
            if not setupapi.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), i, ctypes.byref(data)):
                break
            i += 1
            need = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(data), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(data), buf, need, None, None):
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if f"vid_{RAZER_VID:04x}" in path.lower():
                    paths.append(path)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devs)
    return paths


def _open(path):
    for access in (0xC0000000, 0):  # GENERIC_READ|WRITE, 그다음 접근 권한 없이
        h = k32.CreateFileW(path, access, 0x3, None, 3, 0, None)  # SHARE_READ|WRITE, OPEN_EXISTING
        if h and h != INVALID:
            return h
    return None


def _feature_len(h):
    pp = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
        return 0
    caps = HIDP_CAPS()
    hid.HidP_GetCaps(pp, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(pp)
    return caps.FeatureReportByteLength


def _product(h):
    buf = ctypes.create_unicode_buffer(128)
    return buf.value if hid.HidD_GetProductString(h, buf, ctypes.sizeof(buf)) else ""


def _request(h, tid, cls, cmd, size=0x02):
    """명령을 보내고 응답의 arguments 를 돌려준다. 실패하면 None."""
    rep = bytearray(REPORT_LEN)
    rep[1], rep[5], rep[6], rep[7] = tid, size, cls, cmd
    crc = 0
    for b in rep[2:88]:
        crc ^= b
    rep[88] = crc
    out = (ctypes.c_ubyte * (REPORT_LEN + 1))(0, *rep)           # 앞의 0 은 report id
    if not hid.HidD_SetFeature(h, out, REPORT_LEN + 1):
        return None
    for _ in range(6):
        time.sleep(0.06)
        resp = (ctypes.c_ubyte * (REPORT_LEN + 1))()
        if not hid.HidD_GetFeature(h, resp, REPORT_LEN + 1):
            return None
        r = bytes(resp)[1:]
        status = r[0]
        if status == 0x01:          # 장치가 바쁨 → 잠깐 뒤 다시
            continue
        if status == 0x02 and r[6] == cls and r[7] == cmd:
            return r[8:88]
        return None
    return None


class RazerBattery:
    source = "Razer"

    def __init__(self):
        self.state = {"ok": False, "status": "nodevice", "source": self.source}
        self._found = None   # (path, tid, name)
        threading.Thread(target=self._run, daemon=True, name="razer").start()

    def _read(self, path, tid):
        h = _open(path)
        if not h:
            return None
        try:
            lvl = _request(h, tid, 0x07, 0x80)
            if lvl is None:
                return None
            chg = _request(h, tid, 0x07, 0x84)
            return round(lvl[1] / 255 * 100), bool(chg and chg[1])
        finally:
            k32.CloseHandle(h)

    def _scan(self):
        """배터리 응답을 주는 Razer 장치를 찾는다."""
        candidates = []
        for path in _hid_paths():
            h = _open(path)
            if not h:
                continue
            try:
                if _feature_len(h) < REPORT_LEN + 1:
                    continue
                name = _product(h)
            finally:
                k32.CloseHandle(h)
            candidates.append((0 if MOUSE_HINT.search(name) else 1, path, name))
        for _, path, name in sorted(candidates):
            for tid in TRANSACTION_IDS:
                res = self._read(path, tid)
                if res and res[0] > 0:
                    clean = re.sub(r"\s*(dongle|receiver|\(wireless\))\s*$", "", name, flags=re.I).replace("Razer ", "").strip()
                    log.info("Razer 장치 찾음: %s (tid=0x%02X)", name, tid)
                    return path, tid, clean or "Razer 마우스"
        return None

    def _run(self):
        idle = 30
        while True:
            try:
                if self._found is None:
                    self._found = self._scan()
                    # 못 찾으면 다음 확인까지 점점 길게 (30초 → 최대 5분), 찾으면 원래대로
                    idle = 30 if self._found else min(300, idle * 2)
                if self._found:
                    path, tid, name = self._found
                    res = self._read(path, tid)
                    if res:
                        self.state = {"ok": True, "status": "ok", "source": self.source, "name": name,
                                      "percent": res[0], "charging": res[1], "hours": None, "updated": time.time()}
                    else:   # 마우스가 꺼졌거나 뽑힘 → 다음에 다시 찾기
                        self._found = None
                        self.state = {"ok": False, "status": "nodevice", "source": self.source}
            except Exception as e:
                log.debug("Razer 확인 실패: %s", e)
                self._found = None
            time.sleep(60 if self._found else idle)
