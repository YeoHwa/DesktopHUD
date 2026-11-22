"""라이브 알림: 치지직 · SOOP · YouTube · Twitch 방송 상태 확인 + YouTube 새 영상 목록, Windows 알림.

모두 각 사이트가 웹에서 쓰는 공개되지 않은 주소를 쓰므로, 사이트 쪽이 바뀌면 그 플랫폼만 동작하지 않을 수 있다.
설정 파일의 streamers: [{platform, id, name, image, notify, since?}]  (platform 이 없으면 치지직 — 이전 버전 설정)
"""
from __future__ import annotations

import logging
import threading
import time

import requests

from . import youtube
from .config import load_config, load_state, save_config, save_state
from .notify import image_file, register_aumid, toast

log = logging.getLogger("hud")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
TWITCH_CLIENT = "kimne78kx3ncx6brgo4mv6wki5h1ko"   # twitch.tv 웹이 쓰는 공개 Client-Id
PLATFORMS = {
    "chzzk": {"name": "치지직", "site": "https://chzzk.naver.com/"},
    "soop": {"name": "SOOP", "site": "https://www.sooplive.co.kr/"},
    "youtube": {"name": "YouTube", "site": "https://www.youtube.com/"},
    "twitch": {"name": "Twitch", "site": "https://www.twitch.tv/"},
}
YT_EVERY = 180            # YouTube 확인 간격(초). RSS 자체가 몇 분씩 늦게 바뀐다.
VIDEO_DAYS = 7            # '새 영상' 목록에 보여 줄 기간
SEEN_MAX = 600


def _https(url: str) -> str:
    return "https:" + url if url and url.startswith("//") else (url or "")


def _platform(s: dict) -> str:
    return s.get("platform") or "chzzk"


def _key(platform: str, sid: str) -> str:
    return f"{platform}:{sid}"


# ---------------- 치지직 ----------------
def _chzzk_get(path, **params):
    r = requests.get("https://api.chzzk.naver.com" + path, params=params, headers=UA, timeout=10)
    r.raise_for_status()
    return r.json().get("content") or {}


def chzzk_check(s: dict) -> dict:
    c = _chzzk_get(f"/polling/v2/channels/{s['id']}/live-status")
    st = {"live": c.get("status") == "OPEN", "title": c.get("liveTitle") or "", "viewers": c.get("concurrentUserCount") or 0,
          "category": c.get("liveCategoryValue") or ""}
    if not s.get("image"):
        ch = _chzzk_get(f"/service/v1/channels/{s['id']}")
        st["profile"] = {"image": ch.get("channelImageUrl") or "", "name": ch.get("channelName") or ""}
    return st


def chzzk_search(q: str) -> list[dict]:
    data = _chzzk_get("/service/v1/search/channels", keyword=q, size=8).get("data", [])
    return [{"id": d["channel"]["channelId"], "name": d["channel"]["channelName"], "image": d["channel"].get("channelImageUrl") or "",
             "sub": f"팔로워 {d['channel'].get('followerCount', 0):,}명", "live": bool(d["channel"].get("openLive"))}
            for d in data if d.get("channel")]


# ---------------- SOOP (구 아프리카TV) ----------------
def soop_check(s: dict) -> dict:
    r = requests.get(f"https://chapi.sooplive.co.kr/api/{s['id']}/station", headers=UA, timeout=10)
    r.raise_for_status()
    d = r.json()
    b = d.get("broad") or {}
    st = {"live": bool(b), "title": b.get("broad_title") or "", "viewers": b.get("current_sum_viewer") or 0, "category": "",
          "broadNo": b.get("broad_no")}
    if not s.get("image"):
        st["profile"] = {"image": _https(d.get("profile_image") or ""), "name": (d.get("station") or {}).get("user_nick") or ""}
    return st


def soop_search(q: str) -> list[dict]:
    r = requests.get("https://sch.sooplive.co.kr/api.php", params={"m": "bjSearch", "v": "3.0", "szKeyword": q, "nListCnt": 8},
                     headers=UA, timeout=10)
    r.raise_for_status()
    return [{"id": d["user_id"], "name": d.get("user_nick") or d["user_id"], "image": _https(d.get("station_logo") or ""),
             "sub": f"@{d['user_id']} · 애청자 {int(d.get('favorite_cnt') or 0):,}명", "live": False}
            for d in (r.json().get("DATA") or [])[:8] if d.get("user_id")]


# ---------------- Twitch ----------------
def _twitch_gql(query: str, **variables):
    r = requests.post("https://gql.twitch.tv/gql", json={"query": query, "variables": variables},
                      headers={**UA, "Client-Id": TWITCH_CLIENT}, timeout=10)
    r.raise_for_status()
    return r.json().get("data") or {}


def twitch_check_many(entries: list[dict]) -> dict[str, dict]:
    out = {}
    logins = [s["id"] for s in entries]
    for i in range(0, len(logins), 50):
        data = _twitch_gql("query($l:[String!]){users(logins:$l){login displayName profileImageURL(width:150) "
                           "stream{title viewersCount game{displayName}}}}", l=logins[i:i + 50])
        for u in data.get("users") or []:
            if not u:
                continue
            stream = u.get("stream") or {}
            out[u["login"]] = {"live": bool(stream), "title": stream.get("title") or "", "viewers": stream.get("viewersCount") or 0,
                               "category": (stream.get("game") or {}).get("displayName") or "",
                               "profile": {"image": u.get("profileImageURL") or "", "name": u.get("displayName") or ""}}
    return out


def twitch_search(q: str) -> list[dict]:
    data = _twitch_gql('query($q:String!){searchFor(userQuery:$q, platform:"web", target:{index:USER, limit:8})'
                       "{users{items{login displayName profileImageURL(width:150) followers{totalCount} stream{id}}}}}", q=q)
    items = ((data.get("searchFor") or {}).get("users") or {}).get("items") or []
    return [{"id": u["login"], "name": u.get("displayName") or u["login"], "image": u.get("profileImageURL") or "",
             "sub": f"@{u['login']} · 팔로워 {(u.get('followers') or {}).get('totalCount', 0):,}명", "live": bool(u.get("stream"))}
            for u in items]


SEARCH = {"chzzk": chzzk_search, "soop": soop_search, "twitch": twitch_search, "youtube": youtube.search}


def watch_url(platform: str, sid: str, st: dict | None = None) -> str:
    st = st or {}
    if platform == "chzzk":
        return f"https://chzzk.naver.com/live/{sid}"
    if platform == "soop":
        return f"https://play.sooplive.co.kr/{sid}/{st['broadNo']}" if st.get("broadNo") else f"https://play.sooplive.co.kr/{sid}"
    if platform == "twitch":
        return f"https://www.twitch.tv/{sid}"
    if platform == "youtube":
        return f"https://www.youtube.com/watch?v={st['videoId']}" if st.get("videoId") else f"https://www.youtube.com/channel/{sid}/live"
    return ""


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


class Live:
    def __init__(self):
        self.status: dict[str, dict] = {}
        self.feeds: dict[str, list[dict]] = {}        # YouTube 채널 ID → 최근 영상
        self._known: dict[str, set[str]] = {}         # 알림용: 채널별로 이미 본 영상 ID
        self._first: set[str] = set()                  # 처음 확인할 때는 알림을 띄우지 않는다
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._yt_at = 0.0
        self._seen = set(load_state().get("yt_seen") or [])
        register_aumid()
        threading.Thread(target=self._run, daemon=True, name="live").start()

    # ---------- 확인 ----------
    def refresh_now(self, youtube_too: bool = True):
        if youtube_too:
            self._yt_at = 0.0
        self._wake.set()

    def _run(self):
        while True:
            try:
                self._poll_streams()
            except Exception:
                log.exception("라이브 확인 중 오류")
            if time.time() - self._yt_at >= YT_EVERY:
                self._yt_at = time.time()
                try:
                    self._poll_youtube()
                except Exception:
                    log.exception("YouTube 확인 중 오류")
            secs = max(30, int(load_config().get("chzzk_poll_seconds", 60)))
            self._wake.wait(secs)
            self._wake.clear()

    def _apply(self, s: dict, st: dict, cfg_changed: list):
        """확인 결과 반영 + 방송이 막 시작됐으면 알림."""
        p = _platform(s)
        key = _key(p, s["id"])
        prof = st.pop("profile", None)
        if prof:
            image = s.get("image") or prof.get("image") or ""
            name = prof.get("name") or s.get("name")
            if (image, name) != (s.get("image"), s.get("name")):
                s["image"], s["name"] = image, name
                cfg_changed.append(True)
        with self._lock:
            old = self.status.get(key, {})
            prev = old.get("live")
            st["since"] = old.get("since") if (prev and st["live"]) else (time.time() if st["live"] else None)
            st["checked"] = time.time()
            self.status[key] = st
        first = key not in self._first
        self._first.add(key)
        if st["live"] and prev is False and not first and s.get("notify", True):
            toast(f"{s.get('name')} 방송 시작", st.get("title") or "", watch_url(p, s["id"], st),
                  image_file(s.get("image", "")), " · ".join(filter(None, [st.get("category"), PLATFORMS[p]["name"]])))

    def _poll_streams(self):
        cfg = load_config()
        changed: list = []
        entries = cfg["streamers"]
        twitch = [s for s in entries if _platform(s) == "twitch"]
        if twitch:
            try:
                res = twitch_check_many(twitch)
                for s in twitch:
                    if s["id"] in res:
                        self._apply(s, res[s["id"]], changed)
            except Exception as e:
                log.info("Twitch 확인 실패: %s", e)
        for s in entries:
            p = _platform(s)
            fn = {"chzzk": chzzk_check, "soop": soop_check}.get(p)
            if not fn:
                continue
            try:
                self._apply(s, fn(s), changed)
            except Exception as e:
                log.info("%s 확인 실패 %s: %s", PLATFORMS[p]["name"], s.get("name"), e)
        if changed:
            self._save_profiles(entries)

    def _poll_youtube(self):
        cfg = load_config()
        entries = [s for s in cfg["streamers"] if _platform(s) == "youtube"]
        changed: list = []
        now = time.time()
        for s in entries:
            cid = s["id"]
            try:
                f = youtube.feed(cid)
            except Exception as e:
                log.info("YouTube 새 영상 확인 실패 %s: %s", s.get("name"), e)
                continue
            videos = f["videos"]
            with self._lock:
                self.feeds[cid] = videos
            if f["name"] and f["name"] != s.get("name"):
                s["name"] = f["name"]
                changed.append(True)
            if not s.get("image"):
                info = youtube.channel_info(cid)
                if info.get("image"):
                    s["image"] = info["image"]
                    changed.append(True)
            # 라이브
            live = youtube.find_live(videos)
            st = {"live": bool(live), "title": (live or {}).get("title", ""), "viewers": (live or {}).get("viewers", 0),
                  "category": "", "videoId": (live or {}).get("videoId")}
            self._apply(s, st, changed)
            # 새 영상 알림
            ids = {v["id"] for v in videos}
            known = self._known.get(cid)
            self._known[cid] = ids | (known or set())
            if known is None:
                continue
            for v in videos:
                if v["id"] in known or now - v["published"] > 86400 * 3:
                    continue
                if live and v["id"] == live["videoId"]:
                    continue          # 라이브는 방송 시작 알림으로 이미 알렸다
                if v["id"] not in youtube._final:
                    continue          # 예정된 라이브 대기실 등
                if s.get("notify", True) and not (cfg.get("youtube", {}).get("hide_shorts") and youtube.is_short(v["id"])):
                    toast(f"{s.get('name')} 새 영상", v["title"], video_url(v["id"]), image_file(s.get("image", "")),
                          "YouTube", action="보러 가기", hero=image_file(f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", 2))
        # 목록에 나올 영상은 쇼츠인지 미리 알아 둔다 (영상당 한 번)
        for v in self._recent_videos(cfg):
            youtube.is_short(v["id"])
        if changed:
            self._save_profiles(cfg["streamers"])

    @staticmethod
    def _save_profiles(entries: list[dict]):
        """확인하면서 알게 된 이름/프로필 그림을 설정에 저장 (그 사이 바뀐 목록은 그대로 둔다)."""
        cfg = load_config()
        by_key = {_key(_platform(s), s["id"]): s for s in entries}
        for s in cfg["streamers"]:
            new = by_key.get(_key(_platform(s), s["id"]))
            if new:
                s["name"], s["image"] = new.get("name", s.get("name")), new.get("image", s.get("image", ""))
        save_config(cfg)

    # ---------- HUD 에서 부르는 기능 ----------
    def list(self) -> list[dict]:
        out = []
        with self._lock:
            for s in load_config()["streamers"]:
                p = _platform(s)
                st = self.status.get(_key(p, s["id"]), {})
                out.append({**s, **st, "platform": p, "platformName": PLATFORMS[p]["name"], "live": bool(st.get("live"))})
        out.sort(key=lambda x: (not x["live"], x.get("name", "").lower()))
        return out

    def live_count(self) -> int:
        with self._lock:
            return sum(1 for st in self.status.values() if st.get("live"))

    def _recent_videos(self, cfg=None) -> list[dict]:
        cfg = cfg or load_config()
        now = time.time()
        chans = {s["id"]: s for s in cfg["streamers"] if _platform(s) == "youtube"}
        out = []
        with self._lock:
            for cid, videos in self.feeds.items():
                s = chans.get(cid)
                if not s:
                    continue
                since = max(s.get("since", 0), now - 86400 * VIDEO_DAYS)
                for v in videos:
                    if v["published"] >= since and v["id"] not in self._seen and v["id"] not in youtube._upcoming:
                        out.append({**v, "channelName": s.get("name") or v["channelName"], "channelImage": s.get("image", "")})
        out.sort(key=lambda v: -v["published"])
        return out

    def videos(self) -> list[dict]:
        cfg = load_config()
        hide = cfg.get("youtube", {}).get("hide_shorts", False)
        live_ids = {st.get("videoId") for st in self.status.values() if st.get("live")}
        # 지금 라이브 중인 YouTube 방송은 맨 앞에 (라이브 '전체'에서 YouTube 채널 줄을 숨겨도 여기서 보이게)
        out = []
        with self._lock:
            for s in cfg["streamers"]:
                if _platform(s) != "youtube":
                    continue
                st = self.status.get(_key("youtube", s["id"]), {})
                vid = st.get("videoId")
                if st.get("live") and vid:
                    out.append({"id": vid, "title": st.get("title") or "", "published": st.get("since") or time.time(),
                                "views": 0, "viewers": st.get("viewers") or 0, "channel": s["id"],
                                "channelName": s.get("name", ""), "channelImage": s.get("image", ""), "short": False,
                                "live": True, "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"})
        shown = {v["id"] for v in out}
        for v in self._recent_videos(cfg):
            if v["id"] in shown:
                continue
            short = youtube._shorts.get(v["id"], False)
            if hide and short:
                continue
            out.append({**v, "short": short, "live": v["id"] in live_ids,
                        "thumb": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg"})
        return out

    def new_video_count(self) -> int:
        """왼쪽 메뉴의 '새 영상 N' 배지 (라이브 방송은 'N LIVE' 배지에 이미 들어가므로 뺀다)."""
        return sum(1 for v in self.videos() if not v["live"])

    @staticmethod
    def search(platform: str, keyword: str) -> list[dict]:
        fn = SEARCH.get(platform)
        if not fn or not keyword.strip():
            return []
        try:
            return fn(keyword.strip())
        except Exception:
            log.exception("%s 검색 실패", PLATFORMS.get(platform, {}).get("name", platform))
            return []

    def add(self, platform: str, sid: str, name: str, image: str = ""):
        if platform not in PLATFORMS:
            return False
        cfg = load_config()
        if not any(_platform(s) == platform and s["id"] == sid for s in cfg["streamers"]):
            entry = {"platform": platform, "id": sid, "name": name, "notify": True, "image": image}
            if platform == "youtube":
                entry["since"] = time.time() - 86400 * 3    # 추가할 때는 최근 3일 영상까지만 '새 영상'으로
            cfg["streamers"].append(entry)
            save_config(cfg)
        self.refresh_now(platform == "youtube")
        return True

    def remove(self, platform: str, sid: str):
        cfg = load_config()
        cfg["streamers"] = [s for s in cfg["streamers"] if not (_platform(s) == platform and s["id"] == sid)]
        save_config(cfg)
        with self._lock:
            self.status.pop(_key(platform, sid), None)
            if platform == "youtube":
                self.feeds.pop(sid, None)
        return True

    def set_notify(self, platform: str, sid: str, on: bool):
        cfg = load_config()
        for s in cfg["streamers"]:
            if _platform(s) == platform and s["id"] == sid:
                s["notify"] = bool(on)
        save_config(cfg)
        return True

    def watch(self, platform: str, sid: str) -> str:
        with self._lock:
            return watch_url(platform, sid, self.status.get(_key(platform, sid)))

    def mark_seen(self, video_ids: list[str]):
        self._seen.update(video_ids)
        # 오래된 것부터 버리도록 최근 목록 순서를 유지하기는 어려우니, 넘치면 지금 목록에 없는 것부터 버린다
        if len(self._seen) > SEEN_MAX:
            current = {v["id"] for vs in self.feeds.values() for v in vs}
            self._seen = {v for v in self._seen if v in current} | set(video_ids)
        save_state(yt_seen=sorted(self._seen))
        return True
