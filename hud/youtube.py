"""YouTube: 채널 검색, 새 영상(RSS), 라이브 확인. API 키 없이 공개 주소만 쓴다.

- 새 영상: https://www.youtube.com/feeds/videos.xml?channel_id=...  (채널당 최근 15개, 아주 가벼움)
- 라이브: RSS 에 올라온 최근 영상 중 '라이브일 수 있는 것'만 player 정보(약 6KB)로 확인한다.
  일반 영상/끝난 방송으로 확인되면 다시 묻지 않으므로, 채널 페이지(수백 KB)를 매번 받지 않아도 된다.
- 검색/채널 확인은 YouTube 웹이 쓰는 내부 API(youtubei)를 쓰므로, YouTube 쪽이 바뀌면 동작하지 않을 수 있다.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

log = logging.getLogger("hud")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}
COOKIES = {"SOCS": "CAI"}      # 유럽 등에서 뜨는 동의 화면 건너뛰기
CONTEXT = {"client": {"clientName": "WEB", "clientVersion": "2.20241120.01.00", "hl": "ko", "gl": "KR"}}
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}
CHANNEL_RE = re.compile(r"^UC[\w-]{22}$")


def _innertube(endpoint: str, **body):
    r = requests.post(f"https://www.youtube.com/youtubei/v1/{endpoint}?prettyPrint=false",
                      json={"context": CONTEXT, **body}, headers=UA, cookies=COOKIES, timeout=10)
    r.raise_for_status()
    return r.json()


def _walk(node, key):
    """중첩된 JSON 에서 key 를 가진 객체를 모두 찾는다."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            else:
                yield from _walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)


def _text(t) -> str:
    if not t:
        return ""
    return t.get("simpleText") or "".join(r.get("text", "") for r in t.get("runs", []))


def _https(url: str) -> str:
    return "https:" + url if url.startswith("//") else url


# ---------------- 채널 찾기 ----------------
def search(keyword: str) -> list[dict]:
    keyword = keyword.strip()
    if "youtube.com/" in keyword or "youtu.be/" in keyword or keyword.startswith("@") or CHANNEL_RE.match(keyword):
        ch = resolve(keyword)
        return [ch] if ch else []
    try:
        data = _innertube("search", query=keyword, params="EgIQAg==")   # 필터: 채널만
    except Exception:
        log.exception("YouTube 검색 실패")
        return []
    out = []
    for c in _walk(data, "channelRenderer"):
        thumbs = (c.get("thumbnail") or {}).get("thumbnails") or []
        # YouTube 는 핸들이 있는 채널이면 subscriberCountText 자리에 @핸들을, videoCountText 자리에 구독자 수를 넣는다
        texts = [_text(c.get("subscriberCountText")), _text(c.get("videoCountText"))]
        subs = next((t for t in texts if "구독자" in t), "")
        handle = next((t for t in texts if t.startswith("@")), "")
        out.append({"id": c["channelId"], "name": _text(c.get("title")), "image": _https(thumbs[-1]["url"]) if thumbs else "",
                    "sub": " · ".join(filter(None, [handle, subs])), "live": False})
        if len(out) >= 8:
            break
    return out


def resolve(text: str) -> dict | None:
    """채널 주소 / @핸들 / 채널 ID → {id, name, image}."""
    text = text.strip()
    if CHANNEL_RE.match(text):
        url = f"https://www.youtube.com/channel/{text}"
    elif text.startswith("@"):
        url = f"https://www.youtube.com/{text}"
    else:
        url = text if text.startswith("http") else "https://" + text
    try:
        page = requests.get(url, headers=UA, cookies=COOKIES, timeout=10).text
    except Exception:
        log.exception("YouTube 채널 확인 실패: %s", text)
        return None
    m = re.search(r'"externalId":"(UC[\w-]{22})"', page) or re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', page)
    if not m:
        # 영상 주소를 넣은 경우: 그 영상의 채널
        m = re.search(r'"channelId":"(UC[\w-]{22})"', page)
        if not m:
            return None
        if "/channel/" not in url:
            return resolve(m.group(1))
    name = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    image = re.search(r'<meta property="og:image" content="([^"]*)"', page)
    from html import unescape
    return {"id": m.group(1), "name": unescape(name.group(1)) if name else m.group(1),
            "image": unescape(image.group(1)) if image else "", "sub": "", "live": False}


# ---------------- 새 영상 ----------------
def _ts(s: str) -> float:
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def feed(channel_id: str) -> dict:
    """채널 RSS → {name, videos: [{id, title, published, views, channel}]} (최근 15개, 새것부터)."""
    r = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}, headers=UA, timeout=10)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    name = root.findtext("a:title", "", NS)
    videos = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", "", NS)
        if not vid:
            continue
        stats = e.find("m:group/m:community/m:statistics", NS)
        videos.append({"id": vid, "title": e.findtext("a:title", "", NS), "published": _ts(e.findtext("a:published", "", NS)),
                       "views": int(stats.get("views", 0)) if stats is not None else 0, "channel": channel_id, "channelName": name})
    videos.sort(key=lambda v: -v["published"])
    return {"name": name, "videos": videos}


_shorts: dict[str, bool] = {}


def is_short(video_id: str) -> bool:
    """/shorts/ID 주소가 그대로 열리면(200) 쇼츠, 일반 영상이면 watch 로 넘겨진다(303)."""
    if video_id not in _shorts:
        try:
            r = requests.head(f"https://www.youtube.com/shorts/{video_id}", headers=UA, cookies=COOKIES,
                              allow_redirects=False, timeout=8)
            _shorts[video_id] = r.status_code == 200
        except Exception:
            return False
    return _shorts[video_id]


# ---------------- 라이브 ----------------
_final: set[str] = set()     # 일반 영상이거나 이미 끝난 방송으로 확인된 영상 (다시 묻지 않음)
_upcoming: set[str] = set()  # 예정된 라이브 (대기실) — 새 영상 목록에서 뺀다


def video_state(video_id: str) -> dict:
    d = _innertube("player", videoId=video_id)
    vd = d.get("videoDetails") or {}
    return {"live": bool(vd.get("isLive")), "upcoming": bool(vd.get("isUpcoming")),
            "liveContent": bool(vd.get("isLiveContent")), "title": vd.get("title") or ""}


def live_viewers(video_id: str) -> int:
    """라이브 동시 시청자 수 (모르면 0)."""
    try:
        d = _innertube("updated_metadata", videoId=video_id)
        for v in _walk(d, "videoViewCountRenderer"):
            txt = _text(v.get("viewCount")) or _text(v.get("originalViewCount"))
            digits = re.sub(r"[^\d]", "", txt)
            if digits:
                return int(digits)
    except Exception as e:
        log.debug("YouTube 시청자 수 실패 %s: %s", video_id, e)
    return 0


def find_live(videos: list[dict]) -> dict | None:
    """RSS 의 최근 영상 중 지금 라이브인 것. 없으면 None."""
    for v in videos:       # 24시간 라이브처럼 오래 이어지는 방송도 있으니 기간으로 자르지 않는다 (영상마다 한 번만 확인)
        vid = v["id"]
        if vid in _final:
            continue
        try:
            st = video_state(vid)
        except Exception as e:
            log.info("YouTube 영상 확인 실패 %s: %s", vid, e)
            continue
        if st["upcoming"]:
            _upcoming.add(vid)
            continue
        _upcoming.discard(vid)
        if st["live"]:
            return {"videoId": vid, "title": st["title"] or v["title"], "viewers": live_viewers(vid)}
        _final.add(vid)           # 일반 영상, 또는 끝난 방송
    return None


def channel_info(channel_id: str) -> dict:
    """이름/프로필 그림이 비어 있을 때 채우기."""
    return resolve(channel_id) or {}
