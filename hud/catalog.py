"""설치된 프로그램 자동 감지용 목록: 메신저, 그리고 분야별(개발·음악·영상·디자인 …) 작업 프로그램.

각 항목: (id, 표시 이름, 시작 메뉴 이름 정규식, 설치 경로 후보들, 프로세스 이름)
- 시작 메뉴(Get-StartApps)에서 이름이 맞는 앱을 먼저 찾고, 없으면 설치 경로 후보를 본다.
- 프로세스 이름은 '집중 모드'(메신저 끄기)에 쓴다.
"""
import os
import re

from . import detect

SKIP = re.compile(r"uninstall|제거|readme|manual|documentation|help|도움말|release notes|website|support|faq", re.I)

MESSENGERS = [
    ("discord", "Discord", r"^Discord$", [r"%LOCALAPPDATA%\Discord\Update.exe"], "discord.exe"),
    ("kakaotalk", "카카오톡", r"^(카카오톡|KakaoTalk)$", [r"%ProgramFiles(x86)%\Kakao\KakaoTalk\KakaoTalk.exe",
                                                       r"%ProgramFiles%\Kakao\KakaoTalk\KakaoTalk.exe"], "kakaotalk.exe"),
    ("telegram", "Telegram", r"^(Telegram|Telegram Desktop|텔레그램)$", [r"%APPDATA%\Telegram Desktop\Telegram.exe"], "telegram.exe"),
    ("line", "LINE", r"^LINE$", [r"%LOCALAPPDATA%\LINE\bin\LineLauncher.exe"], "line.exe"),
    ("slack", "Slack", r"^Slack$", [r"%LOCALAPPDATA%\slack\slack.exe"], "slack.exe"),
    ("teams", "Microsoft Teams", r"^(Microsoft Teams|Teams)( \(.*\))?$", [], "ms-teams.exe"),
    ("whatsapp", "WhatsApp", r"^WhatsApp$", [], "whatsapp.exe"),
    ("signal", "Signal", r"^Signal$", [r"%LOCALAPPDATA%\Programs\signal-desktop\Signal.exe"], "signal.exe"),
    ("messenger", "Messenger", r"^Messenger$", [], "messenger.exe"),
    ("zoom", "Zoom", r"^(Zoom|Zoom Workplace)$", [r"%APPDATA%\Zoom\bin\Zoom.exe"], "zoom.exe"),
    ("skype", "Skype", r"^Skype$", [], "skype.exe"),
    ("naverworks", "NAVER WORKS", r"^(NAVER WORKS|네이버 웍스|LINE WORKS)$", [], "naverworks.exe"),
    ("jandi", "JANDI", r"^(JANDI|잔디)$", [], "jandi.exe"),
    ("webex", "Webex", r"^Webex$", [], "webex.exe"),
    ("element", "Element", r"^Element$", [], "element.exe"),
]

# 분야: (id, 이름, 아이콘 글리프, [(id, 이름, 정규식, 경로들, 프로세스)])
FIELDS = [
    ("dev", "개발", "E943", [
        ("vscode", "VS Code", r"^Visual Studio Code$", [r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                                                         r"%ProgramFiles%\Microsoft VS Code\Code.exe"], ""),
        ("cursor", "Cursor", r"^Cursor$", [r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe"], ""),
        ("terminal", "터미널", r"^(터미널|Terminal|Windows Terminal)$", [], ""),
        ("vs", "Visual Studio", r"^Visual Studio 20\d\d", [], ""),
        ("jetbrains", "JetBrains", r"^(IntelliJ IDEA|PyCharm|WebStorm|Rider|CLion|GoLand|DataGrip|Android Studio)", [], ""),
        ("github", "GitHub Desktop", r"^GitHub Desktop$", [], ""),
        ("gitbash", "Git Bash", r"^Git Bash$", [], ""),
        ("docker", "Docker", r"^Docker Desktop$", [], ""),
        ("postman", "Postman", r"^Postman$", [], ""),
        ("claude", "Claude", r"^Claude$", [], ""),
        ("chatgpt", "ChatGPT", r"^ChatGPT$", [], ""),
        ("codex", "Codex", r"^Codex$", [], ""),
    ]),
    ("music", "음악 작업", "E8D6", [
        ("cubase", "Cubase", r"^Cubase", [], ""),
        ("flstudio", "FL Studio", r"^FL Studio", [], ""),
        ("ableton", "Ableton Live", r"^Ableton Live", [], ""),
        ("studioone", "Studio One", r"^(PreSonus )?Studio One", [], ""),
        ("reaper", "REAPER", r"^REAPER", [], ""),
        ("protools", "Pro Tools", r"^Pro Tools", [], ""),
        ("bitwig", "Bitwig Studio", r"^Bitwig Studio", [], ""),
        ("logic", "Logic", r"^Logic Pro", [], ""),
        ("audition", "Audition", r"^Adobe Audition", [], ""),
        ("audacity", "Audacity", r"^Audacity$", [], ""),
        ("melodyne", "Melodyne", r"^Melodyne", [], ""),
        ("izotope", "iZotope RX", r"^(iZotope )?RX \d", [], ""),
        ("musescore", "MuseScore", r"^MuseScore", [], ""),
        ("sibelius", "Sibelius", r"^Sibelius", [], ""),
        ("nativeaccess", "Native Access", r"^Native Access", [], ""),
        ("waves", "Waves Central", r"^Waves Central$", [], ""),
        ("splice", "Splice", r"^Splice$", [], ""),
        ("arturia", "Arturia", r"^Arturia Software Center$", [], ""),
    ]),
    ("video", "영상 편집", "E714", [
        ("premiere", "Premiere Pro", r"^Adobe Premiere Pro", [], ""),
        ("aftereffects", "After Effects", r"^Adobe After Effects", [], ""),
        ("resolve", "DaVinci Resolve", r"^DaVinci Resolve$", [], ""),
        ("vegas", "VEGAS Pro", r"^VEGAS Pro", [], ""),
        ("capcut", "CapCut", r"^CapCut$", [], ""),
        ("vrew", "Vrew", r"^Vrew$", [], ""),
        ("filmora", "Filmora", r"^(Wondershare )?Filmora", [], ""),
        ("powerdirector", "PowerDirector", r"^PowerDirector", [], ""),
        ("mediaencoder", "Media Encoder", r"^Adobe Media Encoder", [], ""),
        ("handbrake", "HandBrake", r"^HandBrake$", [], ""),
        ("clipchamp", "Clipchamp", r"^(Microsoft )?Clipchamp$", [], ""),
    ]),
    ("design", "디자인", "E790", [
        ("photoshop", "Photoshop", r"^Adobe Photoshop", [], ""),
        ("illustrator", "Illustrator", r"^Adobe Illustrator", [], ""),
        ("indesign", "InDesign", r"^Adobe InDesign", [], ""),
        ("lightroom", "Lightroom", r"^Adobe Lightroom", [], ""),
        ("figma", "Figma", r"^Figma$", [], ""),
        ("clipstudio", "CLIP STUDIO PAINT", r"^CLIP STUDIO PAINT", [], ""),
        ("krita", "Krita", r"^Krita", [], ""),
        ("gimp", "GIMP", r"^GIMP", [], ""),
        ("inkscape", "Inkscape", r"^Inkscape", [], ""),
        ("affinity", "Affinity", r"^Affinity (Photo|Designer|Publisher)", [], ""),
        ("canva", "Canva", r"^Canva$", [], ""),
        ("pureref", "PureRef", r"^PureRef$", [], ""),
    ]),
    ("3d", "3D · 게임 제작", "F158", [
        ("blender", "Blender", r"^Blender", [], ""),
        ("maya", "Maya", r"^Maya 20\d\d", [], ""),
        ("3dsmax", "3ds Max", r"^3ds Max", [], ""),
        ("c4d", "Cinema 4D", r"^(Maxon )?Cinema 4D", [], ""),
        ("zbrush", "ZBrush", r"^(Maxon )?ZBrush", [], ""),
        ("substance", "Substance Painter", r"^Adobe Substance 3D Painter", [], ""),
        ("houdini", "Houdini", r"^Houdini", [], ""),
        ("unity", "Unity Hub", r"^Unity Hub$", [], ""),
        ("unreal", "Unreal Engine", r"^Unreal Engine", [], ""),
        ("sketchup", "SketchUp", r"^SketchUp", [], ""),
        ("rhino", "Rhino", r"^Rhino \d", [], ""),
    ]),
    ("office", "문서 · 사무", "E8A5", [
        ("word", "Word", r"^Word$", [], ""),
        ("excel", "Excel", r"^Excel$", [], ""),
        ("powerpoint", "PowerPoint", r"^PowerPoint$", [], ""),
        ("outlook", "Outlook", r"^Outlook", [], ""),
        ("onenote", "OneNote", r"^OneNote", [], ""),
        ("hwp", "한글", r"^한글( 20\d\d)?$", [], ""),
        ("hcell", "한셀", r"^한셀", [], ""),
        ("hshow", "한쇼", r"^한쇼", [], ""),
        ("notion", "Notion", r"^Notion$", [], ""),
        ("obsidian", "Obsidian", r"^Obsidian$", [], ""),
        ("acrobat", "Acrobat", r"^Adobe Acrobat", [], ""),
        ("notepad", "메모장", r"^(메모장|Notepad)$", [], ""),
    ]),
    ("stream", "방송", "E93E", [
        ("obs", "OBS Studio", r"^OBS Studio", [], ""),
        ("prism", "PRISM Live Studio", r"^PRISM Live Studio", [], ""),
        ("streamlabs", "Streamlabs", r"^Streamlabs", [], ""),
        ("xsplit", "XSplit", r"^XSplit", [], ""),
        ("vtube", "VTube Studio", r"^VTube Studio$", [], ""),
        ("voicemeeter", "Voicemeeter", r"^Voicemeeter", [], ""),
        ("nvbroadcast", "NVIDIA Broadcast", r"^NVIDIA Broadcast$", [], ""),
        ("soopstudio", "SOOP Studio", r"^(SOOP|아프리카TV) ?(Studio|스튜디오)", [], ""),
    ]),
]
FIELD_BY_ID = {f[0]: f for f in FIELDS}
# Windows 에 기본으로 들어 있거나 흔한 프로그램: 처음 실행 때 이것만 있으면 그 분야 묶음을 만들지 않는다
COMMON = {"terminal", "clipchamp", "outlook", "notepad", "gitbash"}


def _target_of(app_id: str) -> str:
    """시작 메뉴 앱 ID → 실행할 대상. 실제 exe 경로면 그대로(집중 모드에서 프로세스를 알 수 있게), 아니면 shell:AppsFolder."""
    if re.match(r"^[a-zA-Z]:\\.+\.exe$", app_id) and os.path.isfile(app_id):
        return app_id
    return "shell:AppsFolder\\" + app_id


def find(entry, apps=None) -> dict | None:
    """카탈로그 항목 하나를 이 PC 에서 찾는다 → 바로가기 항목 {name, target, auto, proc} 또는 None."""
    eid, name, pattern, paths, proc = entry
    rx = re.compile(pattern, re.I)
    apps = detect.start_apps() if apps is None else apps
    hits = sorted((a for a in apps if a.get("Name") and a.get("AppID") and rx.search(a["Name"]) and not SKIP.search(a["Name"])),
                  key=lambda a: a["Name"], reverse=True)   # 여러 버전이 있으면 이름순으로 가장 뒤(대개 최신)
    item = None
    if eid == "discord":     # Discord 는 Update.exe 로 실행해야 업데이트 후에도 경로가 안 바뀐다
        p = os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")
        if os.path.isfile(p):
            item = {"name": name, "target": r"%LOCALAPPDATA%\Discord\Update.exe", "args": ["--processStart", "Discord.exe"],
                    "icon": r"%LOCALAPPDATA%\Discord\app.ico"}
    if item is None and eid == "kakaotalk":
        exe = detect.kakaotalk_exe()
        if exe:
            item = {"name": name, "target": exe}
    if item is None and hits:
        item = {"name": hits[0]["Name"] if eid in ("vs", "jetbrains") else name, "target": _target_of(hits[0]["AppID"])}
    if item is None:
        for p in paths:
            if os.path.isfile(os.path.expandvars(p)):
                item = {"name": name, "target": p}
                break
    if item is None and eid == "vscode":
        exe = detect.vscode_exe()
        if exe:
            item = {"name": name, "target": exe}
    if item is None and eid == "terminal":
        item = {"name": name, "target": detect.terminal_cmd(), "glyph": "E756"}
    if item is None:
        return None
    if eid == "docker":
        item = {"name": "Docker", "action": "docker", "glyph": "E7B8"}
    item["auto"] = eid
    if proc:
        item["proc"] = proc
    return item


def detect_messengers(fresh: bool = False) -> list[dict]:
    if fresh:
        detect.start_apps.cache_clear()
    apps = detect.start_apps()
    return [it for it in (find(e, apps) for e in MESSENGERS) if it]


def detect_field(field_id: str, fresh: bool = False) -> list[dict]:
    f = FIELD_BY_ID.get(field_id)
    if not f:
        return []
    if fresh:
        detect.start_apps.cache_clear()
    apps = detect.start_apps()
    return [it for it in (find(e, apps) for e in f[3]) if it]


def fields() -> list[dict]:
    return [{"id": f[0], "name": f[1], "glyph": f[2]} for f in FIELDS]
