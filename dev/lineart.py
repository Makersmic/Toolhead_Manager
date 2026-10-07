"""Turn the manual's black-on-white tool drawings into transparent line art: one copy with black lines
(light theme) and one with white lines (dark theme). Red callouts (boxes, their white lettering, arrows)
are kept exactly as drawn in both."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage

def convert(src, out_base, max_size=(700, 1100)):
    im = Image.open(src).convert("RGB"); im.thumbnail(max_size, Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # red / reddish pixels (callout boxes, arrows, renders) - including their anti-aliased edges
    red = (r - np.maximum(g, b) > 40) & (r > 110)
    # a callout = red outline + its white lettering: fill the holes inside red regions, grow by 1 px for the edge
    callout = ndimage.binary_fill_holes(ndimage.binary_closing(red, iterations=2))
    callout = ndimage.binary_dilation(callout, iterations=1)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    border = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    paper = float(np.median(border))                             # the drawing's background (white, or a render's grey)
    ink = np.clip((paper - lum) / max(paper, 1.0), 0, 1) ** 0.85  # how dark the line work is -> its opacity
    for name, line in (("light", 0.0), ("dark", 255.0)):
        out = np.zeros(a.shape[:2] + (4,), np.float32)
        out[..., 0:3] = line
        out[..., 3] = ink * 255
        out[callout, 0:3] = a[callout]
        out[callout, 3] = 255
        Image.fromarray(out.round().astype(np.uint8), "RGBA").save(f"{out_base}-{name}.png", optimize=True)

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
