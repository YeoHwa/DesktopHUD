"""사용자가 고칠 수 있는 바로가기 목록: 메신저·커뮤니티, 웹 바로가기, 작업 도구(분야별 프로그램 묶음).

목록 이름(kind):
    "msg"        → config["messengers"]
    "web"        → config["web"]
    "ws:<묶음 id>" → config["workspace"]["groups"][…]["items"]
자동 감지로 들어온 항목에는 "auto": 카탈로그 id 가 붙고, 사용자가 지우면 hidden 목록에 남겨 다시 넣지 않는다.
"""
import logging
import os
import time
import uuid

from . import catalog
from .config import load_config, save_config

log = logging.getLogger("hud")
DEFAULT_TITLE = "작업 도구"


# ---------------- 작업 도구 설정 만들기 / 옮기기 ----------------
def new_group(name: str, field: str = "", items: list | None = None) -> dict:
    return {"id": uuid.uuid4().hex[:8], "name": name, "field": field, "items": items or [], "hidden": []}


def default_workspace(projects_dir: str = "") -> dict:
    """처음 실행: 이 PC 에 설치된 프로그램을 분야별로 찾아, 하나라도 있는 분야만 묶음으로 만든다."""
    groups = []
    for f in catalog.fields():
        items = catalog.detect_field(f["id"])
        real = [it for it in items if it.get("auto") not in catalog.COMMON]
        if real:
            groups.append(new_group(f["name"], f["id"], items))
    if not groups:
        groups.append(new_group("내 프로그램"))
    return {"title": DEFAULT_TITLE, "folder": projects_dir, "groups": groups}


def ensure_workspace(cfg: dict) -> bool:
    """이전 버전(개발 유틸리티: dev.tools / dev.projects_dir) 설정을 작업 도구로 옮긴다. 바뀌었으면 True."""
    ws = cfg.get("workspace")
    if isinstance(ws, dict) and isinstance(ws.get("groups"), list):
        return False
    dev = cfg.get("dev") or {}
    if dev.get("tools"):
        cfg["workspace"] = {"title": DEFAULT_TITLE, "folder": dev.get("projects_dir", ""),
                            "groups": [new_group("개발", "dev", dev["tools"])]}
    else:
        cfg["workspace"] = default_workspace(dev.get("projects_dir", ""))
    return True


# ---------------- 목록 찾기 ----------------
def _group(cfg, gid):
    return next((g for g in cfg["workspace"]["groups"] if g["id"] == gid), None)


def _items(cfg, kind: str) -> list:
    if kind == "msg":
        return cfg.setdefault("messengers", [])
    if kind == "web":
        return cfg.setdefault("web", [])
    if kind.startswith("ws:"):
        g = _group(cfg, kind[3:])
        if g is not None:
            return g.setdefault("items", [])
    raise KeyError(kind)


def _hidden(cfg, kind: str) -> list:
    if kind == "msg":
        return cfg.setdefault("messengers_hidden", [])
    if kind.startswith("ws:"):
        g = _group(cfg, kind[3:])
        if g is not None:
            return g.setdefault("hidden", [])
    return []


def _norm_url(url: str) -> str:
    url = url.strip()
    return url if url.startswith(("http://", "https://")) else "https://" + url


# ---------------- 고치기 ----------------
def add(kind: str, item: dict) -> bool:
    """item: {name, target, args?, type: "web" | "app"}"""
    target = (item.get("target") or "").strip()
    if not target:
        return False
    name = (item.get("name") or "").strip()
    if kind == "web" or item.get("type") == "web":
        target = _norm_url(target)
        new = {"name": name or target.split("//", 1)[-1].split("/")[0].removeprefix("www."), "target": target, "glyph": "E909"}
        if kind != "web":
            new["sub"] = "웹"
    else:
        new = {"name": name or os.path.splitext(os.path.basename(target))[0], "target": target}
        if item.get("args"):
            new["args"] = item["args"]
    cfg = load_config()
    _items(cfg, kind).append(new)
    save_config(cfg)
    return True


def remove(kind: str, index: int) -> bool:
    cfg = load_config()
    items = _items(cfg, kind)
    if not 0 <= index < len(items):
        return False
    it = items.pop(index)
    if it.get("auto"):
        hidden = _hidden(cfg, kind)
        if it["auto"] not in hidden:
            hidden.append(it["auto"])
    save_config(cfg)
    return True


def move(kind: str, index: int, delta: int) -> bool:
    cfg = load_config()
    items = _items(cfg, kind)
    j = index + delta
    if not (0 <= index < len(items) and 0 <= j < len(items)):
        return False
    items[index], items[j] = items[j], items[index]
    save_config(cfg)
    return True


def rename(kind: str, index: int, name: str) -> bool:
    name = (name or "").strip()
    cfg = load_config()
    items = _items(cfg, kind)
    if not name or not 0 <= index < len(items):
        return False
    items[index]["name"] = name
    save_config(cfg)
    return True


def _same(a: dict, b: dict) -> bool:
    if a.get("auto") and a.get("auto") == b.get("auto"):
        return True
    if a.get("action") and a.get("action") == b.get("action"):
        return True
    ta, tb = os.path.expandvars(a.get("target", "")).lower(), os.path.expandvars(b.get("target", "")).lower()
    return bool(ta) and ta == tb or (a.get("name", "").lower() == b.get("name", "").lower() and bool(a.get("name")))


def detect_new(kind: str, fresh: bool = True) -> list[str]:
    """자동 감지로 새로 찾은 프로그램을 목록 끝에 더한다 (사용자가 지운 것은 빼고). 더한 이름 목록을 돌려준다."""
    cfg = load_config()
    if kind == "msg":
        found = catalog.detect_messengers(fresh)
    elif kind.startswith("ws:"):
        g = _group(cfg, kind[3:])
        if not g or not g.get("field"):
            return []
        found = catalog.detect_field(g["field"], fresh)
    else:
        return []
    items, hidden = _items(cfg, kind), _hidden(cfg, kind)
    added = []
    for it in found:
        if it["auto"] in hidden or any(_same(it, x) for x in items):
            # 예전 버전에서 손으로 넣은 같은 프로그램이면 자동 감지 표시만 붙여 둔다 (지우면 다시 안 들어오게)
            for x in items:
                if not x.get("auto") and _same(it, x):
                    x["auto"] = it["auto"]
                    x.setdefault("proc", it.get("proc", ""))
            continue
        items.append(it)
        added.append(it["name"])
    save_config(cfg)
    if added:
        log.info("자동 감지로 추가 (%s): %s", kind, ", ".join(added))
    return added


# ---------------- 작업 도구 묶음 ----------------
def ws_add_group(field: str, name: str = "") -> str:
    cfg = load_config()
    ensure_workspace(cfg)
    f = next((x for x in catalog.fields() if x["id"] == field), None)
    g = new_group(name.strip() or (f["name"] if f else "새 묶음"), f["id"] if f else "",
                  catalog.detect_field(f["id"], fresh=True) if f else [])
    cfg["workspace"]["groups"].append(g)
    save_config(cfg)
    return g["id"]


def ws_remove_group(gid: str) -> bool:
    cfg = load_config()
    cfg["workspace"]["groups"] = [g for g in cfg["workspace"]["groups"] if g["id"] != gid]
    save_config(cfg)
    return True


def ws_rename_group(gid: str, name: str) -> bool:
    cfg = load_config()
    g = _group(cfg, gid)
    if not g or not name.strip():
        return False
    g["name"] = name.strip()
    save_config(cfg)
    return True


def ws_move_group(gid: str, delta: int) -> bool:
    cfg = load_config()
    gs = cfg["workspace"]["groups"]
    i = next((k for k, g in enumerate(gs) if g["id"] == gid), -1)
    j = i + delta
    if i < 0 or not 0 <= j < len(gs):
        return False
    gs[i], gs[j] = gs[j], gs[i]
    save_config(cfg)
    return True


def ws_set(title: str | None = None, folder: str | None = None) -> bool:
    cfg = load_config()
    if title is not None and title.strip():
        cfg["workspace"]["title"] = title.strip()[:20]
    if folder is not None:
        cfg["workspace"]["folder"] = folder.strip()
    save_config(cfg)
    return True


class AutoDetect:
    """메신저 자동 감지를 너무 자주 하지 않도록 (시작 메뉴 목록을 다시 읽는 데 1~2초)."""

    def __init__(self, every: float = 300):
        self.every = every
        self.last = 0.0

    def due(self) -> bool:
        if time.time() - self.last >= self.every:
            self.last = time.time()
            return True
        return False
