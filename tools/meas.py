"""meas.py -- the geometry of the capture, measured once on day 1.

Every later measurement reads pixels through these numbers. Sources: hello.rom
(the paper and the border), the border clock (gen_border.py, meas_border.py),
and the frame flag of counter.rom. 50 Hz machine (MSXBOOK_EU16) unless said.
"""
CAPTURE_W, CAPTURE_H = 320, 240        # screenshot -raw and the recorded film
PAPER_X0, PAPER_Y0 = 32, 24            # top-left pixel of the paper in the capture
PAPER_W, PAPER_H = 256, 192
BORDER_PIXELS = CAPTURE_W * CAPTURE_H - PAPER_W * PAPER_H      # 27 648

T_PER_LINE = 228                       # measured: +228 T moves the stripe one row down
PX_PER_T = 1.5                         # measured: +16 T moves the stripe end 24 pixels
PX_PER_LINE = 342                      # 228 x 1.5: +228 T = +342 in raster order
T_PER_FRAME = {"MSXBOOK_EU16": 71364,  # measured: 313 lines
               "MSXBOOK_JP16": 59736}  # measured: 262 lines
LINES_PER_FRAME = {"MSXBOOK_EU16": 313, "MSXBOOK_JP16": 262}

# openMSX numbers the lines of a frame from 0 (VDP_cycle_in_frame // 1368).
# On the 50 Hz machine, capture row r is frame line r + 45, so the paper
# (rows 24-215) is frame lines 69-260, and the interrupt handler starts in
# frame line 261, 66-70 T-states into the first line under the paper.
FRAME_LINE_OF_ROW0 = {"MSXBOOK_EU16": 45}
PAPER_FRAME_LINE0 = {"MSXBOOK_EU16": 69, "MSXBOOK_JP16": 42}   # JP: from the handler line (234 - 192)

# A register write made by OUT (C),r that starts at T-state t of a line shows
# at capture x = ceil(1.5 t - 16): the colour changes at the next whole pixel.
OUT_C_X_OFFSET = -16

# The columns the VDP draws: 13 of border, 256 of paper, 15 of border. Outside
# them openMSX 20.0 and later repeat the colour of column 19 or 302, where 19.1
# and earlier show a change of colour where it happens (chapter 4, edge.asm).
# Captures are compared between versions inside these columns.
DRAWN = (19, 302)


def paper(x, y):
    """capture coordinates of paper pixel (x, y)"""
    return PAPER_X0 + x, PAPER_Y0 + y


def raster(x, y):
    """position of capture pixel (x, y) in raster order, in pixels of a full line"""
    return y * PX_PER_LINE + x
