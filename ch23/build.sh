#!/bin/sh
# build.sh -- assemble the programs of chapter 23, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in places hill clash sprite oneink plain steps mono backdrop blocks zero; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
