#!/usr/bin/env python3
"""Render the low-poly art into assets/renders/ (standard library only).

    python3 art/lowpoly/build.py                    everything
    python3 art/lowpoly/build.py --only nova        one model module (or one job: --only nova_spin)
    python3 art/lowpoly/build.py --frames 8         shorter animations (quick look; changes the manifest)
    python3 art/lowpoly/build.py --list             what would be rendered
    python3 art/lowpoly/build.py --out /tmp/x --sheet /tmp/x     render elsewhere, plus contact sheets

See docs/ART_LOWPOLY.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # so "lowpoly" is importable

from lowpoly import pipeline  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the papercraft low-poly art (pure Python).")
    ap.add_argument("--only", action="append", metavar="NAME",
                    help="a model module (nova, props) or a job name (nova_spin); repeat or comma-separate")
    ap.add_argument("--frames", type=int, metavar="N", help="frames per animation instead of each job's own count")
    ap.add_argument("--out", metavar="DIR", help="output folder (default: assets/renders)")
    ap.add_argument("--jobs", "-j", type=int, metavar="N", help="worker processes (default: CPU count, at most 8)")
    ap.add_argument("--ss", type=int, metavar="N", help="supersampling factor instead of each job's own (3)")
    ap.add_argument("--sheet", metavar="DIR", help="also write a contact sheet per job into DIR (for checking)")
    ap.add_argument("--list", action="store_true", help="list the render jobs and exit")
    args = ap.parse_args(argv)

    only = []
    for item in args.only or []:
        only += [s.strip() for s in item.split(",") if s.strip()]
    try:
        if args.list:
            for mod, job in pipeline.select(pipeline.discover(), only):
                kind = "%d frames @ %d fps" % (job.frames, job.fps) if job.animated else "still"
                print("%-14s %-8s %4dx%-4d %s" % (job.name, mod, job.size[0], job.size[1], kind))
            return 0
        pipeline.run(only=only, frames=args.frames, out_dir=args.out, processes=args.jobs, ss=args.ss,
                     sheet_dir=args.sheet)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
