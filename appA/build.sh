#!/bin/sh
# build.sh - assemble the programs of Appendix A (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15).
set -e
cd "$(dirname "$0")"
for f in times flags; do
    sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm"
done
echo "appendix A: 2 cartridges, 2 listings"
