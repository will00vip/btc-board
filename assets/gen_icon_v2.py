"""
大饼K线雷达 萌萌哒图标 v2
- 圆脸大眼睛可爱小表情
- K线柱子做成装饰
- 黑金配色 + 发光效果
"""
import math, os
from PIL import Image, ImageDraw, ImageFont

def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)

def make_cute_icon(size):
    S = size
    C = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── 1. 圆角方形背景（黑金渐变感）
    corner = int(S * 0.22)
    # 最底层深色
    draw_rounded_rect(d, [0, 0, S-1, S-1], corner, fill=(8, 10, 16, 255))
    # 金色顶部高光
    draw_rounded_rect(d, [0, 0, S-1, int(S*0.5)], corner, fill=(255, 200, 0, 12))
    # 外边框（金色）
    draw_rounded_rect(d, [int(S*0.015), int(S*0.015), S-int(S*0.015)-1, S-int(S*0.015)-1],
                      corner, fill=None, outline=(251, 191, 36, 180), width=max(2, int(S*0.012)))
    # 内层蓝色细边
    draw_rounded_rect(d, [int(S*0.04), int(S*0.04), S-int(S*0.04)-1, S-int(S*0.04)-1],
                      int(corner*0.8), fill=None, outline=(96, 165, 250, 60), width=max(1, int(S*0.005)))

    # ── 2. K线装饰（底部三根柱子）
    bar_y_bot = int(S * 0.90)
    bar_y_tops = [int(S*0.60), int(S*0.44), int(S*0.55)]  # 左中右顶部
    bar_colors = [(52, 211, 153, 200), (251, 113, 133, 220), (52, 211, 153, 190)]
    bar_xs = [int(S*0.20), int(S*0.46), int(S*0.72)]
    bw = int(S * 0.11)
    wick_w = max(1, int(S * 0.013))
    for i in range(3):
        cx = bar_xs[i]
        top = bar_y_tops[i]
        col = bar_colors[i]
        # 影线
        d.line([(cx, int(top - S*0.06)), (cx, bar_y_bot + int(S*0.03))],
               fill=(*col[:3], 120), width=wick_w)
        # 实体
        d.rounded_rectangle(
            [cx - bw//2, top, cx + bw//2, bar_y_bot],
            radius=max(1, int(S*0.025)),
            fill=col
        )

    # ── 3. 圆脸（主角！）
    face_r = int(S * 0.265)
    face_cx = int(S * 0.50)
    face_cy = int(S * 0.34)
    # 脸部阴影/发光
    for expand in range(6, 0, -1):
        glow_alpha = 15 * expand
        d.ellipse([face_cx-face_r-expand, face_cy-face_r-expand,
                   face_cx+face_r+expand, face_cy+face_r+expand],
                  fill=(251, 191, 36, glow_alpha))
    # 脸底色
    d.ellipse([face_cx-face_r, face_cy-face_r,
               face_cx+face_r, face_cy+face_r],
              fill=(255, 218, 80, 240))
    # 脸边框
    d.ellipse([face_cx-face_r, face_cy-face_r,
               face_cx+face_r, face_cy+face_r],
              fill=None, outline=(200, 140, 0, 200), width=max(1, int(S*0.008)))
    # 腮红
    blush_r = int(face_r * 0.28)
    blush_off_x = int(face_r * 0.58)
    blush_off_y = int(face_r * 0.25)
    d.ellipse([face_cx - blush_off_x - blush_r, face_cy + blush_off_y - blush_r//2,
               face_cx - blush_off_x + blush_r, face_cy + blush_off_y + blush_r//2],
              fill=(255, 150, 150, 90))
    d.ellipse([face_cx + blush_off_x - blush_r, face_cy + blush_off_y - blush_r//2,
               face_cx + blush_off_x + blush_r, face_cy + blush_off_y + blush_r//2],
              fill=(255, 150, 150, 90))
    # 眼睛（大圆眼，有高光）
    eye_r = int(face_r * 0.22)
    eye_off_x = int(face_r * 0.42)
    eye_y = face_cy - int(face_r * 0.08)
    for ex in [face_cx - eye_off_x, face_cx + eye_off_x]:
        d.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
                  fill=(30, 20, 10, 240))
        # 眼白高光
        hl_r = max(1, int(eye_r * 0.35))
        d.ellipse([ex - eye_r//2, eye_y - eye_r//2,
                   ex - eye_r//2 + hl_r*2, eye_y - eye_r//2 + hl_r*2],
                  fill=(255, 255, 255, 200))
    # 眉毛
    brow_r = int(face_r * 0.42)
    brow_y = eye_y - int(face_r * 0.30)
    brow_w = max(1, int(S * 0.012))
    for bx in [face_cx - brow_r, face_cx + brow_r]:
        bw2 = int(face_r * 0.22)
        d.arc([bx - bw2, brow_y - bw2//2, bx + bw2, brow_y + bw2//2],
              start=200, end=340, fill=(80, 50, 10, 200), width=brow_w)
    # 嘴巴（大弧度微笑）
    mouth_w = int(face_r * 0.75)
    mouth_y = face_cy + int(face_r * 0.25)
    d.arc([face_cx - mouth_w, mouth_y - mouth_w//2,
           face_cx + mouth_w, mouth_y + mouth_w//2],
          start=15, end=165, fill=(160, 60, 20, 220), width=max(2, int(S*0.015)))

    # ── 4. 右上角小雷达图标
    if S >= 128:
        rad_cx = int(S * 0.80)
        rad_cy = int(S * 0.20)
        rad_r = int(S * 0.10)
        for rr in [rad_r, rad_r*2, rad_r*3]:
            alpha = 120 - rr // 2
            d.arc([rad_cx - rr, rad_cy - rr, rad_cx + rr, rad_cy + rr],
                  start=150, end=390, fill=(96, 165, 250, alpha),
                  width=max(1, int(S*0.010)))
        d.ellipse([rad_cx-int(S*0.022), rad_cy-int(S*0.022),
                   rad_cx+int(S*0.022), rad_cy+int(S*0.022)],
                  fill=(251, 191, 36, 230))

    return img


out_dir = os.path.dirname(os.path.abspath(__file__))

img512 = make_cute_icon(512)
img512.save(os.path.join(out_dir, "icon_512.png"), "PNG")

img144 = make_cute_icon(144)
img144.save(os.path.join(out_dir, "icon_144.png"), "PNG")

img81 = make_cute_icon(81)
img81.save(os.path.join(out_dir, "icon_81.png"), "PNG")

# 微信头像用圆形裁切版（512）
mask = Image.new("L", (512, 512), 0)
mask_d = ImageDraw.Draw(mask)
mask_d.ellipse([0, 0, 511, 511], fill=255)
avatar = make_cute_icon(512).convert("RGBA")
result = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
result.paste(avatar, (0, 0), mask)
result.save(os.path.join(out_dir, "avatar_round_512.png"), "PNG")

print("done: icon_512.png / icon_144.png / icon_81.png / avatar_round_512.png")
