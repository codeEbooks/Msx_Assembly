#!/bin/sh
# build.sh - assemble the programs of Appendix B (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15).
set -e
cd "$(dirname "$0")"
for f in undoc hidden_1 hidden_2; do
    sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm"
done
echo "appendix B: 3 cartridges, 3 listings"
