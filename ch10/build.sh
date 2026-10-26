#!/bin/sh
# build.sh -- assemble the programs of chapter 10, with --syntax=bF (chapter 8)
cd "$(dirname "$0")"
for f in logic sprite bits cost rotate shifts mul friction scroll mirror div bcd; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
