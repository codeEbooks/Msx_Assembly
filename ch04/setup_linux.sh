#!/bin/sh
# setup_linux.sh -- the tools of this book on Debian, Ubuntu and the systems
# built on them. Run it in the folder ch04 of the repository:  sh setup_linux.sh
set -e
SUDO=$(command -v sudo || true)
# openMSX, C-BIOS, a compiler for sjasmplus, and what the measuring scripts use
$SUDO apt-get update -q
$SUDO apt-get install -y -q openmsx cbios build-essential curl \
  python3 python3-pil ffmpeg xvfb
# sjasmplus 1.24.0, built from its released source
v=1.24.0
url=https://github.com/z00m128/sjasmplus/releases/download
[ -f sjasmplus-$v-src.tar.xz ] || curl -LO $url/v$v/sjasmplus-$v-src.tar.xz
tmp=$(mktemp -d)
tar -xJf sjasmplus-$v-src.tar.xz -C "$tmp"
make -C "$tmp/sjasmplus-$v" -j"$(nproc)" >/dev/null
$SUDO make -C "$tmp/sjasmplus-$v" install >/dev/null
rm -rf "$tmp"
# the book's machines, and the C-BIOS ROMs they need, into ~/.openMSX/share
python3 ../install_machines.py /usr/share/cbios
sjasmplus --version 2>&1 | head -1
openmsx -v | head -1
