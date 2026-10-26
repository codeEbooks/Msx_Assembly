#!/bin/sh
# build.sh -- assemble the programs of chapter 15, with --syntax=bFw: b and F
# as since chapter 8, and w, which makes every warning an error and stops the
# build (this chapter). fits.asm and big.asm are wrong on purpose, to show the
# warnings: they are assembled without the w.
cd "$(dirname "$0")"
for f in names macro rows picture rowwise cart8 cart32; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
sjasmplus --nologo --msg=err --syntax=bFw --lst=exprs.lst exprs.asm || exit 1
sjasmplus --nologo --msg=err --syntax=bF --lst=fits.lst fits.asm || exit 1
sjasmplus --nologo --msg=err --syntax=bF --sym=big.sym --lst=big.lst big.asm || exit 1
