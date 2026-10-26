"""versions.py -- does another build of openMSX give a chapter's answers?

A chapter's meas script is run again in a copy of the repository, with
another openMSX, and every number and every capture it makes is compared with
the book's. Captures are compared twice: whole, and inside the columns the VDP
draws (meas.DRAWN), where every version of openMSX is meant to agree; chapter 4
explains the difference.

The builds are listed in the file named by the environment variable
OPENMSX_BUILDS, one per line: "label<TAB>openmsx binary<TAB>its share folder".
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

import meas

REPO = Path(__file__).resolve().parent.parent


def leaves(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}/{i}")
    else:
        yield path, obj


def builds():
    """[(label, binary, share)] from OPENMSX_BUILDS, or [] if it is not set"""
    path = os.environ.get("OPENMSX_BUILDS")
    if not path:
        return []
    return [tuple(l.split("\t")) for l in Path(path).read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def drawn(png):
    """the pixels of a capture inside the drawn columns"""
    im = Image.open(png).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, im.height)).tobytes()


def rerun(env, chapters, sections=None, keep=40, values=False):
    """run measNN.py of each chapter in a copy of the repository with env;
    sections, if given, are the only sections run and compared; the first
    KEEP values that differ are named (all of them if KEEP is None), with
    the book's value and the new one if VALUES"""
    tmp = Path(tempfile.mkdtemp(prefix="rerun_"))
    try:
        shutil.copytree(REPO, tmp / "repo", ignore=shutil.ignore_patterns("__pycache__", "shots"))
        res = {"values": 0, "same_values": 0, "captures": 0, "same_captures": 0,
               "same_in_drawn": 0, "failed": [], "different": []}
        for ch in chapters:
            d = tmp / "repo" / ch
            name = f"meas{ch[2:]}" if ch.startswith("ch") else f"meas{ch[3:]}"   # appA: measA
            shutil.rmtree(d / "captures", ignore_errors=True)
            (d / f"{name}.json").unlink()
            r = subprocess.run([sys.executable, f"{name}.py", *(sections or [])], cwd=d, env=env,
                               capture_output=True, text=True, timeout=3000)
            if r.returncode:
                text = (r.stdout + r.stderr).strip()
                res["failed"].append(f"{ch}: {text.splitlines()[-1] if text else r.returncode}")
                continue
            book = dict(leaves(json.loads((REPO / ch / f"{name}.json").read_text())))
            if sections:
                book = {k: v for k, v in book.items() if k.split("/")[1] in sections}
            new = dict(leaves(json.loads((d / f"{name}.json").read_text())))
            res["values"] += len(book)
            res["same_values"] += sum(1 for k, v in book.items() if new.get(k) == v)
            diff = [(f"{ch}{k}", v, new.get(k)) for k, v in book.items() if new.get(k) != v][:keep]
            if values:
                res.setdefault("values_of", {}).update({k: [v, n] for k, v, n in diff})
            res["different"] += [k for k, _, _ in diff]
            for png in sorted((REPO / ch / "captures").glob("*.png")):
                res["captures"] += 1
                other = d / "captures" / png.name
                if other.exists():
                    res["same_captures"] += other.read_bytes() == png.read_bytes()
                    res["same_in_drawn"] += drawn(other) == drawn(png)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def every_build(chapters, sections=None, log=print, keep=40, values=False):
    """rerun() with every build of OPENMSX_BUILDS"""
    out = {}
    for label, binary, share in builds():
        env = dict(os.environ, MSXCAP_OPENMSX=binary, OPENMSX_SYSTEM_DATA=share)
        v = subprocess.run([binary, "-v"], env=env, capture_output=True, text=True)
        r = rerun(env, chapters, sections, keep, values)
        r["version"] = (v.stdout + v.stderr).strip().splitlines()[0]
        r["sha256"] = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        out[label] = r
        log(f"  {label}: {r['same_values']}/{r['values']} values, {r['same_captures']}/"
            f"{r['captures']} captures ({r['same_in_drawn']} in the drawn columns), "
            f"failed {r['failed']}")
    return out
