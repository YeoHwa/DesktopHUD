"""Desktop HUD 아이콘 만들기 → web/logo.ico (16~256 여러 크기), web/logo.png (256), docs/icon.png (512)

미니멀 디자인: 단색 하늘색 타일(HUD 패널처럼 왼쪽 위·오른쪽 아래 모서리를 자름) 위에
               흰 막대 하나(왼쪽 메뉴 열)와 반투명 흰 판 하나(오른쪽 창). 그라데이션·장식 없음.
실행:  uv run python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SKY = (14, 165, 233)     # #0EA5E9 — HUD 의 강조색과 같음
WHITE = (255, 255, 255)


def chamfer(x0, y0, x1, y1, cut):
    """왼쪽 위·오른쪽 아래를 자른 사각형 (HUD 패널 모양)."""
    return [(x0 + cut, y0), (x1, y0), (x1, y1 - cut), (x1 - cut, y1), (x0, y1), (x0, y0 + cut)]


def draw(size: int) -> Image.Image:
    S = size * 4                                   # 4배로 그린 뒤 줄여서 경계를 부드럽게
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pad, cut = round(S * 0.06), round(S * 0.22)
    ImageDraw.Draw(img).polygon(chamfer(pad, pad, S - pad, S - pad, cut), fill=SKY + (255,))

    # 반투명 흰색이 하늘색과 섞이도록 별도 층에 그려 합성
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    top, bottom = round(S * 0.30), round(S * 0.70)
    d.rectangle([round(S * 0.27), top, round(S * 0.41), bottom], fill=WHITE + (255,))   # 메뉴 열
    d.rectangle([round(S * 0.47), top, round(S * 0.73), bottom], fill=WHITE + (150,))   # 창
    img = Image.alpha_composite(img, layer)
    return img.resize((size, size), Image.LANCZOS)


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [draw(s) for s in sizes]
    web = ROOT / "web"
    frames[-1].save(web / "logo.png")
    frames[-1].save(web / "logo.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    draw(512).save(docs / "icon.png")
    print("만들었어요:", web / "logo.ico", web / "logo.png", docs / "icon.png")


if __name__ == "__main__":
    main()
