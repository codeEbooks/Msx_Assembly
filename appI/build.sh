#!/bin/sh
# build.sh -- assemble appendix I's programs into their .rom cartridges
cd "$(dirname "$0")"
for f in prices flags bit4100 clash120 y208_0 beam_244 solutions; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym="$f.sym" --lst="$f.lst" "$f.asm" || exit 1
done
