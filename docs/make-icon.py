#!/usr/bin/env python3
"""生成项目图标 docs/icon.png（Unraid 容器模板等地方要用方形图标）。

这个脚本只在需要重新生成图标时手动跑一次，**不属于应用的一部分** ——
应用本身是零依赖的，这里用 Pillow 只是为了画图。

    pip install Pillow          # 或者用任意带 Pillow 的 Python
    python3 docs/make-icon.py

设计：深色圆角底 + 雷达同心圆 + 中心点 + 三个「设备」绿点，
配色取自 static/style.css 的 --accent(#3b82f6) / --green(#34d399) / --bg(#0d1117)。
"""
import os
from PIL import Image, ImageDraw

SIZE = 512          # 最终尺寸
SS = 4              # 超采样倍数，先画大图再缩小，边缘才平滑
S = SIZE * SS

ACCENT = (59, 130, 246)      # --accent
ACCENT_LIGHT = (96, 165, 250)
GREEN = (52, 211, 153)       # --green
BG_TOP = (23, 34, 47)        # 与 .dev-card 渐变同色系
BG_BOTTOM = (13, 17, 23)     # --bg
BORDER = (37, 48, 64)        # --line


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def blend(base, paint, alpha=255):
    """把 paint(draw) 画到透明层，再按 alpha 正确混到 base 上。

    ⚠️ 不能直接 ImageDraw 画带 alpha 的颜色：那是**替换**像素（连 alpha 一起换掉），
    不是混合，结果会在浅色背景上变成一层发白的淡色。必须先画到独立图层再 alpha_composite。
    """
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer))
    if alpha < 255:
        layer.putalpha(layer.getchannel("A").point(lambda v: v * alpha // 255))
    return Image.alpha_composite(base, layer)


def main():
    import math

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ---- 圆角底：竖向渐变 ----
    radius = int(S * 0.22)
    grad = Image.new("RGBA", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.point((0, y), fill=lerp(BG_TOP, BG_BOTTOM, y / (S - 1)) + (255,))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    def _border(d):
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius,
                            outline=BORDER, width=max(2, int(S * 0.007)))
    img = blend(img, _border)

    cx = cy = S / 2

    # ---- 雷达同心圆：越往外越淡（用 blend 才不会发白）----
    for frac, alpha in ((0.150, 255), (0.250, 215), (0.350, 150)):
        r = S * frac
        w = max(3, int(S * 0.028))

        def _ring(d, r=r, w=w):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT_LIGHT, width=w)
        img = blend(img, _ring, alpha)

    # ---- 中心点 ----
    cr = S * 0.055

    def _hub(d):
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=ACCENT_LIGHT)
    img = blend(img, _hub)

    # ---- 三个「设备」绿点，落在不同半径/角度上 ----
    contacts = [(0.350, -62, 0.047), (0.250, 152, 0.041), (0.150, 30, 0.035)]
    for ring_frac, deg, dot_frac in contacts:
        rad = math.radians(deg)
        x = cx + math.cos(rad) * S * ring_frac
        y = cy + math.sin(rad) * S * ring_frac
        rr = S * dot_frac

        def _halo(d, x=x, y=y, rr=rr):     # 深色描边，和圆环分开
            d.ellipse([x - rr * 1.45, y - rr * 1.45, x + rr * 1.45, y + rr * 1.45], fill=BG_BOTTOM)
        img = blend(img, _halo)

        def _dot(d, x=x, y=y, rr=rr):
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=GREEN)
        img = blend(img, _dot)

    out = img.resize((SIZE, SIZE), Image.LANCZOS)

    # ---- 顺便导出 Unraid 也够用的几个尺寸 ----
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(here, "icon.png")
    out.save(main_path, "PNG", optimize=True)
    print(f"已生成 {main_path}  {SIZE}x{SIZE}  {os.path.getsize(main_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
