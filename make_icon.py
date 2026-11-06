"""Generate the File Sorter app icon."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "icon.ico"
PREVIEW = Path(__file__).resolve().parent / "icon_preview.png"

SIZE = 256
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

draw.rounded_rectangle(
    (8, 8, 248, 248), radius=52, fill="#0d1117", outline="#2b3542", width=5
)
draw.rounded_rectangle((26, 26, 230, 230), radius=40, fill="#111923")

draw.polygon(
    [(50, 90), (110, 90), (128, 108), (206, 108), (206, 162), (50, 162)],
    fill="#1d4ed8",
)
draw.rounded_rectangle((50, 112, 206, 198), radius=16, fill="#3b82f6")
draw.rounded_rectangle((50, 112, 206, 128), radius=8, fill="#60a5fa")

draw.rectangle((120, 128, 136, 162), fill="#ffffff")
draw.polygon([(102, 154), (128, 182), (154, 154)], fill="#ffffff")

image.save(
    OUT,
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
image.save(PREVIEW)
print("Wrote", OUT)
print("Wrote", PREVIEW)
