#!/usr/bin/env python3
"""install_machines.py - put the book's machines where openMSX finds them.

    python3 install_machines.py [where the C-BIOS ROMs are]

The machines of this book are files in machines/. openMSX looks for machines
in the folder share/machines of your openMSX user folder, and for the ROMs a
machine needs in share/systemroms. This program copies the machines there, and
copies the C-BIOS ROMs they name, checking every ROM against the SHA-1 sum the
machine asks for, so that a wrong file is never copied.

The user folder is Documents\\openMSX on Windows and ~/.openMSX on Linux and
macOS, or the folder in the environment variable OPENMSX_HOME if it is set.

The ROMs are looked for in the folder or the zip file given on the command
line (cbios-0.29a.zip, as downloaded, will do), or else in the places where
openMSX and C-BIOS put them when they are installed.
"""
import hashlib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
USUAL = [
    "/usr/share/cbios",                                         # Debian, Ubuntu: package cbios
    "/usr/share/openmsx",                                       # Linux packages of openMSX
    "/opt/openMSX/share",                                       # openMSX's own Linux build
    "/Applications/openMSX.app/Contents/Resources/share",       # macOS
    r"C:\Program Files\openMSX\share",                          # Windows, installed
]


def user_folder():
    if os.environ.get("OPENMSX_HOME"):
        return Path(os.environ["OPENMSX_HOME"])
    if os.name == "nt":
        return Path.home() / "Documents" / "openMSX"
    return Path.home() / ".openMSX"


def wanted():
    """{sha1: file name} of every ROM the book's machines name"""
    out = {}
    for xml in sorted((HERE / "machines").glob("*.xml")):
        text = xml.read_text()
        for sha1, name in re.findall(r"<sha1>([0-9a-f]{40})</sha1>\s*<filename>([^<]+)</filename>", text):
            out[sha1] = name
    return out


def candidates(place):
    """(name, bytes) of every file in a folder, or in a zip file"""
    place = Path(place)
    if place.is_file() and zipfile.is_zipfile(place):
        with zipfile.ZipFile(place) as z:
            for info in z.infolist():
                if not info.is_dir() and info.file_size <= 1 << 20:
                    yield info.filename, z.read(info)
    elif place.is_dir():
        for p in place.rglob("*"):
            if p.is_file() and p.stat().st_size <= 1 << 20:
                yield str(p), p.read_bytes()


def main(argv):
    share = user_folder() / "share"
    places = argv[1:] or [p for p in USUAL if Path(p).exists()]
    need = wanted()
    found = {}
    for place in places:
        for name, data in candidates(place):
            sha1 = hashlib.sha1(data).hexdigest()
            if sha1 in need and sha1 not in found:
                found[sha1] = (name, data)
    (share / "machines").mkdir(parents=True, exist_ok=True)
    (share / "systemroms").mkdir(parents=True, exist_ok=True)
    for xml in sorted((HERE / "machines").glob("*.xml")):
        shutil.copy(xml, share / "machines" / xml.name)
        print(f"machine  {xml.name}")
    missing = 0
    for sha1, name in sorted(need.items(), key=lambda kv: kv[1]):
        if sha1 in found:
            (share / "systemroms" / name).write_bytes(found[sha1][1])
            print(f"ROM      {name:<24}sha1 {sha1[:12]}  ok")
        else:
            print(f"ROM      {name:<24}sha1 {sha1[:12]}  NOT FOUND")
            missing += 1
    print(f"into {share}")
    if missing:
        print(f"{missing} ROM(s) not found: give the folder or the zip file that holds C-BIOS")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
