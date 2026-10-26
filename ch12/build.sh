#!/bin/sh
# build.sh -- assemble the programs of chapter 12, with --syntax=bF (chapter 8)
cd "$(dirname "$0")"
for f in stack calls lost cost keep frame say where irq top fill fillall fast popsum; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
