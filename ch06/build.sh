#!/bin/sh
# build.sh -- assemble the two programs chapter 6 watches in the debugger
cd "$(dirname "$0")"
for f in border biosway; do
  sjasmplus --nologo --msg=err --sym=$f.sym $f.asm || exit 1
done
