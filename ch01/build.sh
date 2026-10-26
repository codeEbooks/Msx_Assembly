#!/bin/sh
# build.sh -- assemble every program of chapter 1 into its .rom cartridge
cd "$(dirname "$0")"
for f in *.asm; do
  sjasmplus --nologo --msg=err --sym="${f%.asm}.sym" "$f" || exit 1
done
