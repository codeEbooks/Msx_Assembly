#!/bin/sh
# build.sh - assemble the program of Appendix F (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15).
set -e
cd "$(dirname "$0")"
n=0
for f in calls; do
    sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm"
    n=$((n + 1))
done
echo "appendix F: $n cartridge, $n listing"
