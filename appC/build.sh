#!/bin/sh
# build.sh - assemble the programs of Appendix C (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15).
set -e
cd "$(dirname "$0")"
n=0
for f in ports vdp psg ppi sound keys; do
    sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm"
    n=$((n + 1))
done
echo "appendix C: $n cartridges, $n listings"
