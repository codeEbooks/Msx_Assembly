#!/bin/sh
# build.sh -- assemble the programs of chapter 8. From this chapter on every
# program is assembled with --syntax=bF: parentheses round a whole operand
# mean memory, and made-up instructions are refused (chapter 7). paren.asm,
# the chapter's trap, is assembled the old way, into a listing.
cd "$(dirname "$0")"
for f in modes sixteen records selfmod copy4 ldai; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
sjasmplus --nologo --msg=err --lst=paren.lst paren.asm || exit 1
