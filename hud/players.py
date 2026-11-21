"""음악 플레이어 선택: HUD 플레이어가 어느 앱의 재생 정보를 우선해서 보여 줄지, 버튼으로 무엇을 열지.

match: Windows 미디어 제어(SMTC)가 알려 주는 앱 ID(AUMID) 에 들어 있는 글자. 비어 있으면 재생 중인 아무 미디어.
"""
import os

from . import detect
from .config import load_config

# id: (표시 이름, 시작 메뉴 앱 이름들, 웹 주소, SMTC 앱 ID 에 들어 있는 글자, 설치형 exe 경로들)
PRESETS = {
    "youtube_music": ("YouTube Music", ("YouTube Music",), "https://music.youtube.com/", "", ()),
    "spotify": ("Spotify", ("Spotify",), "https://open.spotify.com/", "spotify", (r"%APPDATA%\Spotify\Spotify.exe",)),
    "apple_music": ("Apple Music", ("Apple Music",), "https://music.apple.com/", "applemusic", ()),
    "melon": ("멜론", ("멜론", "Melon", "MelOn"), "https://www.melon.com/", "melon", (r"%ProgramFiles(x86)%\Kakao\MelOn\Melon.exe",)),
    "genie": ("지니", ("지니", "genie", "지니뮤직"), "https://www.genie.co.kr/", "genie", ()),
    "any": ("재생 중인 미디어", (), "", "", ()),
}


def _detect(pid):
    name, apps, url, match, exes = PRESETS[pid]
    if pid == "youtube_music":
        target, crx = detect.youtube_music()
        return name, target, crx, target.startswith("shell:")
    app = detect.find_start_app(*apps) if apps else ""
    if app:
        return name, app, match or app.split("\\")[-1].split("!")[0].lower(), True
    for p in exes:
        p = os.path.expandvars(p)
        if os.path.isfile(p):
            return name, p, match, True
    return name, url, match, False


def current() -> dict:
    """{id, name, target, match, installed}"""
    m = load_config().get("media", {})
    pid = m.get("player", "youtube_music")
    if pid == "custom" and m.get("custom", {}).get("target"):
        c = m["custom"]
        return {"id": "custom", "name": c.get("name", "앱"), "target": c["target"], "match": c.get("match", ""), "installed": True}
    if pid not in PRESETS:
        pid = "youtube_music"
    name, target, match, installed = _detect(pid)
    return {"id": pid, "name": name, "target": target, "match": match.lower(), "installed": installed}


def choices() -> list[dict]:
    out = []
    for pid in PRESETS:
        name, target, match, installed = _detect(pid)
        out.append({"id": pid, "name": name, "installed": installed or pid == "any"})
    return out


def start_apps() -> list[dict]:
    """'직접 고르기' 용 시작 메뉴 앱 목록."""
    return sorted(({"name": a["Name"], "target": "shell:AppsFolder\\" + a["AppID"]}
                   for a in detect.start_apps() if a.get("Name") and a.get("AppID")), key=lambda x: x["name"].lower())


def custom_from_app(name: str, target: str) -> dict:
    aumid = target.split("\\", 1)[-1]
    # 웹 앱은 '_crx_<id>', 스토어 앱은 패키지 이름, 일반 앱은 exe 이름으로 재생 세션을 알아본다
    if "_crx_" in aumid:
        match = aumid.split("_crx_")[1].split(".")[0]
    elif "!" in aumid:
        match = aumid.split("!")[0].split("_")[0]
    else:
        match = os.path.splitext(os.path.basename(aumid))[0]
    return {"name": name, "target": target, "match": match.lower()}
