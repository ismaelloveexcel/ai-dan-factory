#!/usr/bin/env python3
"""
generate_promo_video.py - Free MP4 promo video renderer using MoviePy.

Reads a JSON concept file and renders a short animated MP4 with:
- Gradient background
- Text scenes with fade transitions
- Branded accent color
"""
import argparse
import json
import os
import sys

try:
    from moviepy.editor import (
        ColorClip,
        CompositeVideoClip,
        TextClip,
        concatenate_videoclips,
    )
except ImportError:
    print("MoviePy not installed. Run: pip install moviepy==1.0.3", file=sys.stderr)
    sys.exit(1)


def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def make_scene(
    text: str,
    sub: str,
    duration: float,
    bg_rgb: tuple,
    accent_rgb: tuple,
    size: tuple = (720, 720),
) -> CompositeVideoClip:
    bg = ColorClip(size=size, color=bg_rgb, duration=duration)
    clips = [bg]

    if text:
        try:
            main_text = (
                TextClip(
                    text,
                    fontsize=60,
                    color="white",
                    font="DejaVu-Sans-Bold",
                    method="caption",
                    size=(size[0] - 80, None),
                    align="center",
                )
                .set_duration(duration)
                .set_position("center")
                .crossfadein(0.4)
            )
            clips.append(main_text)
        except Exception as e:
            print(f"  TextClip warning: {e}", file=sys.stderr)

    if sub:
        try:
            sub_text = (
                TextClip(
                    sub,
                    fontsize=34,
                    color=f"rgb({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]})",
                    font="DejaVu-Sans",
                    method="caption",
                    size=(size[0] - 120, None),
                    align="center",
                )
                .set_duration(duration)
                .set_position(("center", int(size[1] * 0.72)))
                .crossfadein(0.5)
            )
            clips.append(sub_text)
        except Exception as e:
            print(f"  SubText warning: {e}", file=sys.stderr)

    return CompositeVideoClip(clips, size=size).set_duration(duration)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True, help="Path to JSON concept file")
    parser.add_argument("--output", default="artifacts/promo_video.mp4")
    args = parser.parse_args()

    with open(args.brief) as f:
        concept = json.load(f)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    product = concept.get("product", "Product")
    tagline = concept.get("tagline", "")
    hook = concept.get("hook", f"Introducing {product}")
    problem = concept.get("problem", "")
    solution = concept.get("solution", tagline)
    cta = concept.get("cta", "Try it free")
    url = concept.get("url", "")
    hashtags = " ".join(f"#{h}" for h in concept.get("hashtags", [])[:4])
    bg_rgb = hex_to_rgb(concept.get("bg_color", "#1a0533"))
    accent_rgb = hex_to_rgb(concept.get("accent_color", "#7c3aed"))

    print(f"Rendering video for: {product}")

    scenes = []
    scenes.append(make_scene(hook, "AI-DAN Factory", 3.0, bg_rgb, accent_rgb))
    if problem:
        scenes.append(make_scene(problem, "", 3.0, bg_rgb, accent_rgb))
    scenes.append(make_scene(solution or tagline, product, 4.0, bg_rgb, accent_rgb))
    scenes.append(make_scene(cta, url or hashtags, 3.0, accent_rgb, bg_rgb))

    video = concatenate_videoclips(scenes, method="compose")

    print(f"Writing {args.output} ({video.duration:.1f}s)...")
    video.write_videofile(
        args.output,
        fps=24,
        codec="libx264",
        audio=False,
        logger=None,
    )
    print(f"✓ Video saved: {args.output}")


if __name__ == "__main__":
    main()
