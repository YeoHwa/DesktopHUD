"""실행 파일(.exe) / 아이콘(.ico) / 이미지에서 아이콘을 꺼내 PNG data URL 로 돌려준다 (캐시 사용)."""
import base64
import hashlib
import io
import logging
import os

from PIL import Image

from .config import CACHE_DIR

log = logging.getLogger("hud")
ICON_DIR = CACHE_DIR / "icons"
ICON_DIR.mkdir(exist_ok=True)
SIZE = 96


def _clean(path: str) -> str:
    path = os.path.expandvars((path or "").strip().strip('"'))
    # "C:\x.exe,0" 형식의 인덱스 제거
    if "," in path and not os.path.exists(path):
        path = path.rsplit(",", 1)[0].strip('"')
    return path.replace("/", "\\")


def _load(path: str) -> Image.Image | None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".exe":
        from icoextract import IconExtractor
        data = IconExtractor(path).get_icon(num=0)
        img = Image.open(data)
    else:
        img = Image.open(path)
    if getattr(img, "format", "") == "ICO" and hasattr(img, "ico"):
        sizes = sorted(img.ico.sizes(), key=lambda s: s[0] * s[1])
        img.size = sizes[-1]
    img.load()
    return img.convert("RGBA")


def icon_data_url(path: str) -> str:
    """아이콘을 못 꺼내면 빈 문자열."""
    path = _clean(path)
    if not path or not os.path.exists(path):
        return ""
    try:
        st = os.stat(path)
        key = hashlib.sha1(f"{path}|{st.st_mtime}|{SIZE}".encode()).hexdigest()
        cached = ICON_DIR / f"{key}.png"
        if not cached.exists():
            img = _load(path)
            img.thumbnail((SIZE, SIZE), Image.LANCZOS)
            canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img)
            canvas.save(cached, "PNG")
        return "data:image/png;base64," + base64.b64encode(cached.read_bytes()).decode()
    except Exception as e:
        log.warning("아이콘 추출 실패 %s: %s", path, e)
        return ""


def bytes_to_data_url(data: bytes, max_size=160) -> str:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
