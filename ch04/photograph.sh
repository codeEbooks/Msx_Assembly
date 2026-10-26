#!/bin/sh
# photograph.sh -- film check.rom on the book's machine and keep frame 60,
# the way every figure in this book was taken
cd "$(dirname "$0")"
python3 ../tools/msxcap.py check.rom 60 --out shots
