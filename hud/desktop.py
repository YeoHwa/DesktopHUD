"""HUD 창을 바탕화면 층에 고정: 항상 다른 창들 뒤, 작업 표시줄/Alt+Tab 에 안 보이게, Win+D 후에도 다시 보이게."""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger("hud")
user32 = ctypes.windll.user32
comctl32 = ctypes.windll.comctl32

WM_WINDOWPOSCHANGING = 0x0046
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOZORDER, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x4, 0x1, 0x2, 0x10
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4

LRESULT = ctypes.c_ssize_t
SUBCLASSPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                  ctypes.c_size_t, ctypes.c_size_t)
comctl32.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
comctl32.DefSubclassProc.restype = LRESULT
comctl32.SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]


class MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]


def make_see_through(form, hwnd):
    """창 바탕을 진짜 투명하게: DWM 유리 영역을 창 전체로 넓히고 바탕을 검정(=투명)으로.
    그러면 WebView2 의 반투명 픽셀이 배경화면과 그대로 섞인다. (UI 스레드에서 호출)"""
    from System.Drawing import Color
    form.BackColor = Color.Black
    dwm = ctypes.windll.dwmapi
    backdrop_none = ctypes.c_int(1)  # DWMSBT_NONE: Mica/아크릴 없이
    dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_none), ctypes.sizeof(backdrop_none))
    hr = dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(-1, -1, -1, -1)))
    log.info("창 투명 처리 hr=%s", hr)


class WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND), ("x", ctypes.c_int),
                ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT)]


_keep = []  # 콜백이 가비지 컬렉션되지 않도록 보관


peek = False  # 테스트용: True 동안은 맨 뒤로 보내지 않음


def peek_front(window, seconds: float):
    """테스트용: 잠깐 맨 앞에 띄웠다가 다시 바탕화면 층으로."""
    global peek
    hwnd = hwnd_of(window)
    peek = True
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)  # TOPMOST
    time.sleep(seconds)
    user32.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)  # NOTOPMOST
    peek = False
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def _proc(hwnd, msg, wparam, lparam, uid, ref):
    if msg == WM_WINDOWPOSCHANGING and not peek:
        pos = ctypes.cast(lparam, ctypes.POINTER(WINDOWPOS)).contents
        pos.hwndInsertAfter = HWND_BOTTOM
        pos.flags &= ~SWP_NOZORDER
    return comctl32.DefSubclassProc(hwnd, msg, wparam, lparam)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]


def fit_height(x: int, y: int, minimum: int = 760) -> int:
    """(x, y) 가 있는 모니터의 작업 영역(작업 표시줄 제외)에서, 위 여백과 같은 여백을 아래에도 두고 꽉 채우는 높이."""
    mon = user32.MonitorFromPoint(wintypes.POINT(int(x) + 10, int(y) + 10), 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return minimum
    work = info.rcWork
    margin = max(0, int(y) - work.top)
    return max(minimum, work.bottom - int(y) - margin)


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                     wintypes.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]


def monitors() -> list[dict]:
    """모니터 목록 (주 모니터 먼저, 그다음 왼쪽부터). 좌표는 작업 표시줄을 뺀 작업 영역."""
    found = []

    def cb(hmon, hdc, rect, lparam):
        info = MONITORINFO(ctypes.sizeof(MONITORINFO))
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            w, m = info.rcWork, info.rcMonitor
            found.append({"left": w.left, "top": w.top, "right": w.right, "bottom": w.bottom,
                          "width": m.right - m.left, "height": m.bottom - m.top, "primary": bool(info.dwFlags & 1)})
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    found.sort(key=lambda m: (not m["primary"], m["left"]))
    for i, m in enumerate(found):
        m["index"] = i
        m["name"] = f"모니터 {i + 1}{' (주 모니터)' if m['primary'] else ''} · {m['width']}×{m['height']}"
    return found


def monitor_at(x: int, y: int) -> dict:
    mons = monitors()
    for m in mons:
        if m["left"] <= x < m["right"] and m["top"] <= y < m["bottom"]:
            return m
    return min(mons, key=lambda m: abs((m["left"] + m["right"]) / 2 - x) + abs((m["top"] + m["bottom"]) / 2 - y))


def hwnd_of(window):
    return wintypes.HWND(window.native.Handle.ToInt64())


def dpi_scale(window) -> float:
    """화면 배율(125%, 150% 등). DPI 를 모르는 창이면 1.0."""
    try:
        return max(1.0, user32.GetDpiForWindow(hwnd_of(window)) / 96)
    except Exception:
        return 1.0


def set_size(window, width: int, height: int):
    """창 크기를 픽셀 그대로 지정 (pywebview 는 테두리 두께만큼 빼서 만들기 때문)."""
    user32.SetWindowPos(hwnd_of(window), None, 0, 0, width, height,
                        SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)


def set_bounds(window, x: int, y: int, width: int, height: int):
    """위치와 크기를 한 번에 (Z 순서는 바탕화면 층 그대로)."""
    user32.SetWindowPos(hwnd_of(window), None, int(x), int(y), int(width), int(height), SWP_NOZORDER | SWP_NOACTIVATE)


user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


def is_visible_on_screen(window, cols: int = 5, rows: int = 9) -> bool:
    """HUD 가 화면에 조금이라도 보이는지. HUD 위를 격자로 찍어 보고, 그 자리 맨 위 창이 HUD 인 점이 하나라도 있으면 보임.
    (HUD 는 항상 맨 뒤라서 다른 창에 완전히 가려지면 False)"""
    hwnd = hwnd_of(window)
    if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
        return False
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return False
    me = hwnd.value
    for i in range(cols):
        for j in range(rows):
            pt = wintypes.POINT(r.left + int(w * (i + 0.5) / cols), r.top + int(h * (j + 0.5) / rows))
            hit = user32.WindowFromPoint(pt)
            if hit and user32.GetAncestor(hit, 2) == me:   # GA_ROOT
                return True
    return False


def set_memory_saving(window, low: bool):
    """가려져 있는 동안 WebView2 메모리 사용을 줄인다 (MemoryUsageTargetLevel)."""
    from System import Action
    form = window.native

    def apply():
        try:
            from Microsoft.Web.WebView2.Core import CoreWebView2MemoryUsageTargetLevel as Level
            core = form.webview.CoreWebView2
            if core is not None:
                core.MemoryUsageTargetLevel = Level.Low if low else Level.Normal
        except Exception as e:
            log.debug("WebView2 메모리 절약 설정 실패: %s", e)

    form.BeginInvoke(Action(apply))


def watch_visibility(window, on_change, interval: float = 1.0):
    """보임/가려짐이 바뀔 때마다 on_change(bool) 호출."""
    def loop():
        last = None
        while True:
            try:
                vis = is_visible_on_screen(window)
                if vis != last:
                    last = vis
                    on_change(vis)
            except Exception as e:
                log.debug("보임 확인 실패: %s", e)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="visibility").start()


def set_zoom(window, zoom: float):
    """HUD 전체 크기 배율 (WebView2 확대/축소)."""
    from System import Action
    form = window.native

    def apply():
        try:
            form.webview.ZoomFactor = float(zoom)
        except Exception as e:
            log.warning("확대 배율 설정 실패: %s", e)

    form.Invoke(Action(apply))


def pin_to_desktop(window, width: int | None = None, height: int | None = None):
    """pywebview 창이 뜬 뒤 호출."""
    form = window.native
    hwnd = hwnd_of(window)
    if width and height:
        set_size(window, width, height)

    def on_ui_thread():
        make_see_through(form, hwnd)
        cb = SUBCLASSPROC(_proc)
        _keep.append(cb)
        # 자식 창(WebView2)이 아니라 최상위 창에 걸어야 Z 순서를 잡을 수 있다
        comctl32.SetWindowSubclass(hwnd, cb, 1, 0)
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    from System import Action
    form.Invoke(Action(on_ui_thread))
    threading.Thread(target=_guard, args=(hwnd,), daemon=True, name="desktop-guard").start()
    log.info("바탕화면 층에 고정 완료")


def _guard(hwnd):
    """Win+D(바탕화면 보기) 등으로 최소화/숨김되면 다시 보이게."""
    while True:
        time.sleep(1.0)
        try:
            if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass
