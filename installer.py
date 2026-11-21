"""Desktop HUD 설치 / 제거 (관리자 권한 불필요, 현재 사용자에게만 설치).

배포 폴더 구조:
    DesktopHUD-x.y.z\\
        설치.cmd            ← 더블클릭
        runtime\\           ← 서명된 공식 Python (python.org)
        app\\               ← main.py, installer.py, hud\\, web\\
설치 위치: %LOCALAPPDATA%\\Programs\\DesktopHUD
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

APP_NAME = "Desktop HUD"
APP_ID = "DesktopHUD"
VERSION = "1.2.0"
SRC_ROOT = Path(__file__).resolve().parent.parent           # 배포 폴더 (runtime, app 이 들어 있는 곳)
DEST = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_ID
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
NO_WINDOW, DETACHED = 0x08000000, 0x00000008
MB_OK, MB_YESNO, MB_ICONINFO, MB_ICONQ, MB_ICONERR, IDYES = 0x0, 0x4, 0x40, 0x20, 0x10, 6


def msg(text, flags=MB_OK | MB_ICONINFO):
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)


def special_folder(name):
    import winreg as wr
    with wr.OpenKey(wr.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
        return Path(wr.QueryValueEx(k, name)[0])


def make_shortcut(lnk: Path, target: Path, args: str, workdir: Path, icon: Path, desc: str):
    from comtypes.client import CreateObject
    from comtypes.persist import IPersistFile
    from comtypes.shelllink import IShellLinkW, ShellLink
    link = CreateObject(ShellLink, interface=IShellLinkW)
    link.SetPath(str(target))
    link.SetArguments(args)
    link.SetWorkingDirectory(str(workdir))
    link.SetIconLocation(str(icon), 0)
    link.SetDescription(desc)
    lnk.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(IPersistFile).Save(str(lnk), True)


def shortcut_paths():
    return [special_folder("Desktop") / f"{APP_NAME}.lnk",
            special_folder("Programs") / f"{APP_NAME}.lnk"]


def stop_running(root: Path):
    import psutil
    me = os.getpid()
    for p in psutil.process_iter(["pid", "exe", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            cmd = " ".join(p.info["cmdline"] or [])
            if str(root).lower() in (p.info["exe"] or "").lower() or (str(root).lower() in cmd.lower() and "main.py" in cmd):
                p.kill()
        except Exception:
            pass
    time.sleep(1)


def dir_size_kb(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) // 1024


def install():
    if SRC_ROOT.resolve() == DEST.resolve():
        msg("이미 설치된 위치에서 실행 중이에요.")
        return
    stop_running(DEST)
    for sub in ("runtime", "app"):
        target = DEST / sub
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(SRC_ROOT / sub, target)

    pyw = DEST / "runtime" / "pythonw.exe"
    main = DEST / "app" / "main.py"
    icon = DEST / "app" / "web" / "logo.ico"
    for lnk in shortcut_paths():
        make_shortcut(lnk, pyw, f'"{main}"', DEST / "app", icon, "Desktop HUD 실행")

    # 앱 및 기능(설정 > 앱)에 '제거' 항목 등록
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, val in {
            "DisplayName": APP_NAME, "DisplayVersion": VERSION, "Publisher": APP_NAME,
            "DisplayIcon": str(icon), "InstallLocation": str(DEST),
            "UninstallString": f'"{pyw}" "{DEST / "app" / "installer.py"}" --uninstall',
        }.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, dir_size_kb(DEST))

    # 자동 시작 (설치된 pythonw 로 등록되도록 설치된 쪽 코드를 실행)
    r = subprocess.run([str(DEST / "runtime" / "python.exe"), "-c",
                        "import sys; sys.path.insert(0, r'%s'); from hud import autostart; print(autostart.enable())" % (DEST / "app")],
                       capture_output=True, creationflags=NO_WINDOW)
    auto_ok = b"True" in r.stdout

    subprocess.Popen([str(pyw), str(main)], cwd=str(DEST / "app"), creationflags=DETACHED)
    msg("설치가 끝났어요.\n\n"
        "• 바탕화면과 시작 메뉴에 'Desktop HUD' 바로가기를 만들었어요.\n"
        f"• Windows 시작 시 자동 실행: {'켜짐' if auto_ok else '설정하지 못함 (HUD 설정에서 켤 수 있어요)'}\n"
        "• HUD 오른쪽 위 톱니바퀴 → 설정에서 소리 장치, 투명도 등을 바꿀 수 있어요.\n\n"
        "이 설치 폴더(압축 푼 폴더)는 이제 지워도 돼요.")


def uninstall():
    if msg("Desktop HUD를 제거할까요?", MB_YESNO | MB_ICONQ) != IDYES:
        return
    keep_settings = msg("설정(스트리머 목록, 소리 장치, 바로가기 등)은 남겨 둘까요?\n\n"
                        "'예'를 누르면 나중에 다시 설치했을 때 그대로 쓸 수 있어요.", MB_YESNO | MB_ICONQ) == IDYES
    stop_running(DEST)
    subprocess.run(["schtasks.exe", "/Delete", "/TN", APP_ID, "/F"], capture_output=True, creationflags=NO_WINDOW)
    for lnk in shortcut_paths():
        lnk.unlink(missing_ok=True)
    for key in (UNINSTALL_KEY, rf"Software\Classes\AppUserModelId\{APP_ID}"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
    shutil.rmtree(Path(os.environ["LOCALAPPDATA"]) / APP_ID, ignore_errors=True)   # 캐시/로그
    if not keep_settings:
        shutil.rmtree(Path(os.environ["APPDATA"]) / APP_ID, ignore_errors=True)
    msg("제거했어요.")
    # 지금 실행 중인 파이썬이 설치 폴더 안에 있으므로, 이 프로세스가 끝난 뒤 폴더를 지운다
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{DEST}"',
                     creationflags=NO_WINDOW | DETACHED, cwd=os.environ.get("TEMP", "C:\\"))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        uninstall() if "--uninstall" in sys.argv else install()
    except Exception as e:
        import traceback
        msg(f"문제가 생겼어요:\n{e}\n\n{traceback.format_exc()[-800:]}", MB_OK | MB_ICONERR)
        sys.exit(1)
