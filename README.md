# MSX Assembly

The programs, figures and measurements of the book

**MSX Assembly** — *Z80 code on the MSX1, measured on the machine: two complete games, and every screen photographed*
by Aravind J. Deshmukh and Henry Radclyffe, first edition 2026, ISBN 9798164813321.

The book's page: www.codeandbooksweb.com/books/msx-assembly

Every program in the book is here, in a folder named after its chapter or
appendix, with the files the captions name. The book prints the paths of
580 files, and every one of them is in this repository.
`verify.py` assembles every program again and compares the result with the
cartridges the book was photographed from, byte for byte.

## Getting started

1. Install the sjasmplus assembler (1.24.0), the openMSX emulator and C-BIOS.
   Chapter 4 does it on Linux, Windows and macOS; on Debian and Ubuntu,
   `sh setup_linux.sh` in the folder `ch04` does all of it.
2. Put the book's machines where openMSX finds them:
   `python3 install_machines.py`, followed by the folder or the zip file that
   holds the C-BIOS ROMs (`/usr/share/cbios` on Debian and Ubuntu,
   `cbios-0.29a.zip` as downloaded). It copies the twelve machines of `machines`
   and the ROMs they need into openMSX's user folder, checking every ROM's
   SHA-1.
3. Run a cartridge on the book's machine, from its folder:
   `openmsx -machine MSXBOOK_EU16 -carta border.rom` in `ch05`, chapter 5's
   first program.
4. Check your assembler against the book's: `python3 verify.py`.

## What is where

| | |
| --- | --- |
| `ch01` … `ch56` | one folder for each chapter, holding everything the chapter prints: the sources, the cartridges that were photographed, the generator that wrote the sources, the meas script and its results, the figures, and in `captures` the frames they were cut from |
| `appA` … `appI` | the appendices' programs and measurements; `appI` holds the programs some of the Workshop answers needed |
| `tools` | what the chapters share: `tools/msxcap.py`, which filmed every figure in the book; `tools/asmparts.py`, the pieces every generator builds its programs from; and the helpers that drive openMSX's debugger and console, read text back from a capture, and run a chapter's measurements again with another openMSX |
| `machines` | the book's twelve machines for openMSX, and `machines/LICENCE-C-BIOS.txt` |
| `install_machines.py` | puts the machines where openMSX finds them |
| `verify.py` | the checker |
| `msx.inc` | the names of the ports and addresses the book's programs use; every folder whose programs include it has a copy, byte for byte the same (64 copies) |
| `bios.inc` | the names of the BIOS's entries and variables; it grew with the chapters, and each of the 43 folders that include it keeps the copy its programs were built with. Every name has the same value in every copy, and this one has all 69 |
| `LICENCE` | the MIT licence |

9,458 files in all:

| what | files | how many |
| --- | --- | ---: |
| assembly sources | `.asm` | 434 |
| files they include: msx.inc, bios.inc, music, a font, a picture, tables | `.inc` | 121 |
| cartridges, as openMSX loads them | `.rom` | 413 |
| chapter 56's EPROM images, and other binary data | `.bin` | 12 |
| the assembler's listings | `.lst` | 311 |
| the assembler's symbol tables | `.sym` | 414 |
| figures and the frames they were cut from | `.png` | 7,174 |
| the sound chip's channels as openMSX recorded them, and two tapes | `.wav` | 57 |
| Python: generators, measuring scripts, figures, tools | `.py` | 297 |
| shell scripts: building, setting up, photographing | `.sh` | 66 |
| measurements | `.json` | 65 |
| what the tools printed, the games' release notes, the C-BIOS notice | `.txt` | 42 |
| the keys pressed in a run, frame by frame, as openMSX commands | `.events` | 26 |
| openMSX scripts: breakpoints the measuring scripts set | `.tcl` | 5 |
| machine definitions for openMSX | `.xml` | 12 |

and 9 more: this file, `LICENCE`, `.gitignore`, `.gitattributes`,
chapter 56's two cartridge labels as PDF, chapter 50's tape (`ch50/screen.cas`) and
disk (`ch50/screen.dsk`), and an openMSX replay (`ch34/define.omr`).

## Checking: verify.py

```
python3 verify.py          every folder
python3 verify.py ch04     one folder
```

It needs Python 3 and sjasmplus on the PATH. With the book's sjasmplus it
begins and ends:

```
sjasmplus 1.24.0 (the book: 1.24.0)
  ...
422 files, 0 different
```

If a file differs, verify.py names it. Chapter 56's EPROM images are not
assembled: verify.py makes them again from the two games' cartridges and
compares them too.

## Since chapter 4

Chapter 4 shows verify.py and install_machines.py as they ran when the
repository held the first chapters. With the whole book:

- verify.py checks 422 files, where chapter 4 shows 40;
- install_machines.py installs twelve machines, where chapter 4 shows six. The
  other six change one thing of the book's machine for one chapter:

| machine | used in | what is different |
| --- | --- | --- |
| `MSXBOOK_EU16B` | chapter 55 | With its RAM switched on as a real MSX1's: 128 bytes of $00, then 128 of $FF, over and over, as openMSX's description of the Philips VG 8010 has it. |
| `MSXBOOK_EU16E` | chapter 38 | With a slot expander in cartridge slot 1, the cartridge in its second socket, secondary slot 1-1: to see a cartridge find a slot that is not primary. |
| `MSXBOOK_EU16G` | chapter 34 | With a keyboard that ghosts as one without diodes does: three keys at three corners of a rectangle in the matrix read as four. |
| `MSXBOOK_EU16P` | chapter 36 | With a PSG whose two ports follow bits 6 and 7 of register 7, as a PSG chip of its own does: port A an output, or port B an input, when register 7 says so. |
| `MSXBOOK_EU16S` | chapter 55 | With its RAM switched on as a real MSX1's: $FF, $00, over and over, as openMSX's description of the Canon V-20 has it. |
| `MSXBOOK_EU16X` | chapter 38 | With slot 3 expanded and its 16 KB of RAM in secondary slot 3-2: to see a program find RAM that is not in a primary slot. |

Chapter 4 also says that the repository's files are all in small letters.
That holds for every file a source names, and for the chapters' sources and
cartridges; but the appendices' folders and files carry their letter in
capitals (`appA`, `appA/measA.py`), the machines their names
(`machines/MSXBOOK_EU16.xml`), and a few frames in `captures` the name of the
machine they were taken on (in `ch01`, `ch51`, `ch55`).

## Measuring again

Every chapter's folder has a meas script that runs the programs in openMSX
again, films them and recounts every number the chapter prints. The scripts
need Linux, openMSX 19.1 and C-BIOS 0.29a, and on Ubuntu 24.04 these
packages:

| what | package | for |
| --- | --- | --- |
| openMSX and C-BIOS | `openmsx`, `cbios` | every chapter |
| Pillow, for Python | `python3-pil` | every chapter |
| ffmpeg, which turns openMSX's film into frames, and Xvfb, the screen nobody sees | `ffmpeg`, `xvfb` | every chapter |
| NumPy, for Python | `python3-numpy` | chapters 36, 37, 46 and 49, appendices D and E |
| mtools | `mtools` | chapter 50's disk |
| xdotool | `xdotool` | chapter 35 and appendix C, which press keys on openMSX's window |
| img2pdf | `img2pdf` | chapter 56's labels as PDF |

`ch04/setup_linux.sh` installs the first three lines and builds sjasmplus.

Run a script in its folder, `python3 meas18.py`, or one section of it,
`python3 meas18.py answers`: the top of each script lists its sections. One
after the other, the 62 scripts of the chapters and of appendices A to G took
about 2 hours on a machine of two cores, before this repository was
published; all of them ran to the end, from a fresh clone. What they
changed, and why:

- Several scripts compare other builds of openMSX (17.0 to 21.0), listed in
  the environment variable `OPENMSX_BUILDS`. Without it they measure with
  your openMSX alone and write `"skipped"` where the book's results hold the
  comparison; that is all that changes in their json.
- Three counts are taken over the whole repository, so they give the number
  of today rather than of the chapter: chapter 7's sources that assemble the
  same with `--syntax=F` (the book: 56; now 391), chapter 38's programs and
  the bytes they keep in RAM (the book: 318 programs of chapters 1 to 37; now
  381), and chapter 55's cartridges (the book: 381 in chapters 1 to 54; now
  384).
- `ch34/define.omr`, the replay of chapter 34, is written again with the
  date of the run.

Chapter 4's `ch04/meas04.py` also runs `ch04/setup_linux.sh` in a scratch home
folder, which installs packages with sudo, and compares other builds
(openMSX 20.0 and 21.0, openMSX and sjasmplus for Windows under Wine, older
releases of sjasmplus); the top of the script says how it finds them. The
scripts of appendices H and I run the chapters' scripts again, in a copy of
the repository.

## Line endings

`.gitattributes` turns Git's line-ending conversion off, so every file
arrives exactly as it was checked.

## The BIOS, and the machines

The programs in this book were run and photographed on C-BIOS, a BIOS
written from scratch for emulators and given away under a BSD licence, which
comes with openMSX. The BIOS of a real MSX belongs to its maker: no system ROM
is included in this repository. install_machines.py copies the C-BIOS ROMs
from your own C-BIOS or openMSX.

The machine definitions in `machines` are C-BIOS's own configurations for
openMSX, changed in the lines that make them the book's machines, and they keep
C-BIOS's licence notice: see `machines/LICENCE-C-BIOS.txt`.

## Licence

MIT, for everything in this repository: the code, and the figures and the
recordings it made. See `LICENCE`. The machine definitions keep C-BIOS's
notice as well, as above.

## Trademarks

MSX is a trademark of its owner. Zilog, Z80, Texas Instruments, Yamaha,
General Instrument, Microsoft, ASCII, and all other product, company, or
service names mentioned belong to their respective owners. Their use here is
editorial and descriptive. This book and this repository are independent
publications and are not authorised by, affiliated with, or sponsored by any
of them.
