"""설치된 게임 자동 감지 (Windows '앱 제거' 목록 기반) 와 실행."""
import logging
import os
import re
import subprocess
import winreg

from .icons import icon_data_url
from .launch import open_target

log = logging.getLogger("hud")

UNINSTALL_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
]
# 게임이 아닌 런처/도구
EXCLUDE = {"steam", "battle.net", "riot client", "neopleplugin", "anticheatexpert", "넥슨플러그", "nexonplug",
           "wallpaper engine", "steamworks common redistributables", "riot vanguard"}
GAME_DIR = re.compile(r"[\\/](Games|SteamLibrary|Epic Games|Riot Games|Nexon|NCSOFT|Kakao ?Games|Smilegate|"
                      r"Pearl ?Abyss|Netmarble|Krafton|HoYoverse|miHoYo|Ubisoft|EA Games|Electronic Arts)[\\/]", re.I)
EPIC_MANIFESTS = os.path.expandvars(r"%ProgramData%\Epic\EpicGamesLauncher\Data\Manifests")
SHORTCUT_DIRS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
]


def _val(key, name):
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return ""


def _shortcuts():
    found = {}
    for d in SHORTCUT_DIRS:
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".lnk", ".url")):
                    found.setdefault(os.path.splitext(f)[0].lower(), os.path.join(root, f))
    return found


def _entries():
    for hive, path in UNINSTALL_KEYS:
        try:
            base = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(base)[0]):
            try:
                sub = winreg.EnumKey(base, i)
                with winreg.OpenKey(base, sub) as k:
                    yield sub, {n: _val(k, n) for n in ("DisplayName", "DisplayIcon", "InstallLocation", "UninstallString")}
            except OSError:
                continue


def scan(cfg) -> list[dict]:
    hidden = set(cfg["games"].get("hidden", []))
    shortcuts = _shortcuts()
    bnet_exe = ""
    games: dict[str, dict] = {}

    entries = list(_entries())
    for sub, e in entries:
        if e["DisplayName"].strip().lower() == "battle.net":
            bnet_exe = e["DisplayIcon"].split(",")[0].strip('"')

    for sub, e in entries:
        name = e["DisplayName"].strip()
        icon = e["DisplayIcon"].split(",")[0].strip('"')
        un = e["UninstallString"]
        if not name or name.lower() in EXCLUDE:
            continue
        g = None
        if m := re.match(r"Steam App (\d+)$", sub):
            g = {"id": f"steam:{m[1]}", "source": "Steam", "launch": {"target": f"steam://rungameid/{m[1]}"}}
        elif sub.startswith("Riot Game"):
            prod = re.search(r"--uninstall-product=(\S+)", un)
            exe = re.match(r'"([^"]+)"', un)
            if prod and exe and prod[1].lower() != "riot_client":
                g = {"id": f"riot:{prod[1]}", "source": "Riot",
                     "launch": {"target": exe[1], "args": [f"--launch-product={prod[1]}", "--launch-patchline=live"]}}
        elif "NGM64.exe" in un and (gid := re.search(r"-game:(\d+)", un)):
            sc = shortcuts.get(name.lower())
            g = {"id": f"nexon:{gid[1]}", "source": "Nexon",
                 "launch": {"target": sc or f"http://game.nexon.com/{gid[1]}"}}
        elif "NeopleLauncher" in un:
            g = {"id": f"neople:{sub}", "source": "Nexon", "launch": {"target": "https://df.nexon.com/"}}
        elif "Blizzard Uninstaller" in un and (uid := re.search(r"--uid=(\S+)", un)):
            sc = shortcuts.get(name.lower())
            launch = {"target": sc} if sc else {"target": bnet_exe, "args": [f"--exec=launch {uid[1].upper()}"]}
            g = {"id": f"bnet:{uid[1]}", "source": "Battle.net", "launch": launch}
        elif GAME_DIR.search(icon or e["InstallLocation"] or "") and icon.lower().endswith(".exe") \
                and not re.search(r"unins|setup|uninst", icon, re.I):
            g = {"id": f"app:{sub}", "source": "기타", "launch": {"target": icon}}
        if not g or g["id"] in hidden:
            continue
        g["name"] = cfg["games"].get("rename", {}).get(g["id"]) or name.replace("®", "").replace("™", "").strip()
        g["iconPath"] = icon
        games[g["id"]] = g

    # Epic Games 런처로 설치한 게임
    if os.path.isdir(EPIC_MANIFESTS):
        import json
        for f in os.listdir(EPIC_MANIFESTS):
            if not f.endswith(".item"):
                continue
            try:
                m = json.load(open(os.path.join(EPIC_MANIFESTS, f), encoding="utf-8"))
            except Exception:
                continue
            if "games" not in [c.lower() for c in m.get("AppCategories", ["games"])]:
                continue
            gid = f"epic:{m.get('AppName')}"
            if gid in hidden:
                continue
            exe = os.path.join(m.get("InstallLocation", ""), m.get("LaunchExecutable", ""))
            games[gid] = {"id": gid, "source": "Epic", "name": m.get("DisplayName", m.get("AppName")),
                          "launch": {"target": f"com.epicgames.launcher://apps/{m.get('AppName')}?action=launch&silent=true"},
                          "iconPath": exe}

    for extra in cfg["games"].get("extra", []):
        gid = f"extra:{extra['name']}"
        if gid in hidden:
            continue
        games[gid] = {"id": gid, "name": extra["name"], "source": extra.get("source", "기타"),
                      "launch": {"target": extra["target"], "args": extra.get("args")},
                      "iconPath": extra.get("icon", extra["target"])}

    order = {"Nexon": 0, "Riot": 1, "Steam": 2, "Battle.net": 3, "Epic": 4, "기타": 5}
    result = sorted(games.values(), key=lambda g: (order.get(g["source"], 9), g["name"]))
    for g in result:
        g["icon"] = icon_data_url(g["iconPath"])
    log.info("게임 %d개 감지", len(result))
    return result


def launch(game: dict) -> bool:
    l = game["launch"]
    return open_target(l["target"], l.get("args"))
