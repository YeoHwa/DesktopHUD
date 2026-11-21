"""소리 출력 장치: 목록, 현재 기본 장치, 기본 장치 바꾸기 (꺼져 있는 장치는 켜고 바꿈)."""
import logging
import re
from ctypes import HRESULT, c_int, c_void_p, c_wchar_p

import comtypes
from comtypes import GUID, IUnknown, STDMETHOD

from .config import load_config, save_config

log = logging.getLogger("hud")


class IPolicyConfig(IUnknown):
    # Windows 7 이후 공통으로 쓰이는 비공개 인터페이스 (소리 설정 앱이 쓰는 것과 같음)
    _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
    _methods_ = [
        STDMETHOD(HRESULT, "GetMixFormat", [c_wchar_p, c_void_p]),
        STDMETHOD(HRESULT, "GetDeviceFormat", [c_wchar_p, c_int, c_void_p]),
        STDMETHOD(HRESULT, "ResetDeviceFormat", [c_wchar_p]),
        STDMETHOD(HRESULT, "SetDeviceFormat", [c_wchar_p, c_void_p, c_void_p]),
        STDMETHOD(HRESULT, "GetProcessingPeriod", [c_wchar_p, c_int, c_void_p, c_void_p]),
        STDMETHOD(HRESULT, "SetProcessingPeriod", [c_wchar_p, c_void_p]),
        STDMETHOD(HRESULT, "GetShareMode", [c_wchar_p, c_void_p]),
        STDMETHOD(HRESULT, "SetShareMode", [c_wchar_p, c_void_p]),
        STDMETHOD(HRESULT, "GetPropertyValue", [c_wchar_p, c_void_p, c_void_p]),
        STDMETHOD(HRESULT, "SetPropertyValue", [c_wchar_p, c_void_p, c_void_p]),
        STDMETHOD(HRESULT, "SetDefaultEndpoint", [c_wchar_p, c_int]),
        STDMETHOD(HRESULT, "SetEndpointVisibility", [c_wchar_p, c_int]),
    ]


CLSID_PolicyConfigClient = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")
HEADSET_RX = re.compile(r"헤드|head|이어|ear|buds|airpods|hyperx|arctis|minifuse", re.I)


def _policy():
    comtypes.CoInitialize()
    return comtypes.CoCreateInstance(CLSID_PolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL)


def list_outputs() -> list[dict]:
    """사용 중(1) + 사용 안 함(2) 상태의 출력 장치."""
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    out = []
    for d in AudioUtilities.GetAllDevices():
        did = d.id or ""
        state = int(getattr(d.state, "value", d.state) or 0)
        if not did.startswith("{0.0.0.") or state not in (1, 2):
            continue
        out.append({"id": did, "name": d.FriendlyName or did, "enabled": state == 1})
    out.sort(key=lambda x: (not x["enabled"], x["name"]))
    return out


def default_id() -> str:
    try:
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        return AudioUtilities.GetSpeakers().id or ""
    except Exception as e:
        log.debug("기본 출력 장치 확인 실패: %s", e)
        return ""


def set_default(device_id: str) -> bool:
    try:
        p = _policy()
        p.SetEndpointVisibility(device_id, 1)  # 꺼져 있으면 켬
        for role in (0, 1, 2):                   # 콘솔 / 멀티미디어 / 통신
            p.SetDefaultEndpoint(device_id, role)
        return default_id() == device_id
    except Exception:
        log.exception("출력 장치 변경 실패")
        return False


def short_label(name: str) -> str:
    """'스피커 (Realtek(R) Audio)' → '스피커'"""
    base = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
    return (base or name)[:12]


def favorites() -> list[dict]:
    """HUD 의 두 버튼에 걸린 장치. 비어 있으면 처음 두 장치로 채운다."""
    cfg = load_config()
    favs = cfg["audio"].get("favorites") or []
    if len(favs) < 2:
        try:
            devs = [d for d in list_outputs() if d["enabled"]] or list_outputs()
        except Exception:
            devs = []
        for d in devs:
            if len(favs) >= 2:
                break
            if any(f["id"] == d["id"] for f in favs):
                continue
            favs.append({"id": d["id"], "label": short_label(d["name"]),
                         "icon": "headset" if HEADSET_RX.search(d["name"]) else "speaker"})
        if favs:
            cfg["audio"]["favorites"] = favs
            save_config(cfg)
    return favs
