# -*- coding: utf-8 -*-
"""生成软件图标：R 字样，输出为 icon.ico（多尺寸供 Windows 使用）"""
import os
from PIL import Image, ImageDraw, ImageFont

def build_icon():
    base = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base, "icon.ico")
    w = h = 256
    img = Image.new("RGBA", (w, h), (30, 40, 60, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 180)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 180)
        except Exception:
            font = ImageFont.load_default()
    text = "R"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (w - tw) // 2 - bbox[0]
    y = (h - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    img.save(out_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("已生成:", out_path)

if __name__ == "__main__":
    build_icon()
