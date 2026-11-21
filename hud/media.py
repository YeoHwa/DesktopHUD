"""지금 재생 중인 곡 정보와 조작 (Windows 미디어 제어 = SMTC), PC 전체 음량."""
import asyncio
import datetime as dt
import logging
import threading

from .icons import bytes_to_data_url

log = logging.getLogger("hud")

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
except Exception:  # pragma: no cover
    Manager = None
    log.exception("winrt 미디어 모듈을 불러오지 못했습니다")


class Media:
    def __init__(self, prefer: str):
        self.prefer = prefer.lower()
        self.loop = asyncio.new_event_loop()
        self._mgr = None
        self._thumb_key = None
        self._thumb = ""
        threading.Thread(target=self.loop.run_forever, daemon=True, name="media").start()

    def set_prefer(self, match: str):
        """설정에서 플레이어를 바꿨을 때."""
        self.prefer = (match or "").lower()
        self._thumb_key = None

    def _call(self, coro, timeout=4):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _session(self):
        if Manager is None:
            return None
        if self._mgr is None:
            self._mgr = await Manager.request_async()
        sessions = list(self._mgr.get_sessions())
        if not sessions:
            return None
        preferred = [s for s in sessions if self.prefer and self.prefer in (s.source_app_user_model_id or "").lower()]
        if preferred:
            return preferred[0]
        playing = [s for s in sessions if s.get_playback_info().playback_status == Status.PLAYING]
        return playing[0] if playing else (self._mgr.get_current_session() or sessions[0])

    async def _info(self):
        s = await self._session()
        if s is None:
            return {"ok": False}
        props = await s.try_get_media_properties_async()
        pb = s.get_playback_info()
        tl = s.get_timeline_properties()
        playing = pb.playback_status == Status.PLAYING
        pos = tl.position.total_seconds()
        end = tl.end_time.total_seconds()
        if playing and tl.last_updated_time:
            pos += max(0.0, (dt.datetime.now(dt.timezone.utc) - tl.last_updated_time).total_seconds())
        key = (props.title, props.artist)
        if key != self._thumb_key:
            self._thumb_key, self._thumb = key, ""
            if props.thumbnail:
                try:
                    stream = await props.thumbnail.open_read_async()
                    buf = Buffer(stream.size)
                    await stream.read_async(buf, stream.size, InputStreamOptions.READ_AHEAD)
                    self._thumb = bytes_to_data_url(bytes(buf))
                except Exception as e:
                    log.debug("앨범 이미지 실패: %s", e)
        app = s.source_app_user_model_id or ""
        return {
            "ok": True,
            "title": props.title or "",
            "artist": props.artist or "",
            "album": props.album_title or "",
            "playing": playing,
            "position": min(pos, end) if end else pos,
            "duration": end,
            "thumb": self._thumb,
            "isPreferred": bool(self.prefer) and self.prefer in app.lower(),
        }

    def info(self):
        try:
            return self._call(self._info())
        except Exception as e:
            log.debug("미디어 정보 실패: %s", e)
            self._mgr = None
            return {"ok": False}

    def control(self, action: str, seconds: float = 10):
        async def run():
            s = await self._session()
            if s is None:
                return False
            if action == "toggle":
                return await s.try_toggle_play_pause_async()
            if action == "next":
                return await s.try_skip_next_async()
            if action == "prev":
                return await s.try_skip_previous_async()
            if action in ("forward", "rewind"):
                tl = s.get_timeline_properties()
                cur = tl.position.total_seconds()
                if s.get_playback_info().playback_status == Status.PLAYING and tl.last_updated_time:
                    cur += (dt.datetime.now(dt.timezone.utc) - tl.last_updated_time).total_seconds()
                target = max(0.0, cur + (seconds if action == "forward" else -seconds))
                return await s.try_change_playback_position_async(int(target * 10_000_000))
            return False
        try:
            return bool(self._call(run()))
        except Exception:
            log.exception("미디어 조작 실패: %s", action)
            return False


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
