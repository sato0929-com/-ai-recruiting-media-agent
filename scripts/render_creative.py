"""クリエイティブエージェントの出力(レイアウト指示)から、実際の画像・動画を生成する。

AIに画像・動画そのものを生成させるのではなく、共通のHTML/CSSテンプレートに文字を
流し込み、ヘッドレスブラウザ(Playwright)でスクリーンショットを撮る方式にしている。
Remotionは組織の売上規模によっては有料ライセンスが必要になる可能性があるため使わない。

- カルーセル画像(1080x1350): render_carousel()
- Shorts動画(1080x1920、無音): render_shorts_video()(FFmpegが別途必要)
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

CAROUSEL_SIZE = (1080, 1350)
SHORTS_SIZE = (1080, 1920)

# 共通テンプレート(3種類まで運用する想定。agents/05_creative.md 参照)
# 配色は青・シルバー・白を基調とする(2026-09-14変更)。
TEMPLATES = {
    "template_a": {"bg": "#ffffff", "ink": "#0b1f3a", "accent": "#1d4ed8", "accent_soft": "#e8edf7"},
    "template_b": {"bg": "#0b1f3a", "ink": "#f5f7fa", "accent": "#8fb2e8", "accent_soft": "#16305a"},
    "template_c": {"bg": "#eef0f3", "ink": "#0b1f3a", "accent": "#1d4ed8", "accent_soft": "#ffffff"},
}

_FONT_LINK = (
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@700&'
    'family=Noto+Sans+JP:wght@500;700&display=swap">'
)

_CAROUSEL_HTML = """<!doctype html>
<html><head><meta charset="utf-8">{font_link}
<style>
  html,body{{margin:0;padding:0;}}
  body{{
    width:{w}px;height:{h}px;background:{bg};color:{ink};
    font-family:"Noto Sans JP",sans-serif;
    display:flex;flex-direction:column;
    box-sizing:border-box;padding:120px 110px;
  }}
  .eyebrow{{font-size:26px;color:{accent};font-weight:700;letter-spacing:.14em;}}
  .content{{flex:1;display:flex;flex-direction:column;justify-content:center;}}
  h1{{
    font-family:"Shippori Mincho",serif;font-size:62px;line-height:1.55;
    margin:0;color:{ink};white-space:pre-line;
  }}
  p{{
    font-size:32px;line-height:1.95;margin:48px 0 0;color:{ink};
    white-space:pre-line;
  }}
  .footer{{
    display:flex;justify-content:space-between;align-items:center;
    font-size:22px;color:{accent};padding-top:32px;border-top:1px solid {accent_soft};
  }}
  .pagebox{{
    border:1px solid {accent};color:{accent};border-radius:999px;padding:8px 24px;font-weight:700;
  }}
</style></head>
<body>
  <div class="eyebrow">採用AIメディア</div>
  <div class="content">
    <h1>{heading}</h1>
    <p>{body}</p>
  </div>
  <div class="footer">
    <span>採用・転職・AI活用の実務メディア</span>
    <span class="pagebox">{slide_no} / {slide_total}</span>
  </div>
</body></html>
"""

_SHORTS_FRAME_HTML = """<!doctype html>
<html><head><meta charset="utf-8">{font_link}
<style>
  html,body{{margin:0;padding:0;}}
  body{{
    width:{w}px;height:{h}px;background:{bg};color:{ink};
    font-family:"Noto Sans JP",sans-serif;
    display:flex;align-items:center;justify-content:center;
    box-sizing:border-box;padding:160px 130px;
  }}
  p{{
    font-family:"Shippori Mincho",serif;font-size:68px;line-height:1.7;
    text-align:center;color:{ink};white-space:pre-line;
  }}
  .accent-bar{{
    position:absolute;top:0;left:0;right:0;height:6px;background:{accent};
  }}
</style></head>
<body>
  <div class="accent-bar"></div>
  <p>{text}</p>
</body></html>
"""


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    # このClaude Code開発環境ではPlaywrightに同梱されたffmpegが使える。
    # GitHub Actions(ubuntu-latest)には標準でffmpegが入っているため、通常はshutil.whichで見つかる。
    fallback = Path("/opt/pw-browsers")
    if fallback.exists():
        for candidate in fallback.glob("ffmpeg-*/ffmpeg-linux"):
            return str(candidate)
    raise RuntimeError("ffmpegが見つかりません。`apt-get install ffmpeg` 等でインストールしてください。")


def _pinned_chromium_executable() -> str | None:
    """このClaude Code開発環境のように、pipのplaywrightパッケージが期待する
    ブラウザのリビジョンと、あらかじめ用意されたブラウザのリビジョンがずれている場合の
    救済策。GitHub Actions上では `playwright install` でリビジョンが一致するため通常は不要。"""
    base = Path("/opt/pw-browsers")
    if not base.exists():
        return None
    for candidate in base.glob("chromium-*/chrome-linux/chrome"):
        return str(candidate)
    return None


def _launch_kwargs() -> dict:
    """開発環境のようにHTTPSプロキシ経由でしか外部(Googleフォント等)に出られない場合、
    ChromiumはHTTPS_PROXY環境変数を自動では見ないため、明示的に渡す。
    GitHub Actions等プロキシのない環境では何も渡さない。"""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_url:
        return {"proxy": {"server": proxy_url}}
    return {}


def _screenshot_html(
    html_content: str, size: tuple[int, int], output_path: Path, image_type: str = "png"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    launch_kwargs = _launch_kwargs()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception:
            executable_path = _pinned_chromium_executable()
            if not executable_path:
                raise
            browser = p.chromium.launch(executable_path=executable_path, **launch_kwargs)
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        page.set_content(html_content, wait_until="networkidle")
        if image_type == "jpeg":
            page.screenshot(path=str(output_path), type="jpeg", quality=92)
        else:
            page.screenshot(path=str(output_path))
        browser.close()


def render_carousel(slides: list[dict], output_dir: Path, template: str = "template_a") -> list[Path]:
    """slides: [{"heading": str, "body": str}, ...] -> 生成したJPEGファイルパスの一覧

    Instagram Graph APIの画像投稿はJPEG形式のみ受け付けるため、PNGではなくJPEGで出力する。
    """
    colors = TEMPLATES[template]
    output_dir = Path(output_dir)
    paths = []
    for i, slide in enumerate(slides, start=1):
        content = _CAROUSEL_HTML.format(
            font_link=_FONT_LINK,
            w=CAROUSEL_SIZE[0],
            h=CAROUSEL_SIZE[1],
            bg=colors["bg"],
            ink=colors["ink"],
            accent=colors["accent"],
            accent_soft=colors["accent_soft"],
            heading=html.escape(slide["heading"]),
            body=html.escape(slide["body"]),
            slide_no=i,
            slide_total=len(slides),
        )
        out_path = output_dir / f"slide_{i:02d}.jpg"
        _screenshot_html(content, CAROUSEL_SIZE, out_path, image_type="jpeg")
        paths.append(out_path)
    return paths


def render_shorts_video(
    caption_chunks: list[dict], output_path: Path, template: str = "template_a", fps: int = 30
) -> Path:
    """caption_chunks: [{"text": str, "duration_sec": number}, ...] -> 生成したmp4のパス"""
    colors = TEMPLATES[template]
    output_path = Path(output_path)
    frame_dir = output_path.parent / f"{output_path.stem}_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    frame_paths = []
    for i, chunk in enumerate(caption_chunks, start=1):
        content = _SHORTS_FRAME_HTML.format(
            font_link=_FONT_LINK,
            w=SHORTS_SIZE[0],
            h=SHORTS_SIZE[1],
            bg=colors["bg"],
            ink=colors["ink"],
            accent=colors["accent"],
            text=html.escape(chunk["text"]),
        )
        frame_path = frame_dir / f"frame_{i:03d}.png"
        _screenshot_html(content, SHORTS_SIZE, frame_path)
        frame_paths.append((frame_path, chunk.get("duration_sec", 3)))

    concat_file = frame_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for frame_path, duration in frame_paths:
            f.write(f"file '{frame_path.resolve()}'\n")
            f.write(f"duration {duration}\n")
        # ffmpeg concatの仕様上、最後のファイルはdurationが無視されるため同じ画像をもう一度書く。
        if frame_paths:
            f.write(f"file '{frame_paths[-1][0].resolve()}'\n")

    ffmpeg = _find_ffmpeg()
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-vf", f"fps={fps},format=yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
