#!/bin/sh
# build.sh - assemble the programs of Appendix D (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15). Each includes tables.inc.
set -e
cd "$(dirname "$0")"
n=0
for f in addr timep timec beam calls; do
    sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm"
    n=$((n + 1))
done
echo "appendix D: $n cartridges, $n listings"
