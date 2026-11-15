"""Check a visual review pack before a reviewer sees it (DIRECTOR-WORK 2.3.0, F1 + F5).

Review packs went out that could not show the defect, or showed one that was not there: frames sampled every 8th frame
of a motion whose key phase lasts 4 (the contact was never in the pack); a camera whose subject left the frame half way;
a "glove close-up" that did not contain the glove; file names that told the blind reviewer which image was the new
version (`_v3`, `_fix`, `_after`); a render setting (motion blur, a lossy format, a lower resolution) that made a smear
the reviewer called a defect; a pack README written from memory that listed files the pack did not hold.

  pack_check.py check  PACK [--leak-regex REGEX] [--min-part-fraction 0.02] [--margin 0]
  pack_check.py readme PACK [--out README.md]

PACK is a folder with manifest.json (schema review-pack-v1), written by the script that renders the pack:
  {"schema": "review-pack-v1", "fps": 30, "sampled_frames": [40, 42, 44], "events": {"contact": 44},
   "min_phase_frames": 4, "period_frames": null,
   "images": [{"file": "img/cam_a_0044.png", "camera": "cam_a", "frame": 44, "subject_bbox": [x0, y0, x1, y1],
               "part": "glove", "part_bbox": [x0, y0, x1, y1]}],
   "render": {"motion_blur": false, "resolution_percent": 100, "file_format": "PNG", "dof": false},
   "reference_render": {...the settings of the accepted reference, compared key by key...}}
  bboxes are pixel boxes of the subject / part projected by the renderer (not guessed from the picture).

check (F1):
  sampling    every event frame must be sampled or have a sample within one frame; the largest step between samples
              must be at most half of min_phase_frames (a phase shorter than two steps can fall between samples);
              a uniform step that is a multiple of period_frames samples one phase only (aliasing): FAIL
  in frame    per camera per frame, subject_bbox inside the image (width / height read from the PNG header; --margin
              pixels allowed outside); a missing subject_bbox is FAIL
  close-ups   an image with "part" needs a part_bbox inside the image and covering at least --min-part-fraction of it
  names       no file name in the pack may carry a version or verdict code (--leak-regex; default: v3, r2, rev1,
              round2, set1, cand, before, after, fix, final, pass, fail, old, new, best, baseline as separate tokens)
  files       every manifest image exists; every image in the pack is in the manifest
check (F5):
  render      settings known to make false defects must be neutral: motion_blur / dof false, resolution_percent 100,
              a lossless file_format (PNG, EXR, TIFF); every key of reference_render must have the same value in render
              (a different color transform or sample count is a different picture, not a defect)
  README      when PACK/README.md exists, it must list exactly the files the pack holds (write it with `readme`)
readme: writes PACK/README.md from the objects really in the pack: each file with size and, for PNG, width x height,
  and per manifest image its camera and frame. It holds no verdicts or scores (the blind layer stays blind).

Prints one line per finding and a last line `PACK_CHECK: PASS|FAIL images=n findings=n`. Exit 0 PASS, 1 FAIL, 2 the
pack cannot be read. Only reads, except `readme`.
"""
import argparse
import json
import pathlib
import re
import struct
import sys

SCHEMA = "review-pack-v1"
LEAK = (r"(?i)(?:^|[_\-. ])(v\d+|r\d+[a-z]?|rev\d+|round\d+|set\d+|cand(?:idate)?|before|after|fix(?:ed)?|final|pass|"
        r"fail|old|new|best|baseline)(?=$|[_\-. ])")
LOSSLESS = {"PNG", "OPEN_EXR", "EXR", "OPEN_EXR_MULTILAYER", "TIFF", "TIF"}
IMAGE = {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".webp"}
SKIP = {"manifest.json", "README.md"}


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def pack_files(pack):
    return sorted(p.relative_to(pack).as_posix() for p in pack.rglob("*") if p.is_file())


def load(pack):
    data = json.loads((pack / "manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("images"), list):
        raise ValueError(f"manifest.json is not a {SCHEMA} manifest with an images list")
    return data


def sampling(data):
    out = []
    frames = sorted({int(f) for f in data.get("sampled_frames") or [i.get("frame") for i in data["images"]
                                                                       if isinstance(i.get("frame"), int)]})
    if not frames:
        return ["sampling: no sampled frames"]
    for name, frame in (data.get("events") or {}).items():
        if not any(abs(f - int(frame)) <= 1 for f in frames):
            near = min(frames, key=lambda f: abs(f - int(frame)))
            out.append(f"sampling: event {name} at frame {frame} is not sampled (nearest sample {near})")
    steps = [b - a for a, b in zip(frames, frames[1:])]
    shortest = data.get("min_phase_frames")
    if steps and shortest and max(steps) * 2 > shortest:
        out.append(f"sampling: largest step {max(steps)} frames > half of the shortest phase ({shortest} frames): "
                   "a phase can fall between samples")
    period = data.get("period_frames")
    if period and steps and len(set(steps)) == 1 and steps[0] % int(period) == 0:
        out.append(f"sampling: uniform step {steps[0]} is a multiple of the motion period {period}: every sample shows "
                   "the same phase (aliasing)")
    return out


def inside(box, width, height, margin):
    x0, y0, x1, y1 = box
    return x0 >= -margin and y0 >= -margin and x1 <= width + margin and y1 <= height + margin and x1 > x0 and y1 > y0


def image_findings(pack, data, margin, min_fraction):
    out = []
    for item in data["images"]:
        name = item.get("file") or "?"
        path = pack / name
        where = f"{name} ({item.get('camera', '?')} frame {item.get('frame', '?')})"
        if not path.is_file():
            out.append(f"files: {name} is in the manifest but not in the pack")
            continue
        size = png_size(path) if path.suffix.lower() == ".png" else None
        width, height = size or (item.get("width"), item.get("height"))
        if not width or not height:
            out.append(f"in frame: {where}: no image size (not a PNG and no width / height in the manifest)")
            continue
        box = item.get("subject_bbox")
        if not (isinstance(box, list) and len(box) == 4):
            out.append(f"in frame: {where}: no subject_bbox (the renderer's projection of the subject)")
        elif not inside(box, width, height, margin):
            out.append(f"in frame: {where}: subject {box} leaves the {width}x{height} image")
        if item.get("part"):
            part = item.get("part_bbox")
            if not (isinstance(part, list) and len(part) == 4):
                out.append(f"close-up: {where}: part {item['part']} has no part_bbox")
            elif not inside(part, width, height, 0):
                out.append(f"close-up: {where}: part {item['part']} {part} is not inside the image")
            elif (part[2] - part[0]) * (part[3] - part[1]) < min_fraction * width * height:
                share = (part[2] - part[0]) * (part[3] - part[1]) / (width * height) * 100
                out.append(f"close-up: {where}: part {item['part']} covers {share:.1f} % of the image "
                           f"(< {min_fraction * 100:g} %): not a close-up of it")
    return out


def render_findings(data):
    out, render = [], data.get("render")
    if not isinstance(render, dict):
        return ["render: no render settings in the manifest (cannot show the pack is free of render-made defects)"]
    for key in ("motion_blur", "dof"):
        if render.get(key):
            out.append(f"render: {key} is on: it smears or blurs what the reviewer judges")
    if render.get("resolution_percent", 100) != 100:
        out.append(f"render: resolution_percent {render['resolution_percent']} (not 100): detail is lost")
    fmt = str(render.get("file_format", "")).upper()
    if fmt and fmt not in LOSSLESS:
        out.append(f"render: file_format {fmt} is lossy: compression artefacts look like defects")
    for key, want in (data.get("reference_render") or {}).items():
        if render.get(key) != want:
            out.append(f"render: {key} = {render.get(key)!r}, the reference used {want!r}")
    return out


def readme_text(pack, data):
    images = {i.get("file"): i for i in data["images"]}
    lines = ["# Review pack contents", "", "Generated by pack_check.py readme from the files in this folder.", "",
             "| file | bytes | size | camera | frame |", "|---|---|---|---|---|"]
    for name in pack_files(pack):
        if name == "README.md":
            continue
        path = pack / name
        size = png_size(path) if path.suffix.lower() == ".png" else None
        item = images.get(name, {})
        lines.append(f"| {name} | {path.stat().st_size} | {f'{size[0]}x{size[1]}' if size else ''} | "
                     f"{item.get('camera', '')} | {item.get('frame', '')} |")
    return "\n".join(lines) + "\n"


def readme_findings(pack):
    path = pack / "README.md"
    if not path.is_file():
        return []
    listed = set(re.findall(r"^\|\s*([^|\s][^|]*?)\s*\|", path.read_text(encoding="utf-8-sig"), re.M)) - {"file", "---"}
    actual = set(pack_files(pack)) - {"README.md"}
    out = [f"README: lists {n}, which the pack does not hold" for n in sorted(listed - actual)]
    out += [f"README: does not list {n} (regenerate it: pack_check.py readme)" for n in sorted(actual - listed)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("check", "readme"))
    ap.add_argument("pack", help="the review pack folder (with manifest.json)")
    ap.add_argument("--leak-regex", default=LEAK, help="file-name pattern that leaks a version or verdict")
    ap.add_argument("--min-part-fraction", type=float, default=0.02, help="close-up part's minimum share of the image")
    ap.add_argument("--margin", type=float, default=0.0, help="pixels a subject may extend outside the image")
    ap.add_argument("--out", help="readme: write here instead of PACK/README.md")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    pack = pathlib.Path(a.pack).resolve()
    try:
        data = load(pack)
        leak = re.compile(a.leak_regex)
    except (OSError, ValueError, re.error) as error:
        print(f"PACK_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    if a.action == "readme":
        target = pathlib.Path(a.out) if a.out else pack / "README.md"
        target.write_text(readme_text(pack, data), encoding="utf-8")
        print(f"README written: {target.as_posix()} ({len(pack_files(pack))} file(s) in the pack)")
        return 0
    findings = sampling(data) + image_findings(pack, data, a.margin, a.min_part_fraction) + render_findings(data)
    listed = {i.get("file") for i in data["images"]}
    for name in pack_files(pack):
        if leak.search(pathlib.PurePosixPath(name).stem) or any(leak.search(part) for part in name.split("/")[:-1]):
            findings.append(f"names: {name} carries a version or verdict code (a blind reviewer must not read it)")
        if pathlib.PurePosixPath(name).suffix.lower() in IMAGE and name not in listed and name not in SKIP:
            findings.append(f"files: {name} is in the pack but not in the manifest")
    findings += readme_findings(pack)
    for f in findings:
        print(f"FAIL {f}")
    print(f"PACK_CHECK: {'FAIL' if findings else 'PASS'} images={len(data['images'])} findings={len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"PACK_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
