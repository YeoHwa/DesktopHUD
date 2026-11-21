"""Desktop HUD 설치 / 제거 (관리자 권한 불필요, 현재 사용자에게만 설치).

배포 폴더 구조:
    DesktopHUD-x.y.z\\
        설치.cmd            ← 더블클릭 → 로고가 들어간 설치 창이 열림
        runtime\\           ← 서명된 공식 Python (python.org)
        app\\               ← main.py, installer.py, hud\\, web\\
설치 위치: %LOCALAPPDATA%\\Programs\\DesktopHUD

설치 창은 .NET WinForms(pythonnet) 로 그린다. 창을 띄울 수 없으면 기본 메시지 상자로 진행한다.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import winreg
from pathlib import Path

APP_NAME = "Desktop HUD"
APP_ID = "DesktopHUD"
VERSION = "1.3.0"
HERE = Path(__file__).resolve().parent                       # app 폴더
SRC_ROOT = HERE.parent                                       # 배포 폴더 (runtime, app 이 들어 있는 곳)
DEST = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_ID
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
NO_WINDOW, DETACHED = 0x08000000, 0x00000008
MB_OK, MB_YESNO, MB_ICONINFO, MB_ICONQ, MB_ICONERR, IDYES = 0x0, 0x4, 0x40, 0x20, 0x10, 6


def msg(text, flags=MB_OK | MB_ICONINFO):
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)


# ---------------------------------------------------------------- 설치/제거 작업
def special_folder(name):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
        return Path(winreg.QueryValueEx(k, name)[0])


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


def desktop_link():
    return special_folder("Desktop") / f"{APP_NAME}.lnk"


def start_menu_link():
    return special_folder("Programs") / f"{APP_NAME}.lnk"


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


def refresh_icons():
    """바로가기 아이콘 캐시 새로고침 (새 로고가 바로 보이도록)."""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def do_install(autostart=True, desktop_shortcut=True, run_after=True, report=lambda s: None) -> dict:
    report("실행 중인 HUD 를 닫는 중…")
    stop_running(DEST)
    for sub in ("runtime", "app"):
        report(f"파일 복사 중… ({sub})")
        target = DEST / sub
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(SRC_ROOT / sub, target)

    report("바로가기 만드는 중…")
    pyw = DEST / "runtime" / "pythonw.exe"
    main = DEST / "app" / "main.py"
    icon = DEST / "app" / "web" / "logo.ico"
    make_shortcut(start_menu_link(), pyw, f'"{main}"', DEST / "app", icon, "Desktop HUD 실행")
    if desktop_shortcut:
        make_shortcut(desktop_link(), pyw, f'"{main}"', DEST / "app", icon, "Desktop HUD 실행")
    else:
        desktop_link().unlink(missing_ok=True)

    report("설정 > 앱 에 등록하는 중…")
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

    auto_ok = None
    report("자동 실행 설정 중…")
    code = "import sys; sys.path.insert(0, r'%s'); from hud import autostart; print(autostart.%s())" % (
        DEST / "app", "enable" if autostart else "disable")
    r = subprocess.run([str(DEST / "runtime" / "python.exe"), "-c", code], capture_output=True, creationflags=NO_WINDOW)
    auto_ok = (b"True" in r.stdout) if autostart else True

    refresh_icons()
    if run_after:
        subprocess.Popen([str(pyw), str(main)], cwd=str(DEST / "app"), creationflags=DETACHED)
    return {"autostart": autostart and auto_ok, "autostart_failed": autostart and not auto_ok}


def do_uninstall(keep_settings=True, report=lambda s: None):
    report("실행 중인 HUD 를 닫는 중…")
    stop_running(DEST)
    report("자동 실행과 바로가기를 지우는 중…")
    subprocess.run(["schtasks.exe", "/Delete", "/TN", APP_ID, "/F"], capture_output=True, creationflags=NO_WINDOW)
    for lnk in (desktop_link(), start_menu_link()):
        lnk.unlink(missing_ok=True)
    for key in (UNINSTALL_KEY, rf"Software\Classes\AppUserModelId\{APP_ID}"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
    report("남은 파일을 정리하는 중…")
    shutil.rmtree(Path(os.environ["LOCALAPPDATA"]) / APP_ID, ignore_errors=True)   # 캐시/로그
    if not keep_settings:
        shutil.rmtree(Path(os.environ["APPDATA"]) / APP_ID, ignore_errors=True)


def remove_install_folder_later():
    """지금 실행 중인 파이썬이 설치 폴더 안에 있으므로, 이 프로세스가 끝난 뒤 폴더를 지운다."""
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{DEST}"',
                     creationflags=NO_WINDOW | DETACHED, cwd=os.environ.get("TEMP", "C:\\"))


# ---------------------------------------------------------------- 설치 창 (WinForms)
def run_window(mode: str):
    """mode: 'install' / 'uninstall'. 창을 띄울 수 없으면 예외."""
    import clr
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System import Action
    from System.Drawing import Color, ContentAlignment, Font, FontStyle, Icon, Image, Point, Size
    from System.Threading import ApartmentState, Thread, ThreadStart
    from System.Windows.Forms import (AnchorStyles, Application, Button, CheckBox, DockStyle, FlatStyle, Form,
                                      FormBorderStyle, FormStartPosition, Label, Panel, PictureBox, PictureBoxSizeMode,
                                      ProgressBar, ProgressBarStyle)

    # 작업 표시줄에 파이썬 아이콘 대신 이 창의 로고가 보이도록 앱 ID 를 따로 준다
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DesktopHUD.Setup")
    sky, sky_deep, ink, mut, danger = (Color.FromArgb(14, 165, 233), Color.FromArgb(3, 105, 161),
                                       Color.FromArgb(12, 59, 90), Color.FromArgb(79, 111, 134), Color.FromArgb(220, 38, 38))
    face = "Malgun Gothic"
    error = {}

    def build():
        installing = mode == "install"
        f = Form()
        f.Text = f"{APP_NAME} {'설치' if installing else '제거'}"
        f.ClientSize = Size(500, 340)
        f.FormBorderStyle = FormBorderStyle.FixedSingle
        f.MaximizeBox = False
        f.StartPosition = FormStartPosition.CenterScreen
        f.BackColor = Color.White
        f.Font = Font(face, 9.5)
        f.Icon = Icon(str(HERE / "web" / "logo.ico"))

        head = Panel()
        head.Dock = DockStyle.Top
        head.Height = 104
        head.BackColor = Color.FromArgb(240, 249, 255)
        accent = Panel()                      # 머리글 아래 하늘색 줄
        accent.Dock = DockStyle.Bottom
        accent.Height = 3
        accent.BackColor = sky
        head.Controls.Add(accent)
        logo = PictureBox()
        logo.Image = Image.FromFile(str(HERE / "web" / "logo.png"))
        logo.SizeMode = PictureBoxSizeMode.Zoom
        logo.Location, logo.Size = Point(24, 16), Size(72, 72)
        logo.BackColor = Color.Transparent
        title = Label()
        title.Text = APP_NAME
        title.Font = Font(face, 18, FontStyle.Bold)
        title.ForeColor = ink
        title.AutoSize = True
        title.Location = Point(110, 22)
        sub = Label()
        sub.Text = f"버전 {VERSION} · 바탕화면 게임 / 파일 / 음악 런처"
        sub.ForeColor = mut
        sub.AutoSize = True
        sub.Location = Point(113, 64)
        for c in (logo, title, sub):
            head.Controls.Add(c)

        y = 122
        info = Label()
        info.AutoSize = False
        info.Size = Size(452, 40)
        info.Location = Point(24, y)
        info.ForeColor = mut
        if installing:
            info.Text = f"설치 위치: {DEST}\n관리자 권한 없이 현재 사용자에게만 설치돼요."
        else:
            info.Text = f"설치된 {APP_NAME} 를 제거해요.\n바탕화면·시작 메뉴 바로가기와 자동 실행도 함께 지워져요."
        f.Controls.Add(info)
        y += 50

        checks = []

        def check(text, on):
            nonlocal y
            c = CheckBox()
            c.Text, c.Checked, c.AutoSize = text, on, True
            c.ForeColor = ink
            c.Location = Point(26, y)
            f.Controls.Add(c)
            checks.append(c)
            y += 28
            return c

        if installing:
            c_auto = check("Windows 시작 시 자동으로 실행", True)
            c_desk = check("바탕화면에 바로가기 만들기", True)
            c_run = check("설치가 끝나면 바로 실행", True)
        else:
            c_del = check("설정도 함께 지우기 (스트리머 목록, 소리 장치, 바로가기 등)", False)

        status = Label()
        status.AutoSize = False
        status.Size = Size(452, 40)
        status.Location = Point(24, 252)
        status.ForeColor = ink
        status.Text = ""
        bar = ProgressBar()
        bar.Style = ProgressBarStyle.Marquee
        bar.Location, bar.Size = Point(24, 252), Size(452, 6)
        bar.Visible = False

        primary = Button()
        primary.Text = "설치" if installing else "제거"
        primary.Size = Size(110, 34)
        primary.Location = Point(366, 294)
        primary.FlatStyle = FlatStyle.Flat
        primary.FlatAppearance.BorderSize = 0
        primary.BackColor = sky if installing else danger
        primary.ForeColor = Color.White
        primary.Font = Font(face, 10, FontStyle.Bold)
        cancel = Button()
        cancel.Text = "취소"
        cancel.Size = Size(90, 34)
        cancel.Location = Point(268, 294)
        cancel.FlatStyle = FlatStyle.Flat
        cancel.FlatAppearance.BorderColor = Color.FromArgb(186, 230, 253)
        cancel.ForeColor = ink
        for c in (status, bar, primary, cancel):
            f.Controls.Add(c)
        f.Controls.Add(head)
        f.AcceptButton = primary

        state = {"done": False}

        def ui(fn):
            f.BeginInvoke(Action(fn))

        def set_status(text):
            ui(lambda: setattr(status, "Text", text))

        def finish(text, color=None):
            def apply():
                bar.Visible = False
                for c in checks:                  # 끝나면 선택 항목 대신 결과 문구를 그 자리에
                    c.Visible = False
                status.Location = Point(24, 176)
                status.Size = Size(452, 100)
                status.Font = Font(face, 10)
                status.Text = text
                if color is not None:
                    status.ForeColor = color
                primary.Text = "닫기"
                primary.BackColor = sky
                primary.Enabled = True
                cancel.Visible = False
                state["done"] = True
            ui(apply)

        def work():
            try:
                if installing:
                    res = do_install(c_auto.Checked, c_desk.Checked, c_run.Checked, report=set_status)
                    note = "자동 실행을 켜지 못했어요. HUD 설정에서 다시 켤 수 있어요." if res["autostart_failed"] else \
                        "바탕화면·시작 메뉴의 'Desktop HUD' 로 실행하고, 톱니바퀴 → 설정에서 바꿀 수 있어요."
                    finish("설치가 끝났어요.  " + note + "\n이 압축 푼 폴더는 이제 지워도 돼요.")
                else:
                    do_uninstall(keep_settings=not c_del.Checked, report=set_status)
                    state["remove_folder"] = True
                    finish("제거했어요.")
            except Exception as e:
                finish(f"문제가 생겼어요: {e}", danger)
                traceback.print_exc()

        def on_primary(sender, args):
            if state["done"]:
                f.Close()
                return
            primary.Enabled = False
            cancel.Enabled = False
            for c in checks:
                c.Enabled = False
            bar.Visible = True
            status.Location = Point(24, 264)
            threading.Thread(target=work, daemon=True).start()

        primary.Click += on_primary
        cancel.Click += lambda s, a: f.Close()
        Application.EnableVisualStyles()
        Application.Run(f)
        if state.get("remove_folder"):
            remove_install_folder_later()

    def guarded():
        try:
            build()
        except Exception as e:
            error["e"] = e

    t = Thread(ThreadStart(guarded))
    t.SetApartmentState(ApartmentState.STA)     # WinForms 는 STA 스레드에서
    t.Start()
    t.Join()
    if "e" in error:
        raise error["e"]


# ---------------------------------------------------------------- 메시지 상자로 진행 (예비)
def fallback(mode: str):
    if mode == "install":
        res = do_install()
        msg("설치가 끝났어요.\n\n"
            "• 바탕화면과 시작 메뉴에 'Desktop HUD' 바로가기를 만들었어요.\n"
            f"• Windows 시작 시 자동 실행: {'켜짐' if res['autostart'] else '설정하지 못함 (HUD 설정에서 켤 수 있어요)'}\n\n"
            "이 설치 폴더(압축 푼 폴더)는 이제 지워도 돼요.")
    else:
        if msg("Desktop HUD를 제거할까요?", MB_YESNO | MB_ICONQ) != IDYES:
            return
        keep = msg("설정(스트리머 목록, 소리 장치, 바로가기 등)은 남겨 둘까요?", MB_YESNO | MB_ICONQ) == IDYES
        do_uninstall(keep)
        msg("제거했어요.")
        remove_install_folder_later()


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    mode = "uninstall" if "--uninstall" in sys.argv else "install"
    if mode == "install" and SRC_ROOT.resolve() == DEST.resolve():
        msg("이미 설치된 위치에서 실행 중이에요.")
        sys.exit(0)
    try:
        try:
            run_window(mode)
        except Exception:
            traceback.print_exc()
            fallback(mode)
    except Exception as e:
        msg(f"문제가 생겼어요:\n{e}\n\n{traceback.format_exc()[-800:]}", MB_OK | MB_ICONERR)
        sys.exit(1)
