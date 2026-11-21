"""마우스 배터리: Logitech(G HUB → 없으면 수신기에 직접) / Razer 중 연결된 쪽을 자동으로 고른다."""
import logging

from .config import load_config

log = logging.getLogger("hud")
PROVIDERS = ("auto", "ghub", "logitech", "razer", "off")


class MouseBattery:
    def __init__(self):
        provider = load_config().get("mouse", {}).get("provider", "auto")
        self.provider = provider if provider in PROVIDERS else "auto"
        self.ghub = self.logi = self.razer = None
        if self.provider in ("auto", "ghub"):
            from .ghub import GHubBattery
            self.ghub = GHubBattery()
        if self.provider in ("auto", "logitech"):
            self._start("logi", ".logitech", "LogitechBattery")
            if self.logi and self.ghub:
                # G HUB 가 배터리를 주고 있으면 직접 읽기는 쉰다 (같은 수신기에 이중으로 묻지 않도록)
                self.logi.paused = lambda: bool(self.ghub.state.get("ok"))
        if self.provider in ("auto", "razer"):
            self._start("razer", ".razer", "RazerBattery")

    def _start(self, attr, module, cls):
        try:
            import importlib
            mod = importlib.import_module(module, __package__)
            setattr(self, attr, getattr(mod, cls)())
        except Exception:
            log.exception("%s 모듈을 시작하지 못했습니다", cls)

    @property
    def state(self) -> dict:
        if self.provider == "off":
            return {"ok": False, "status": "off", "source": ""}
        sources = [s for s in (self.ghub, self.logi, self.razer) if s]
        for s in sources:
            if s.state.get("ok"):
                return s.state
        if self.ghub and self.ghub.state.get("status") == "nodevice":
            return self.ghub.state          # G HUB 는 켜져 있는데 마우스가 꺼진 경우
        return {"ok": False, "status": "searching", "source": ""}

    def app_target(self) -> str:
        """마우스 칸을 눌렀을 때 열 프로그램."""
        from . import detect
        cfg = load_config()
        src = self.state.get("source")
        if src == "Razer":
            return cfg.get("razer_app") or detect.razer_app()
        if src == "Logitech":   # G HUB 없이 읽는 중 → Logi Options+ 가 있으면 그것
            return detect.find_start_app("Logi Options+", "Logitech Options+", "Logi Options") or cfg.get("ghub_exe", "")
        return cfg.get("ghub_exe") or detect.ghub_exe() or cfg.get("razer_app", "")
