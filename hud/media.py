"""지금 재생 중인 곡 정보와 조작 (Windows 미디어 제어 = SMTC), PC 전체 음량.

SMTC 는 .NET Framework(pythonnet) 으로 호출한다 (hud/winrt_net.py 참고).
"""
import logging
import threading
import time

from .icons import bytes_to_data_url

log = logging.getLogger("hud")
PLAYING = 4   # GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing


class Media:
    def __init__(self, prefer: str):
        self.prefer = (prefer or "").lower()
        self._mgr = None
        self._types = None
        self._lock = threading.Lock()
        self._thumb_key = None
        self._thumb = ""

    def set_prefer(self, match: str):
        """설정에서 플레이어를 바꿨을 때."""
        self.prefer = (match or "").lower()
        self._thumb_key = None

    def _manager(self):
        from . import winrt_net
        if self._types is None:
            ns = "Windows.Media.Control.GlobalSystemMediaTransportControlsSession"
            self._types = {
                "mgr": winrt_net.winrt_type(ns + "Manager", "Windows.Media.Control"),
                "props": winrt_net.winrt_type(ns + "MediaProperties", "Windows.Media.Control"),
            }
        if self._mgr is None:
            req = self._types["mgr"].GetMethod("RequestAsync").Invoke(None, None)
            self._mgr = winrt_net.wait(req, self._types["mgr"])
        return self._mgr

    def _session(self):
        mgr = self._manager()
        sessions = list(mgr.GetSessions())
        if not sessions:
            return None
        if self.prefer:
            for s in sessions:
                if self.prefer in (s.SourceAppUserModelId or "").lower():
                    return s
        for s in sessions:
            if int(s.GetPlaybackInfo().PlaybackStatus) == PLAYING:
                return s
        return mgr.GetCurrentSession() or sessions[0]

    @staticmethod
    def _position(s):
        tl = s.GetTimelineProperties()
        pos, end = tl.Position.TotalSeconds, tl.EndTime.TotalSeconds
        if int(s.GetPlaybackInfo().PlaybackStatus) == PLAYING:
            from System import DateTimeOffset
            pos += max(0.0, (DateTimeOffset.Now - tl.LastUpdatedTime).TotalSeconds)
        return pos, end

    def info(self):
        from . import winrt_net
        try:
            with self._lock:
                s = self._session()
                if s is None:
                    return {"ok": False}
                props = winrt_net.wait(s.TryGetMediaPropertiesAsync(), self._types["props"])
                playing = int(s.GetPlaybackInfo().PlaybackStatus) == PLAYING
                pos, end = self._position(s)
                title, artist = props.Title or "", props.Artist or ""
                if (title, artist) != self._thumb_key:
                    self._thumb_key, self._thumb = (title, artist), ""
                    if props.Thumbnail is not None:
                        try:
                            self._thumb = bytes_to_data_url(winrt_net.read_stream_ref(props.Thumbnail))
                        except Exception as e:
                            log.debug("앨범 이미지 실패: %s", e)
                app = s.SourceAppUserModelId or ""
                return {
                    "ok": True, "title": title, "artist": artist, "album": props.AlbumTitle or "",
                    "playing": playing, "position": min(pos, end) if end > 0 else pos, "duration": end,
                    "thumb": self._thumb, "isPreferred": bool(self.prefer) and self.prefer in app.lower(),
                }
        except Exception as e:
            log.debug("미디어 정보 실패: %s", e)
            self._mgr = None
            return {"ok": False}

    def control(self, action: str, seconds: float = 10):
        from . import winrt_net
        from System import Boolean
        try:
            with self._lock:
                s = self._session()
                if s is None:
                    return False
                if action == "toggle":
                    op = s.TryTogglePlayPauseAsync()
                elif action == "next":
                    op = s.TrySkipNextAsync()
                elif action == "prev":
                    op = s.TrySkipPreviousAsync()
                elif action in ("forward", "rewind"):
                    pos, _ = self._position(s)
                    target = max(0.0, pos + (seconds if action == "forward" else -seconds))
                    op = s.TryChangePlaybackPositionAsync(int(target * 10_000_000))
                else:
                    return False
                return bool(winrt_net.wait(op, clr_type(Boolean)))
        except Exception:
            log.exception("미디어 조작 실패: %s", action)
            self._mgr = None
            return False


def clr_type(py_type):
    import clr
    return clr.GetClrType(py_type)


# ---------------- PC 전체 음량 (pycaw) ----------------
def _endpoint():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume():
    try:
        ep = _endpoint()
        return {"level": round(ep.GetMasterVolumeLevelScalar() * 100), "muted": bool(ep.GetMute())}
    except Exception as e:
        log.debug("음량 읽기 실패: %s", e)
        return {"level": None, "muted": False}


def set_volume(level: int):
    try:
        ep = _endpoint()
        ep.SetMasterVolumeLevelScalar(max(0, min(100, int(level))) / 100, None)
        if level > 0 and ep.GetMute():
            ep.SetMute(0, None)
        return True
    except Exception:
        log.exception("음량 설정 실패")
        return False


def toggle_mute():
    try:
        ep = _endpoint()
        ep.SetMute(0 if ep.GetMute() else 1, None)
        return True
    except Exception:
        log.exception("음소거 실패")
        return False
