"""Combine PNG frames (e.g. m4cm output) into an animated GIF."""

import argparse
import glob
import sys
from pathlib import Path

from PIL import Image


def expand(patterns: list[str]) -> list[Path]:
    files = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
        files += [Path(m) for m in matches]
    return files


def load_frames(files: list[Path], background: str) -> list[Image.Image]:
    images = [Image.open(f).convert("RGBA") for f in files]
    width = max(im.width for im in images)
    height = max(im.height for im in images)
    frames = []
    for im in images:
        # GIF transparency is 1-bit, so flatten onto a solid background
        canvas = Image.new("RGBA", (width, height), background)
        canvas.alpha_composite(im, ((width - im.width) // 2, (height - im.height) // 2))
        frames.append(canvas.convert("RGB"))
    return frames


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Combine PNG frames into an animated GIF.")
    p.add_argument("frames", nargs="+", help="PNG files or glob patterns, used in the order given")
    p.add_argument("-o", "--output", type=Path,
                   help="output GIF (default: animation.gif next to the first frame)")
    p.add_argument("-d", "--duration", type=int, default=1500, help="milliseconds per frame (default: 1500)")
    p.add_argument("-l", "--loop", type=int, default=0,
                   help="0 = loop forever (default), N = play N+1 times, -1 = play once")
    p.add_argument("-b", "--background", default="white", help="background colour (default: white)")
    args = p.parse_args(argv)

    files = expand(args.frames)
    missing = [str(f) for f in files if not f.is_file()]
    if not files or missing:
        print("No frames found" if not files else "Not found: " + ", ".join(missing), file=sys.stderr)
        return 2

    output = args.output or files[0].parent / "animation.gif"
    frames = load_frames(files, args.background)
    loop = {} if args.loop < 0 else {"loop": args.loop}
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=args.duration, **loop)
    print(f"{len(frames)} frames -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
