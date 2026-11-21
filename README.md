# Desktop HUD

Windows 바탕화면에 깔리는, PC방 런처 같은 HUD입니다.
흰색/하늘색(또는 어두운 테마)의 반투명 패널로 게임 실행, 파일 관리, 음악 조작, 치지직 방송 알림을 한곳에서 할 수 있어요.

## 기능

| 영역 | 내용 |
|---|---|
| 상태 | 시계·날짜, CPU / GPU(NVIDIA) / RAM 사용률 |
| 마우스 배터리 | Logitech(G HUB 실시간), Razer 무선 마우스(USB HID 로 직접 읽음, Synapse 불필요) |
| 소리 출력 | 자주 쓰는 출력 장치 2개를 버튼 하나로 전환 (꺼진 장치도 자동으로 켬) |
| 빠른 버튼 | 4칸에 원하는 기능 배치: 마이크 음소거, 화면 캡처, 화면 잠금, 화면 끄기, 절전, RAM 청소, 클립보드 기록, 집중 모드, 음소거, 배경 멈춤, 작업 관리자, 계산기, Windows 설정, 휴지통 비우기 |
| 게임 | Steam · Riot · Nexon · Battle.net · Epic 설치 게임 자동 감지, 실제 아이콘, 직접 추가/숨기기 |
| 치지직 라이브 | 스트리머 검색·등록, 방송 시작 시 Windows 알림 |
| 음악 | 지금 재생 중인 곡(YouTube Music 등) 표시, 이전/다음·10초 이동·재생, PC 음량 |
| 내 파일 | 다운로드·스크린샷·문서 등 폴더, 휴지통 열기/비우기, 드라이브 용량 |
| 개발 유틸리티 | 프로젝트 폴더 자동 목록(폴더/터미널로 열기), 터미널·VS Code·Docker 등 |
| 시스템 | RAM 청소, 집중 모드, 모니터 1/2, 배경(Wallpaper Engine) 일시정지, 디스크 정리, 안전 종료 |
| 웹 바로가기 | 자주 가는 사이트 추가/삭제 |

창은 항상 다른 창들 **뒤**(바탕화면 층)에 깔리고, 작업 표시줄·Alt+Tab 에는 나오지 않아요.

## 설치 (사용자)

1. [Releases](../../releases) 에서 `DesktopHUD-x.y.z.zip` 을 받아 압축을 풉니다.
2. `설치.cmd` 를 더블클릭합니다. ("Windows의 PC 보호" 창이 뜨면 **추가 정보 → 실행**)
3. 설치가 끝나면 HUD가 바로 켜지고, 다음부터는 로그인할 때 자동으로 켜집니다.

- 관리자 권한 없이 현재 사용자에게만 설치됩니다 (`%LOCALAPPDATA%\Programs\DesktopHUD`).
- 제거: **설정 → 앱 → 설치된 앱 → Desktop HUD → 제거**
- 요구 사항: Windows 10 (1803+) / 11, Microsoft Edge WebView2 런타임 (Windows 11 기본 포함)

## 사용

- 시계 부분을 끌면 위치를 옮길 수 있어요. 화면 오른쪽에 두면 메뉴 창이 왼쪽으로 열려요.
- 톱니바퀴 → **설정**: 자동 실행, 테마·글꼴, 패널 투명도(%), 위치·크기(모니터, 붙일 쪽, 여백, 배율, 메뉴 창 너비, 높이),
  소리 출력 장치, 빠른 버튼, 음악 플레이어, 왼쪽 메뉴 순서, 마우스 배터리, 키보드 버튼 링크, 프로젝트 폴더
- 설정 파일: `%APPDATA%\DesktopHUD\config.json` · 로그: `%LOCALAPPDATA%\DesktopHUD\hud.log`

## 개발

```powershell
uv sync                      # 의존성 설치 (.venv)
uv run python main.py        # 실행
uv run python main.py --debug --panel=game --theme=dark   # 개발자 도구 + 패널 열기 + 테마
```

### 배포 파일 만들기

```powershell
.\build_dist.ps1             # → dist\DesktopHUD-<버전>.zip
```

exe 로 묶지 않는 이유: Windows 11 **스마트 앱 컨트롤**이 서명되지 않은 새 exe(PyInstaller 결과물, 설치 exe 등)를 막습니다.
그래서 배포 파일은 python.org 의 **서명된 공식 Python 런타임** + PyPI 라이브러리 + 이 저장소의 코드로만 구성되고,
설치/제거는 `installer.py` 가 합니다. 빌드에는 python.org 에서 설치한 Python 3.12 가 필요해요.

### 구조

```
main.py            진입점, JS ↔ Python API
installer.py       설치 / 제거
hud/
  config.py        설정 파일, 처음 실행 시 자동 감지로 기본값 생성
  detect.py        설치된 프로그램 찾기 (앱 제거 목록, 시작 메뉴)
  games.py         게임 감지 / 실행
  desktop.py       창을 바탕화면 층에 고정, 투명 처리, 크기
  audio.py         출력 장치 목록 / 전환 (IPolicyConfig)
  media.py         재생 중인 곡 (Windows 미디어 제어), 음량
  mouse.py         마우스 배터리 (ghub.py, razer.py)
  chzzk.py         치지직 방송 확인 / 알림
  quick.py         빠른 버튼 (마이크, 캡처, 잠금 등)
  players.py       음악 플레이어 선택
  winrt_net.py     Windows 런타임 API 를 .NET 으로 호출
  system.py        시스템 상태, 빠른 기능, 파일, 개발 도구
  autostart.py     작업 스케줄러 자동 실행
web/               HUD 화면 (HTML / CSS / JS)
```

## 알아 둘 점

- 치지직 방송 확인은 치지직의 공개되지 않은 API 를 쓰므로, 치지직 쪽이 바뀌면 동작하지 않을 수 있어요.
- Razer 배터리는 openrazer 에 공개된 프로토콜을 사용합니다. 모델에 따라 지원되지 않을 수 있어요.
- G HUB 배터리는 G HUB 의 로컬 연결(127.0.0.1:9010)을 사용합니다. G HUB 가 없으면 Logitech 수신기에 HID++ 로 직접 묻습니다.
- 재생 중인 곡 정보와 Windows 알림은 .NET Framework(pythonnet) 으로 Windows 런타임 API 를 호출합니다.
  (winrt 파이썬 패키지의 네이티브 파일이 스마트 앱 컨트롤에 막히는 경우가 있어서 쓰지 않음)

## 라이선스

코드: [MIT](LICENSE)

함께 들어 있는 글꼴 (`web/fonts`, 모두 SIL Open Font License 1.1 — 라이선스 전문은 같은 폴더에 있음)
- [Pretendard](https://github.com/orioncactus/pretendard) © Kil Hyung-jin
- [SUIT](https://github.com/sun-typeface/SUIT) © SUNN
- [Rajdhani](https://fonts.google.com/specimen/Rajdhani) © Indian Type Foundry

프로그램/사이트 로고는 저장소에 포함하지 않고, 실행하는 PC 에서 각 앱·사이트의 아이콘을 가져와 표시합니다.
