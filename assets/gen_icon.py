"""
大饼K线雷达 萌萌哒图标生成器
输出：
  icon_81.png   → 小程序 appIcon（81×81）
  icon_512.png  → 头像下载版（512×512）
"""
import math, os
from PIL import Image, ImageDraw, ImageFont

def make_icon(size):
    S = size
    C = S // 2  # 中心
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── 背景圆（黑金渐变感：用多层圆叠出）
    for i in range(20, 0, -1):
        r = int(C * (i / 20))
        alpha = int(255 * (1 - i / 22))
        # 深黑底
        d.ellipse([C-r, C-r, C+r, C+r],
                  fill=(8, 10, 18, 255 - alpha // 3))

    # 主背景圆
    d.ellipse([2, 2, S-2, S-2], fill=(10, 13, 22, 255))

    # 金色外圈光晕（多层）
    for i in range(5):
        gw = int(S * 0.012) * (5 - i)
        alpha_g = 60 - i * 10
        d.ellipse([2+gw, 2+gw, S-2-gw, S-2-gw],
                  outline=(251, 191, 36, alpha_g),
                  width=max(1, int(S * 0.004)))

    # 蓝色内圈
    d.ellipse([int(S*.05), int(S*.05), int(S*.95), int(S*.95)],
              outline=(96, 165, 250, 80),
              width=max(1, int(S * 0.006)))

    # ── K线柱子（3根，黑金风格）
    # 排列：左矮空 / 中高多 / 右中
    bars = [
        # (x_center_pct, body_top_pct, body_bot_pct, wick_top, wick_bot, color)
        (0.30, 0.62, 0.78, 0.58, 0.82, "short"),   # 左：空头阴线（绿）
        (0.50, 0.32, 0.65, 0.22, 0.70, "long"),     # 中：多头阳线（红，最高）
        (0.70, 0.50, 0.72, 0.44, 0.76, "short"),    # 右：小阴线（绿）
    ]
    bar_w = S * 0.10
    for bx, bt, bb, wt, wb, typ in bars:
        cx = S * bx
        body_t = S * bt
        body_b = S * bb
        wick_t = S * wt
        wick_b = S * wb
        if typ == "long":
            col = (251, 113, 133, 240)   # 红（中国涨色）
            col_wick = (251, 113, 133, 180)
        else:
            col = (52, 211, 153, 220)    # 绿（跌色）
            col_wick = (52, 211, 153, 160)

        # 影线
        lw = max(1, int(S * 0.012))
        d.line([(cx, wick_t), (cx, wick_b)], fill=col_wick, width=lw)
        # 实体
        bw = bar_w
        d.rounded_rectangle(
            [cx - bw/2, body_t, cx + bw/2, body_b],
            radius=max(1, int(S * 0.02)),
            fill=col
        )

    # ── 雷达扫描弧（金色，右下角）
    arc_r = int(S * 0.28)
    arc_cx = int(S * 0.50)
    arc_cy = int(S * 0.50)
    for i, (r_off, a_start, a_end, alpha_a) in enumerate([
        (0,       0, 360, 25),
        (-int(S*.05), 20, 160, 50),
        (-int(S*.10), 30, 130, 80),
    ]):
        r2 = arc_r + r_off
        d.arc(
            [arc_cx - r2, arc_cy - r2, arc_cx + r2, arc_cy + r2],
            start=a_start, end=a_end,
            fill=(96, 165, 250, alpha_a),
            width=max(1, int(S * 0.012))
        )

    # ── 中心圆点（金色 glow）
    dot_r = int(S * 0.04)
    for layer, alpha_l in [(dot_r*3, 30), (dot_r*2, 60), (dot_r, 220)]:
        color_l = (251, 191, 36, alpha_l)
        d.ellipse([arc_cx - layer, arc_cy - layer,
                   arc_cx + layer, arc_cy + layer],
                  fill=color_l)

    # ── 顶部小可爱表情（仅 512 大图才画，小图太小）
    if S >= 256:
        face_size = int(S * 0.22)
        fx = int(S * 0.72)
        fy = int(S * 0.12)
        # 圆脸
        d.ellipse([fx, fy, fx+face_size, fy+face_size],
                  fill=(255, 220, 100, 230),
                  outline=(251, 191, 36, 180),
                  width=max(1, int(S * 0.005)))
        # 眼睛
        ew = face_size // 8
        ex1 = fx + face_size // 3 - ew
        ex2 = fx + face_size * 2 // 3 - ew
        ey  = fy + face_size // 3 - ew
        d.ellipse([ex1, ey, ex1+ew*2, ey+ew*2], fill=(40, 30, 20, 220))
        d.ellipse([ex2, ey, ex2+ew*2, ey+ew*2], fill=(40, 30, 20, 220))
        # 微笑
        smile_x1 = fx + face_size // 4
        smile_y1 = fy + face_size * 55 // 100
        smile_x2 = fx + face_size * 3 // 4
        smile_y2 = fy + face_size * 75 // 100
        d.arc([smile_x1, smile_y1, smile_x2, smile_y2],
              start=10, end=170,
              fill=(180, 80, 30, 200),
              width=max(2, int(S * 0.008)))

    # ── 底部文字"大饼"（仅512版）
    if S >= 256:
        try:
            # 尝试加载系统中文字体
            fnt_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
            ]
            fnt = None
            fsize = int(S * 0.085)
            for fp in fnt_paths:
                if os.path.exists(fp):
                    fnt = ImageFont.truetype(fp, fsize)
                    break
            if fnt:
                text = "大饼K线雷达"
                bbox = d.textbbox((0, 0), text, font=fnt)
                tw = bbox[2] - bbox[0]
                tx = (S - tw) // 2
                ty = int(S * 0.82)
                # 文字阴影
                d.text((tx+2, ty+2), text, font=fnt, fill=(0,0,0,120))
                # 渐变文字感（用金色）
                d.text((tx, ty), text, font=fnt, fill=(251, 191, 36, 220))
        except Exception:
            pass

    return img


# 输出目录
out_dir = os.path.dirname(os.path.abspath(__file__))

img512 = make_icon(512)
img512.save(os.path.join(out_dir, "icon_512.png"), "PNG")
print("✅ icon_512.png 已生成")

img81 = make_icon(81)
img81.save(os.path.join(out_dir, "icon_81.png"), "PNG")
print("✅ icon_81.png 已生成")

# 还生成一个 144px（微信小程序 appicon 要求）
img144 = make_icon(144)
img144.save(os.path.join(out_dir, "icon_144.png"), "PNG")
print("✅ icon_144.png 已生成")

print("\n📁 所有图标已保存到:", out_dir)
