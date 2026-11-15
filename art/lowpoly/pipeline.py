"""Render jobs: what each model module asks for, and the code that runs them across processes.

A model module (``art/lowpoly/models/<name>.py``) lists what it wants rendered:

    JOBS = [
        Job("nova_bust", (512, 512), bust_scene),                       # a still
        Job("nova_spin", (192, 192), spin_scene, frames=24, fps=12),    # an animation
    ]

``scene`` is a top-level function ``scene(i, n) -> lowpoly.render.Scene`` (frame ``i`` of ``n``;
a still gets ``(0, 1)``). Every module in ``models/`` is discovered automatically, so adding a
character never means editing this file or ``build.py``.

Stills are written as ``<name>.png``, animation frames as ``<name>_00.png``, ``<name>_01.png``...
and everything is described in ``manifest.json`` next to them (docs/SPEC_V2.md section 5).
"""
from __future__ import annotations

import importlib
import json
import multiprocessing
import os
import re
import time
from pathlib import Path

from . import png
from .render import Image, contact_sheet, render

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT_DIR = REPO / "assets" / "renders"
MANIFEST_VERSION = 1


class Job:
    """One still or one animation.

    ``name``: output base name (letters, digits, underscore). ``size``: ``(width, height)`` in
    pixels. ``scene``: ``scene(i, n) -> Scene``, a module-level function (it is looked up by name
    in worker processes). ``frames``: 1 for a still. ``fps`` is only recorded in the manifest.
    ``ss``: supersampling factor.
    """

    def __init__(self, name, size, scene, frames=1, fps=12, ss=3):
        if not re.match(r"^[a-z0-9_]+$", name):
            raise ValueError("job names are lower-case letters, digits and underscores: %r" % (name,))
        self.name = name
        self.size = (int(size[0]), int(size[1]))
        self.scene = scene
        self.frames = int(frames)
        self.fps = int(fps)
        self.ss = int(ss)

    @property
    def animated(self):
        return self.frames > 1

    def filenames(self, frames=None):
        n = self.frames if frames is None else frames
        if n <= 1:
            return [self.name + ".png"]
        return ["%s_%02d.png" % (self.name, i) for i in range(n)]


def discover():
    """Import every ``models/*.py`` and return ``[(module_name, Job), ...]`` in a stable order."""
    found = []
    seen = {}
    for path in sorted((HERE / "models").glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = importlib.import_module("lowpoly.models." + path.stem)
        for job in getattr(module, "JOBS", []):
            if job.name in seen:
                raise ValueError("render job %r is defined in both models/%s.py and models/%s.py"
                                 % (job.name, seen[job.name], path.stem))
            seen[job.name] = path.stem
            found.append((path.stem, job))
    return found


def select(jobs, only=None):
    """Filter ``discover()`` output: ``only`` names are job names or model module names."""
    if not only:
        return list(jobs)
    wanted = set(only)
    picked = [(mod, job) for mod, job in jobs if job.name in wanted or mod in wanted]
    known = set(job.name for _m, job in jobs) | set(mod for mod, _j in jobs)
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError("no render job or model module called: %s (known: %s)"
                         % (", ".join(unknown), ", ".join(sorted(known))))
    return picked


def _find_job(module_name, job_name):
    module = importlib.import_module("lowpoly.models." + module_name)
    for job in module.JOBS:
        if job.name == job_name:
            return job
    raise KeyError(job_name)


def _render_task(task):
    """Worker: render one frame and write it. Runs in a child process, so it only takes plain data."""
    module_name, job_name, index, total, out_path, ss = task
    job = _find_job(module_name, job_name)
    t0 = time.perf_counter()
    scene = job.scene(index, total)
    image = render(scene, job.size[0], job.size[1], ss=ss)
    size = image.save(out_path)
    return (job_name, index, time.perf_counter() - t0, size, scene.triangle_count())


def load_manifest(out_dir=None):
    path = Path(out_dir or OUT_DIR) / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("renders"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": MANIFEST_VERSION, "renders": {}}


def manifest_entry(job, frames=None):
    n = job.frames if frames is None else frames
    if n <= 1:
        return {"file": job.name + ".png", "size": [job.size[0], job.size[1]]}
    return {"frames": job.filenames(n), "fps": job.fps, "size": [job.size[0], job.size[1]]}


def run(only=None, frames=None, out_dir=None, processes=None, ss=None, sheet_dir=None, log=print):
    """Render the selected jobs and update ``manifest.json``. Returns a per-job report dict.

    ``frames`` overrides the frame count of every animation (the loop still covers one full
    cycle); frames beyond the new count are removed so the folder always matches the manifest.
    ``processes`` defaults to the CPU count (at most 8); 1 renders in this process.
    """
    out = Path(out_dir or OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    jobs = select(discover(), only)
    tasks = []
    counts = {}
    for mod, job in jobs:
        n = job.frames if (frames is None or not job.animated) else max(2, int(frames))
        counts[job.name] = n
        for i, fname in enumerate(job.filenames(n)):
            tasks.append((mod, job.name, i, n, str(out / fname), ss or job.ss))
    if processes is None:
        processes = max(1, min(8, os.cpu_count() or 1))
    processes = max(1, min(processes, len(tasks) or 1))

    report = {job.name: {"module": mod, "frames": counts[job.name], "size": list(job.size), "seconds": 0.0,
                         "bytes": 0, "triangles": 0} for mod, job in jobs}
    t0 = time.perf_counter()
    if processes == 1:
        results = map(_render_task, tasks)
        pool = None
    else:
        pool = multiprocessing.Pool(processes)
        results = pool.imap_unordered(_render_task, tasks)
    try:
        for name, _index, seconds, size, triangles in results:
            r = report[name]
            r["seconds"] += seconds
            r["bytes"] += size
            r["triangles"] = max(r["triangles"], triangles)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    wall = time.perf_counter() - t0

    manifest = load_manifest(out)
    manifest["version"] = MANIFEST_VERSION
    for _mod, job in jobs:
        n = counts[job.name]
        manifest["renders"][job.name] = manifest_entry(job, n)
        if job.animated:        # drop frames left over from a longer run of the same animation
            pattern = re.compile(r"^%s_(\d{2,})\.png$" % re.escape(job.name))
            for path in out.iterdir():
                m = pattern.match(path.name)
                if m and int(m.group(1)) >= n:
                    path.unlink()
    manifest["renders"] = dict(sorted(manifest["renders"].items()))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if sheet_dir:
        sheets = Path(sheet_dir)
        sheets.mkdir(parents=True, exist_ok=True)
        for _mod, job in jobs:
            images = [Image(*png.read_png(out / f)) for f in job.filenames(counts[job.name])]
            columns = 1 if len(images) == 1 else min(6, len(images))
            contact_sheet(images, columns=columns, background="#ffd9ec").save(sheets / (job.name + "_sheet.png"))

    if log:
        for name in sorted(report):
            r = report[name]
            log("%-14s %2d frame(s) %4dx%-4d %5d tris %7.2fs cpu %8d bytes"
                % (name, r["frames"], r["size"][0], r["size"][1], r["triangles"], r["seconds"], r["bytes"]))
        log("%d file(s) in %.1fs wall on %d process(es) -> %s" % (len(tasks), wall, processes, out))
    report["_wall"] = wall
    report["_processes"] = processes
    return report
