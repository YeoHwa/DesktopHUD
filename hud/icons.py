"""아이콘을 PNG data URL 로 돌려준다 (모두 캐시).

- 프로그램: Windows 셸이 보여 주는 실제 앱 아이콘 (exe, 바로가기, 스토어 앱 shell:AppsFolder\\..., 웹 앱 포함)
- 웹사이트: 그 사이트가 내놓은 공식 아이콘 (apple-touch-icon / favicon) 을 내려받아 사용
로고 파일은 저장소에 포함하지 않고, 실행하는 PC 에서 그때그때 가져온다.
"""
import base64
import ctypes
import hashlib
import io
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from urllib.parse import urljoin, urlparse

from PIL import Image

from .config import CACHE_DIR

log = logging.getLogger("hud")
ICON_DIR = CACHE_DIR / "icons"
FAV_DIR = CACHE_DIR / "favicons"
for _d in (ICON_DIR, FAV_DIR):
    _d.mkdir(exist_ok=True)
SIZE = 96
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="icon")
_fav_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="favicon")   # 따로 둬야 서로 기다리다 멈추지 않음
_pending: set[str] = set()
_lock = threading.Lock()


def _png_url(path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _save_square(img: Image.Image, dest):
    img = img.convert("RGBA")
    bbox = img.getbbox()            # 투명한 여백 잘라내기
    if bbox:
        img = img.crop(bbox)
    scale = SIZE / max(img.width, img.height)       # 작은 아이콘은 키우고 큰 아이콘은 줄임
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img)
    canvas.save(dest, "PNG")


# ---------------- 프로그램 아이콘 (Windows 셸) ----------------
class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _shell_image(target: str) -> Image.Image | None:
    """IShellItemImageFactory 로 셸 아이콘을 비트맵으로 받는다."""
    import comtypes
    from comtypes import GUID, HRESULT, IUnknown, COMMETHOD

    class IShellItemImageFactory(IUnknown):
        _iid_ = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
        _methods_ = [COMMETHOD([], HRESULT, "GetImage", (["in"], _SIZE, "size"), (["in"], ctypes.c_int, "flags"),
                               (["out"], ctypes.POINTER(wintypes.HBITMAP), "phbm"))]

    comtypes.CoInitialize()
    shell32, gdi32, user32 = ctypes.windll.shell32, ctypes.windll.gdi32, ctypes.windll.user32
    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    ptr = ctypes.c_void_p()
    iid = IShellItemImageFactory._iid_
    if shell32.SHCreateItemFromParsingName(target, None, ctypes.byref(iid), ctypes.byref(ptr)) != 0 or not ptr.value:
        return None
    factory = ctypes.cast(ptr, ctypes.POINTER(IShellItemImageFactory))   # 해제는 comtypes 가 알아서 함
    hbm = factory.GetImage(_SIZE(256, 256), 0x4 | 0x1)   # ICONONLY | BIGGERSIZEOK
    try:
        bm = _BITMAP()
        gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        bi = _BMIH(ctypes.sizeof(_BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = user32.GetDC(None)
        gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bi), 0)
        user32.ReleaseDC(None, hdc)
        img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
        # 셸 비트맵은 보통 '미리 곱한 알파'(색 ≤ 알파) → 원래 색으로 되돌린다
        from PIL import ImageChops, ImageMath
        r, g, b, a = img.split()
        if a.getextrema()[1] == 0:
            return img.convert("RGB").convert("RGBA")     # 알파가 없는 비트맵
        premultiplied = all(ImageChops.subtract(c, a).getextrema()[1] == 0 for c in (r, g, b))
        if premultiplied:
            def unmul(c):
                return ImageMath.lambda_eval(lambda e: e["convert"](e["c"] * 255 / e["max"](e["a"], 1), "L"), c=c, a=a)
            img = Image.merge("RGBA", (unmul(r), unmul(g), unmul(b), a))
        return img
    finally:
        gdi32.DeleteObject(hbm)


def _clean(path: str) -> str:
    path = os.path.expandvars((path or "").strip().strip('"'))
    if "," in path and not os.path.exists(path):          # "C:\x.exe,0" 의 인덱스 제거
        path = path.rsplit(",", 1)[0].strip('"')
    return path if path.startswith("shell:") else path.replace("/", "\\")


def _load_file(path: str) -> Image.Image:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".exe":
        from icoextract import IconExtractor
        img = Image.open(IconExtractor(path).get_icon(num=0))
    else:
        img = Image.open(path)
    if getattr(img, "format", "") == "ICO" and hasattr(img, "ico"):
        img.size = sorted(img.ico.sizes(), key=lambda s: s[0] * s[1])[-1]
    img.load()
    return img


def icon_data_url(path: str) -> str:
    """exe / ico / 이미지 / 바로가기 / shell:AppsFolder\\... 의 아이콘. 못 꺼내면 빈 문자열."""
    path = _clean(path)
    if not path:
        return ""
    is_shell = path.startswith("shell:")
    if not is_shell and not os.path.exists(path):
        return ""
    try:
        stamp = "" if is_shell else os.stat(path).st_mtime
        cached = ICON_DIR / (hashlib.sha1(f"{path}|{stamp}|{SIZE}|2".encode()).hexdigest() + ".png")
        if not cached.exists():
            img = None
            if not is_shell and os.path.splitext(path)[1].lower() in (".ico", ".png", ".jpg", ".jpeg"):
                img = _load_file(path)
            if img is None:
                try:
                    img = _shell_image(path)
                except Exception as e:
                    log.debug("셸 아이콘 실패 %s: %s", path, e)
            if img is None and not is_shell:
                img = _load_file(path)
            if img is None:
                return ""
            _save_square(img, cached)
        return _png_url(cached)
    except Exception as e:
        log.warning("아이콘 추출 실패 %s: %s", path, e)
        return ""


# ---------------- 웹사이트 아이콘 ----------------
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def _fav_file(url: str):
    host = urlparse(url).netloc.lower() or url
    return FAV_DIR / (re.sub(r"[^a-z0-9.-]", "_", host) + ".png")


def _fetch_favicon(url: str):
    import requests
    dest = _fav_file(url)
    try:
        page = requests.get(url, headers=_UA, timeout=6)
        base = page.url
        cands = []
        for tag in re.findall(r"<link\b[^>]*>", page.text[:200_000], re.I):
            rel = re.search(r'rel=["\']?([^"\'>]+)', tag, re.I)
            href = re.search(r'href=["\']?([^"\'\s>]+)', tag, re.I)
            if not rel or not href or "icon" not in rel[1].lower():
                continue
            sizes = re.search(r'sizes=["\']?(\d+)', tag, re.I)
            r_low = rel[1].lower()
            score = int(sizes[1]) if sizes else (512 if "fluid" in r_low else 180 if "apple" in r_low else 32)
            if "mask" in r_low:
                continue                # 단색 실루엣용 아이콘은 제외
            if href[1].lower().endswith(".svg"):
                score = -1              # SVG 는 변환할 수 없어 마지막 후보
            cands.append((score, urljoin(base, href[1].replace("&amp;", "&"))))
        p = urlparse(base)
        cands.append((16, f"{p.scheme}://{p.netloc}/favicon.ico"))
        for _, icon_url in sorted(cands, reverse=True):
            try:
                r = requests.get(icon_url, headers=_UA, timeout=6)
                if r.status_code != 200 or len(r.content) < 100:
                    continue
                img = Image.open(io.BytesIO(r.content))
                if getattr(img, "format", "") == "ICO" and hasattr(img, "ico"):
                    img.size = sorted(img.ico.sizes(), key=lambda s: s[0] * s[1])[-1]
                img.load()
                _save_square(img, dest)
                return
            except Exception:
                continue
        log.info("사이트 아이콘을 찾지 못함: %s", url)
    except Exception as e:
        log.info("사이트 아이콘 실패 %s: %s", url, e)
    finally:
        with _lock:
            _pending.discard(url)


def favicon_data_url(url: str, wait: float = 0) -> str:
    """캐시에 있으면 바로, 없으면 받아 온다 (wait 초까지 기다림, 0 이면 백그라운드로만)."""
    if not url.startswith(("http://", "https://")):
        return ""
    dest = _fav_file(url)
    if dest.exists():
        return _png_url(dest)
    with _lock:
        fut = None
        if url not in _pending:
            _pending.add(url)
            fut = _fav_pool.submit(_fetch_favicon, url)
    if fut and wait:
        try:
            fut.result(timeout=wait)
        except Exception:
            pass
    return _png_url(dest) if dest.exists() else ""


def official_icon(item: dict, wait: float = 4) -> str:
    """바로가기 항목({target, icon})의 공식 아이콘."""
    if item.get("icon") and not str(item["icon"]).startswith("data:"):
        url = icon_data_url(item["icon"])
        if url:
            return url
    target = os.path.expandvars(item.get("iconTarget") or item.get("target") or "")
    if target.startswith(("http://", "https://")):
        return favicon_data_url(target, wait)
    if target.lower() in ("wt.exe", "powershell.exe", "cmd.exe"):
        from . import detect
        app = detect.find_start_app("Terminal", "Windows Terminal", "터미널") if target.lower() == "wt.exe" else ""
        target = app or os.path.expandvars(rf"%WINDIR%\System32\WindowsPowerShell\v1.0\{target}" if target.lower() == "powershell.exe" else rf"%WINDIR%\System32\{target}")
    return icon_data_url(target)


def official_icons(items: list[dict], wait: float = 4) -> list[dict]:
    """여러 항목의 아이콘을 동시에 가져와 'icon' 에 data URL 로 채운다."""
    futures = [_pool.submit(official_icon, it, wait) for it in items]
    out = []
    for it, f in zip(items, futures):
        o = dict(it)
        try:
            o["icon"] = f.result(timeout=wait + 2) or ""
        except Exception:
            o["icon"] = ""
        out.append(o)
    return out


def bytes_to_data_url(data: bytes, max_size=160) -> str:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
