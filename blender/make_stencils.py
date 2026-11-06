"""Render the text masks painted onto the suit and pack (run with a Python that has Pillow, not Blender's).

  python3 blender/make_stencils.py

Each mask is a grayscale PNG, white = ink, sized to the label's aspect ratio. texturing.py samples them
by the label's local (s, t) coordinates, so the resolution here only needs to beat the texel density.
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stencils')
FONT = '/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf'

# name: (text, width_px, height_px)
LABELS = {
    'fuel': ('FUEL', 512, 160),
    'pilot': ('PILOT', 512, 160),
    'caution': ('CAUTION  HOT', 768, 128),
}

os.makedirs(OUT, exist_ok=True)
for name, (text, w, h) in LABELS.items():
    img = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(img)
    size = h
    while True:
        font = ImageFont.truetype(FONT, size)
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
        if x1 - x0 <= w * 0.92 and y1 - y0 <= h * 0.80:
            break
        size -= 2
    d.text(((w - (x1 - x0)) / 2 - x0, (h - (y1 - y0)) / 2 - y0), text, font=font, fill=255)
    img.save(os.path.join(OUT, name + '.png'))
    print('wrote', name, size)
