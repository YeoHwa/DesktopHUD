"""마우스 배터리: Logitech(G HUB) 와 Razer 중 연결된 쪽을 자동으로 고른다."""
import logging

from .config import load_config

log = logging.getLogger("hud")


class MouseBattery:
    def __init__(self):
        provider = load_config().get("mouse", {}).get("provider", "auto")
        self.provider = provider
        self.ghub = self.razer = None
        if provider in ("auto", "ghub"):
            from .ghub import GHubBattery
            self.ghub = GHubBattery()
        if provider in ("auto", "razer"):
            try:
                from .razer import RazerBattery
                self.razer = RazerBattery()
            except Exception:
                log.exception("Razer 배터리 모듈을 시작하지 못했습니다")

    @property
    def state(self) -> dict:
        if self.provider == "off":
            return {"ok": False, "status": "off", "source": ""}
        states = [s.state for s in (self.ghub, self.razer) if s]
        for st in states:
            if st.get("ok"):
                return st
        # 둘 다 배터리가 없으면 가장 '가까운' 상태를 보여 준다 (G HUB 가 켜져 있으면 그쪽 메시지)
        for st in states:
            if st.get("status") == "nodevice" and st.get("source") == "G HUB":
                return st
        return states[0] if states else {"ok": False, "status": "off", "source": ""}

    def app_target(self) -> str:
        """마우스 칸을 눌렀을 때 열 프로그램."""
        cfg = load_config()
        src = self.state.get("source")
        if src == "Razer" and cfg.get("razer_app"):
            return cfg["razer_app"]
        if cfg.get("ghub_exe"):
            return cfg["ghub_exe"]
        return cfg.get("razer_app", "")
