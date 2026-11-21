"""Logitech G HUB 로컬 연결(ws://127.0.0.1:9010)로 마우스 배터리를 실시간으로 받는다.

주의: G HUB 가 막 켜진 직후에는 장치 목록이 비어 있을 수 있다.
      그래서 마우스를 찾을 때까지 10초마다 장치 목록을 다시 요청한다.
"""
import json
import logging
import threading
import time

import websocket

log = logging.getLogger("hud")
URL = "ws://127.0.0.1:9010"


class GHubBattery:
    source = "G HUB"

    def __init__(self):
        # status: noapp(G HUB 안 켜짐) / nodevice(무선 마우스 없음) / ok
        self.state = {"ok": False, "status": "noapp", "source": self.source}
        self._devices: dict[str, str] = {}
        self._ws = None
        threading.Thread(target=self._run, daemon=True, name="ghub").start()

    def _send(self, verb, path, msg_id=""):
        self._ws.send(json.dumps({"msgId": msg_id, "verb": verb, "path": path}))

    def _apply_battery(self, p):
        name = self._devices.get(p.get("deviceId"))
        if name is None:
            self._send("GET", "/devices/list", "devices")   # 모르는 장치 → 목록부터 다시
            return
        self.state = {
            "ok": True, "status": "ok", "source": self.source, "name": name,
            "percent": p.get("percentage"), "charging": bool(p.get("charging")),
            "hours": round(p["mileage"]) if p.get("mileage") else None, "updated": time.time(),
        }

    def _refresh(self):
        for dev_id in list(self._devices):
            self._send("GET", f"/battery/{dev_id}/state")

    def _run(self):
        while True:
            try:
                self._ws = websocket.create_connection(URL, subprotocols=["json"], origin="file://", timeout=5)
                log.info("G HUB 연결됨")
                self._devices = {}
                self.state = {"ok": False, "status": "nodevice", "source": self.source}
                self._send("SUBSCRIBE", "/battery/state/changed")
                self._send("SUBSCRIBE", "/devices/state/changed")
                last_list = last_poll = 0.0
                while True:
                    now = time.time()
                    if not self._devices and now - last_list > 10:     # 마우스를 찾을 때까지 10초마다
                        last_list = now
                        self._send("GET", "/devices/list", "devices")
                    if self._devices and now - last_poll > 60:          # 구독이 끊겨도 1분마다 확인
                        last_poll = now
                        self._refresh()
                    try:
                        msg = json.loads(self._ws.recv())
                    except websocket.WebSocketTimeoutException:
                        continue
                    path, payload = msg.get("path", ""), msg.get("payload") or {}
                    if path == "/devices/list":
                        found = {d["id"]: d.get("displayName", "") for d in payload.get("deviceInfos", [])
                                 if d.get("deviceType") == "MOUSE" and d.get("state") == "ACTIVE"
                                 and d.get("hasWirelessInterface", True)}
                        if found != self._devices:
                            log.info("G HUB 마우스: %s", list(found.values()) or "없음")
                        self._devices = found
                        if not found:
                            self.state = {"ok": False, "status": "nodevice", "source": self.source}
                        self._refresh()
                    elif path.startswith("/battery") and "percentage" in payload:
                        self._apply_battery(payload)
                    elif path.startswith("/devices/state"):
                        last_list = 0.0
                        self._devices = {}
            except Exception as e:
                if self.state.get("status") != "noapp":
                    log.info("G HUB 연결 끊김/대기: %s", e)
                self.state = {"ok": False, "status": "noapp", "source": self.source}
                time.sleep(10)
