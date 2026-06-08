# =============================================================
#  display_en.py — Driver + layout v4 ePaper 7.5" B V2 (BWR 800x480)
#  MicroPython on ESP32 Waveshare e-Paper Driver Board.
#
#  Phase 2c: layout overhaul based on HTML mockup
#  (black border, red bullets, sub-columns, boxed elements, small caps).
#
#  Required files on the board:
#    display.py
#    barlow_bold_56.py    (hero)
#    barlow_bold_40.py    (date title + PV now)
#    barlow_bold_28.py    (secondary numbers + kWh next-to-hero)
#    archivo_bold_13.py   (all small caps labels)
#
#  You can remove the legacy files:
#    barlow_bold_44.py, archivo_18.py, archivo_13.py
#
#  CITY_NAME below is the only place where the city label is set.
#  Change it to your own city.
# =============================================================

from machine import Pin, SPI
import framebuf, time, gc

PIN_CS, PIN_DC, PIN_RST, PIN_BUSY = 15, 27, 26, 25
PIN_SCK, PIN_MOSI = 13, 14
WIDTH, HEIGHT = 800, 480
BUFSZ = WIDTH * HEIGHT // 8

CITY_NAME = "CITYNAME"   # <- replace with your city, e.g. "BOSTON"



# ---------------------------------------------------------------
#  Pre-allocated framebuffer (anti-fragmentation)
#
#  The MicroPython heap fragments quickly after a few imports +
#  JSON parsing + WiFi. Result: a later bytearray(48000) call
#  fails ("memory allocation failed") even with 100+ KB free in
#  total — it just lacks 48 KB CONTIGUOUS.
#
#  The fix: reserve the buffer at boot, before everything else.
#  main.py calls preallocate_buffer() as its first line.
# ---------------------------------------------------------------
_BUF = None

def preallocate_buffer():
    """Reserve the 48 KB framebuffer while the heap is still
    contiguous. Call as early as possible in main.py."""
    global _BUF
    if _BUF is None:
        gc.collect()
        _BUF = bytearray(BUFSZ)
        gc.collect()
        print("Framebuffer 48 KB reserved, free mem:", gc.mem_free())


def _get_buf():
    """Return the pre-allocated buffer. Allocate if needed (fallback)."""
    if _BUF is None:
        preallocate_buffer()
    return _BUF


def free_buffer():
    """Free the 48 KB framebuffer. Call when rendering is no longer needed
    until the next reboot (typically after render_portal_screen in captive
    mode). Gives ~48 KB back to ESP-IDF for the WiFi/LWIP/DHCP buffers.
    Will be re-allocated automatically on next _get_buf() if needed."""
    global _BUF
    _BUF = None
    gc.collect()
    print("Framebuffer released, free mem:", gc.mem_free())


# ---------------------------------------------------------------
#  Low-level UC8179 driver
# ---------------------------------------------------------------
class EPD:
    def __init__(self):
        self.cs   = Pin(PIN_CS,   Pin.OUT, value=1)
        self.dc   = Pin(PIN_DC,   Pin.OUT, value=0)
        self.rst  = Pin(PIN_RST,  Pin.OUT, value=1)
        self.busy = Pin(PIN_BUSY, Pin.IN)
        self.spi  = SPI(2, baudrate=4_000_000, polarity=0, phase=0,
                        sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))

    def _reset(self):
        self.rst.value(1); time.sleep_ms(20)
        self.rst.value(0); time.sleep_ms(4)
        self.rst.value(1); time.sleep_ms(20)

    def _wait(self, label="busy"):
        t0 = time.ticks_ms()
        while self.busy.value() == 0:
            if time.ticks_diff(time.ticks_ms(), t0) > 30000:
                print("EPD: timeout on", label); return
            time.sleep_ms(20)

    def _cmd(self, c):
        self.dc.value(0); self.cs.value(0)
        self.spi.write(bytes([c])); self.cs.value(1)

    def _data(self, d):
        self.dc.value(1); self.cs.value(0)
        self.spi.write(bytes([d]) if isinstance(d, int) else d)
        self.cs.value(1)

    def init(self):
        self._reset()
        self._cmd(0x01); self._data(bytes([0x07, 0x07, 0x3F, 0x3F]))
        self._cmd(0x04); time.sleep_ms(100); self._wait("power on")
        self._cmd(0x00); self._data(0x0F)
        self._cmd(0x61); self._data(bytes([0x03, 0x20, 0x01, 0xE0]))
        self._cmd(0x15); self._data(0x00)
        self._cmd(0x50); self._data(bytes([0x11, 0x07]))
        self._cmd(0x60); self._data(0x22)

    def send_black(self, buf): self._cmd(0x10); self._data(buf)
    def send_red(self,   buf): self._cmd(0x13); self._data(buf)
    def refresh(self):         self._cmd(0x12); time.sleep_ms(100); self._wait("refresh")
    def sleep(self):
        self._cmd(0x02); self._wait("power off")
        self._cmd(0x07); self._data(0xA5)


# ---------------------------------------------------------------
#  Drawing layer
# ---------------------------------------------------------------
_TXT_PRO = "_TP"


def measure(font, s):
    total = 0
    for ch in s:
        try:
            _, _, w = font.get_ch(ch)
            total += w
        except Exception:
            total += font.max_width() // 2
    return total


class Display:
    BLACK = 1
    RED   = 2
    WHITE = 0

    def __init__(self, buf=None):
        self.epd = EPD()
        self._cmds = []
        self._buf = buf if buf is not None else bytearray(BUFSZ)

    def clear(self):
        self._cmds = []
        gc.collect()

    def _rec(self, color, fn, *args):
        self._cmds.append((color, fn, args))

    # Primitives
    def pixel(self, x, y, color):            self._rec(color, "pixel", x, y)
    def fill_rect(self, x, y, w, h, color):  self._rec(color, "fill_rect", x, y, w, h)
    def rect(self, x, y, w, h, color):       self._rec(color, "rect", x, y, w, h)
    def hline(self, x, y, w, color):         self._rec(color, "hline", x, y, w)
    def vline(self, x, y, h, color):         self._rec(color, "vline", x, y, h)
    def line(self, x1, y1, x2, y2, color):   self._rec(color, "line", x1, y1, x2, y2)
    def text_pro(self, s, x, y, font, color=BLACK):
        self._rec(color, _TXT_PRO, s, x, y, font)

    def _color_value(self, color, plane):
        if plane == "black":
            return 0 if color == self.BLACK else 1
        else:
            return 1 if color == self.RED else 0

    def _draw_text_pro(self, fb, s, x, y, font, v):
        cx = x
        for ch in s:
            try:
                data = font.get_ch(ch)
                if data is None:
                    cx += font.max_width() // 2
                    continue
                bitmap, ch_h, ch_w = data
            except Exception:
                cx += 4
                continue
            if v == 1:
                buf = bytearray(bitmap)
                cfb = framebuf.FrameBuffer(buf, ch_w, ch_h, framebuf.MONO_HLSB)
                fb.blit(cfb, cx, y, 0)
            else:
                bpr = (ch_w + 7) // 8
                for py in range(ch_h):
                    row_off = py * bpr
                    for byte_idx in range(bpr):
                        b = bitmap[row_off + byte_idx]
                        if b == 0:
                            continue
                        px_base = byte_idx << 3
                        for bit in range(8):
                            if px_base + bit >= ch_w:
                                break
                            if b & (0x80 >> bit):
                                fb.pixel(cx + px_base + bit, y + py, 0)
            cx += ch_w

    def _render_plane(self, fb, plane):
        for color, fn, args in self._cmds:
            v = self._color_value(color, plane)
            if fn == _TXT_PRO:
                s, x, y, font = args
                self._draw_text_pro(fb, s, x, y, font, v)
            else:
                getattr(fb, fn)(*args, v)

    def render(self):
        print("EPD: init...")
        self.epd.init()
        gc.collect()
        print("Free mem before render:", gc.mem_free())
        buf = self._buf
        fb  = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.MONO_HLSB)
        fb.fill(1)
        self._render_plane(fb, "black")
        print("EPD: sending black plane...")
        self.epd.send_black(buf)
        fb.fill(0)
        self._render_plane(fb, "red")
        print("EPD: sending red plane...")
        self.epd.send_red(buf)
        print("EPD: refresh (~20 s)...")
        self.epd.refresh()
        fb = None; gc.collect()
        print("EPD: deep sleep.")
        self.epd.sleep()


# ---------------------------------------------------------------
#  Layout: overhaul based on HTML mockup
# ---------------------------------------------------------------
DAYS_EN  = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MONTHS_EN = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
TZ_OFFSET = 2 * 3600


def _is_hp(hour):
    """Peak-hour tariff (peak/off-peak schedule):
       PEAK: 7-11 AM and 5-10 PM, **every day** (weekday and weekend identical)
       OFF-PEAK: the rest (10 PM - 7 AM and 11 AM - 5 PM)"""
    return (7 <= hour < 11) or (17 <= hour < 22)


def _fmt(x, decimals=1):
    """Format a number with the given decimals: 14.2 -> '14.2'."""
    return ("{:." + str(decimals) + "f}").format(x)


def _draw_wifi_icon(d, x, y, rssi):
    """Smartphone/laptop-style WiFi icon: center dot + 3 concentric arcs
    fanning out above it. Bounding box ~30x22 px.

    Approach: each arc is rendered as a thick polyline (3x3 squares placed
    every ~0.7 px along a 120° arc). Gives crisp curves with rounded ends,
    no pixel staircase.

    dBm thresholds:
      > -55 dBm: 3 arcs (excellent)
      -55 to -70: 2 arcs (good)
      -70 to -85: 1 arc  (weak)
      < -85     : none (just the dot)
    """
    if rssi is None:
        return
    BLACK = d.BLACK
    if   rssi > -55: bars = 3
    elif rssi > -70: bars = 2
    elif rssi > -85: bars = 1
    else:            bars = 0

    cx = x + 15
    cy = y + 18    # dot sits at the bottom of the bounding box

    # Solid center dot (5x5)
    d.fill_rect(cx - 2, cy - 2, 5, 5, BLACK)
    if bars == 0:
        return

    import math

    def stroke_arc(r, stroke):
        """Upper arc (210° → 330° = 120° sweep) drawn with overlapping squares."""
        n_steps = int(r * 3)        # ~0.7 px spacing, overlap guaranteed
        half = stroke // 2
        for i in range(n_steps + 1):
            t = math.radians(210 + 120 * i / n_steps)
            px = round(cx + r * math.cos(t))
            py = round(cy + r * math.sin(t))
            d.fill_rect(px - half, py - half, stroke, stroke, BLACK)

    if bars >= 1:
        stroke_arc(6, 2)
    if bars >= 2:
        stroke_arc(10, 2)
    if bars >= 3:
        stroke_arc(14, 2)


def _draw_dashboard(d, data, hourly, now, refresh_min, battery, F_HERO, F_BIG, F_MED, F_LAB):
    BLACK, RED, WHITE = d.BLACK, d.RED, d.WHITE
    MARGIN = 14
    BULLET = 10

    # ============ OUTER BORDER (rect + edge vlines for visibility) ============
    d.rect(0, 0, WIDTH, HEIGHT, BLACK)
    d.rect(1, 1, WIDTH - 2, HEIGHT - 2, BLACK)
    # Safety: vertical line 2 px from the right edge (in case the panel clips)
    d.vline(WIDTH - 3, 0, HEIGHT, BLACK)
    d.vline(2,         0, HEIGHT, BLACK)

    # ============ HEADER (y 8..75) ============
    # Date (left)
    date_s = "{}. {} {}".format(DAYS_EN[now[6]], now[2], MONTHS_EN[now[1] - 1])
    d.text_pro(date_s, MARGIN, 10, F_BIG, BLACK)
    d.text_pro(CITY_NAME, MARGIN, 56, F_LAB, BLACK)

    # PV now (right, red)
    pv_s = "{} kW".format(_fmt(data.get("pv_now_kw", 0), 1))
    pv_w = measure(F_BIG, pv_s)
    d.text_pro(pv_s, WIDTH - MARGIN - pv_w, 10, F_BIG, RED)
    sub_s = "PV PRODUCTION - NOW"
    sub_w = measure(F_LAB, sub_s)
    d.text_pro(sub_s, WIDTH - MARGIN - sub_w, 56, F_LAB, BLACK)

    d.hline(MARGIN, 78, WIDTH - 2 * MARGIN, BLACK)

    # ============ LEFT COLUMN (x 14..474) ============
    LX = MARGIN
    LW = 460

    # --- SOLAR PRODUCTION title + HR ---
    sy = 90
    d.fill_rect(LX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("SOLAR PRODUCTION", LX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(LX, sy + 19, LW, BLACK)

    # Hero split into 2 sub-columns
    SUB = LW // 2

    # Left sub: PRODUCED TODAY
    d.text_pro("PRODUCED TODAY", LX, sy + 28, F_LAB, BLACK)
    pv_today = _fmt(data.get("pv_today", 0), 1)
    d.text_pro(pv_today, LX, sy + 45, F_HERO, BLACK)
    pvt_w = measure(F_HERO, pv_today)
    d.text_pro("kWh", LX + pvt_w + 8, sy + 75, F_MED, BLACK)

    # Right sub: GRID EXPORT (red)
    SX = LX + SUB
    d.text_pro("GRID EXPORT", SX, sy + 28, F_LAB, RED)
    inj_s = _fmt(data.get("inj_today", 0), 1)
    d.text_pro(inj_s, SX, sy + 45, F_HERO, RED)
    inj_w = measure(F_HERO, inj_s)
    d.text_pro("kWh", SX + inj_w + 8, sy + 75, F_MED, RED)

    # --- Self-use / Export bar ---
    bar_y = sy + 145
    bar_h = 26
    auto_pct = data.get("auto_pct", 0)
    inj_pct  = data.get("inj_pct", 0)
    d.text_pro("SELF-USED {} %".format(auto_pct), LX, bar_y - 16, F_LAB, BLACK)
    inj_lbl = "EXPORTED {} %".format(inj_pct)
    d.text_pro(inj_lbl, LX + LW - measure(F_LAB, inj_lbl), bar_y - 16, F_LAB, RED)
    auto_w = int(LW * auto_pct / 100)
    d.fill_rect(LX, bar_y, auto_w, bar_h, BLACK)
    d.fill_rect(LX + auto_w, bar_y, LW - auto_w, bar_h, RED)

    # --- Histogram: title + legend ---
    hist_t_y = bar_y + bar_h + 18
    d.text_pro("HOURLY PRODUCTION", LX, hist_t_y, F_LAB, BLACK)
    # Peak/off-peak legend, right-aligned
    leg_x = LX + LW
    leg_x -= measure(F_LAB, "HC")
    d.text_pro("HC", leg_x, hist_t_y, F_LAB, BLACK)
    leg_x -= 4 + BULLET
    d.fill_rect(leg_x, hist_t_y + 2, BULLET, BULLET, BLACK)
    leg_x -= 14
    leg_x -= measure(F_LAB, "HP")
    d.text_pro("HP", leg_x, hist_t_y, F_LAB, BLACK)
    leg_x -= 4 + BULLET
    d.fill_rect(leg_x, hist_t_y + 2, BULLET, BULLET, RED)

    # --- Bars: rolling 12h window in 30-min slots (24 bars) ---
    hist_y0 = hist_t_y + 18
    hist_h  = 125
    hist_base = hist_y0 + hist_h
    n_bars = 24
    bucket_min = 30
    gap_pix = 2
    bar_pix = (LW - (n_bars - 1) * gap_pix) // n_bars
    padded = list(hourly or [])
    while len(padded) < n_bars: padded.append(0.0)
    padded = padded[:n_bars]
    mx = max(padded) if padded and max(padded) > 0 else 1.0
    # Window aligned on the current 30-min slot (consistent with hourly_buckets)
    current_h = now[3]
    current_m = now[4]
    end_slot_min   = (current_h * 60 + current_m) // bucket_min * bucket_min + bucket_min
    window_start_min = end_slot_min - n_bars * bucket_min   # may be negative (yesterday)
    for i, val in enumerate(padded):
        x = LX + i * (bar_pix + gap_pix)
        h_px = int(val / mx * hist_h)
        if h_px < 1 and val > 0: h_px = 1
        hour_of_bucket = ((window_start_min + i * bucket_min) // 60) % 24
        col = RED if _is_hp(hour_of_bucket) else BLACK
        if h_px > 0:
            d.fill_rect(x, hist_base - h_px, bar_pix, h_px, col)
    d.hline(LX, hist_base + 1, LW, BLACK)
    # Hourly labels: 4 labels every 3h at indexes (0, 6, 12, 18)
    axis_y = hist_base + 5
    label_indices = (0, 6, 12, 18)
    for idx in label_indices:
        h = ((window_start_min + idx * bucket_min) // 60) % 24
        lbl = "{}h".format(h)
        x_c = LX + idx * (bar_pix + gap_pix) + bar_pix // 2
        d.text_pro(lbl, x_c - measure(F_LAB, lbl) // 2, axis_y, F_LAB, BLACK)

    # ============ VERTICAL SEPARATOR between columns ============
    # Between left column end (x=474) and right column start (x=510)
    d.vline(492, 85, 360, BLACK)

    # ============ RIGHT COLUMN (x 510..786) ============
    RX = 510
    RW = WIDTH - RX - MARGIN
    # 60/40 split to give more room to USED TODAY vs COST TODAY
    R_SUB = int(RW * 0.6)

    # --- GRID ---
    sy = 90
    d.fill_rect(RX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("GRID", RX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(RX, sy + 19, RW, BLACK)

    d.text_pro("USED TODAY", RX, sy + 28, F_LAB, BLACK)
    conso_s = _fmt(data.get("conso_day", 0), 1)
    d.text_pro(conso_s, RX, sy + 42, F_MED, BLACK)
    d.text_pro("kWh", RX + measure(F_MED, conso_s) + 4, sy + 56, F_LAB, BLACK)

    d.text_pro("COST TODAY", RX + R_SUB, sy + 28, F_LAB, BLACK)
    cost_s = _fmt(data.get("cost_day", 0), 2)
    d.text_pro(cost_s, RX + R_SUB, sy + 42, F_MED, BLACK)
    d.text_pro("EUR", RX + R_SUB + measure(F_MED, cost_s) + 4, sy + 56, F_LAB, BLACK)

    # --- CURRENT RATE box ---
    tar_y = sy + 90
    tar_h = 36
    d.rect(RX, tar_y, RW, tar_h, BLACK)
    d.text_pro("CURRENT RATE", RX + 10, tar_y + 12, F_LAB, BLACK)
    tarif = data.get("tarif", "?")
    tarif_color = RED if tarif == "HP" else BLACK
    tw = measure(F_MED, tarif)
    d.text_pro(tarif, RX + RW - tw - 12, tar_y + 4, F_MED, tarif_color)

    # --- TEMPERATURES (50/50 split for balance) ---
    sy = 255
    R_SUB_T = RW // 2
    d.fill_rect(RX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("TEMPERATURES", RX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(RX, sy + 19, RW, BLACK)

    d.text_pro("OUTDOOR", RX, sy + 28, F_LAB, RED)
    te_s = _fmt(data.get("t_ext", 0), 1)
    d.text_pro(te_s, RX, sy + 42, F_MED, RED)
    d.text_pro("°C", RX + measure(F_MED, te_s) + 2, sy + 42, F_MED, RED)

    d.text_pro("LAUNDRY", RX + R_SUB_T, sy + 28, F_LAB, BLACK)
    tb_s = _fmt(data.get("t_buand", 0), 1)
    d.text_pro(tb_s, RX + R_SUB_T, sy + 42, F_MED, BLACK)
    d.text_pro("°C", RX + R_SUB_T + measure(F_MED, tb_s) + 2, sy + 42, F_MED, BLACK)

    # --- SURPLUS AVAILABLE box (more visible: F_MED centered) ---
    surp_y = 350
    surp_h = 95
    d.rect(RX, surp_y, RW, surp_h, BLACK)
    d.fill_rect(RX + 10, surp_y + 12, BULLET, BULLET, RED)
    d.text_pro("SURPLUS", RX + 10 + BULLET + 8, surp_y + 9, F_LAB, BLACK)

    if data.get("surplus_ok") and data.get("surplus_kw", 0) > 0.05:
        sw_s = _fmt(data["surplus_kw"], 1) + " kW"
        sw_w = measure(F_BIG, sw_s)
        d.text_pro(sw_s, RX + (RW - sw_w) // 2, surp_y + 28, F_BIG, RED)
        msg2 = "AVAILABLE"
        mw = measure(F_LAB, msg2)
        d.text_pro(msg2, RX + (RW - mw) // 2, surp_y + 74, F_LAB, RED)
    else:
        msg = "INSUFFICIENT"
        mw = measure(F_BIG, msg)
        d.text_pro(msg, RX + (RW - mw) // 2, surp_y + 38, F_BIG, BLACK)

    # ============ FOOTER ============
    foot_y = 456
    d.hline(MARGIN, foot_y - 8, WIDTH - 2 * MARGIN, BLACK)

    # Battery block (optional) on the left, before SUNRISE/SUNSET
    # The whole icon (body + tip + fill + text) turns RED when CHARGING
    # (USB-C plugged in) OR when battery is low (<20%). Otherwise BLACK.
    foot_l_x = MARGIN
    if battery is not None:
        pct       = battery.get("percent", 0)
        charging  = battery.get("charging", False)
        is_low    = pct < 20
        # Single color for the whole battery block
        icon_color = RED if (charging or is_low) else BLACK
        # Battery icon: 20x10 body + 2x4 tip, vertically aligned with the text
        bx, by = MARGIN, foot_y + 2
        bw, bh = 20, 10
        d.rect(bx, by, bw, bh, icon_color)
        d.fill_rect(bx + bw, by + 3, 2, bh - 6, icon_color)
        fill_w = max(0, min(bw - 2, int((bw - 2) * pct / 100 + 0.5)))
        if fill_w > 0:
            d.fill_rect(bx + 1, by + 1, fill_w, bh - 2, icon_color)
        # Percentage text (same color as the icon for visual consistency)
        text_x = bx + bw + 4
        pct_s = "{}%".format(pct)
        d.text_pro(pct_s, text_x, foot_y, F_LAB, icon_color)
        text_x += measure(F_LAB, pct_s)
        foot_l_x = text_x + 12        # visual separator before SUNRISE

    foot_l = "SUNRISE {}  -  SUNSET {}".format(
        data.get("lever", "--:--"), data.get("coucher", "--:--"))
    d.text_pro(foot_l, foot_l_x, foot_y, F_LAB, BLACK)
    foot_r = "HOME ASSISTANT  -  UPD {:02d}/{:02d}  -  {:02d}:{:02d}  (refresh {} min)".format(
        now[2], now[1], now[3], now[4], refresh_min)
    foot_r_w = measure(F_LAB, foot_r)
    # WiFi RSSI icon at the far right, just after the (refresh X min) text
    rssi = data.get("wifi_rssi")
    icon_offset = (30 + 8) if rssi is not None else 0   # 30 px icon + 8 px gap
    d.text_pro(foot_r, WIDTH - MARGIN - foot_r_w - icon_offset, foot_y, F_LAB, BLACK)
    if rssi is not None:
        _draw_wifi_icon(d, WIDTH - MARGIN - 30, foot_y - 6, rssi)


def _free_fonts(*names):
    """Free the font modules after a render, otherwise they squat
    ~15-20 KB of RAM until the next reset. Critical for the captive
    portal where we render the screen BEFORE activating the AP — without
    freeing them, the AP can OOM due to missing WiFi buffers."""
    import sys
    for n in names:
        if n in sys.modules:
            del sys.modules[n]
    gc.collect()


def render_dashboard(data, hourly, refresh_min=10, battery=None):
    gc.collect()
    print("Free mem at render start:", gc.mem_free())
    buf = _get_buf()
    gc.collect()
    print("Buffer ready, free mem:", gc.mem_free())
    d = Display(buf=buf)
    import barlow_bold_56 as F_HERO
    import barlow_bold_40 as F_BIG
    import barlow_bold_28 as F_MED
    import archivo_bold_13 as F_LAB
    gc.collect()
    print("Fonts loaded, free mem:", gc.mem_free())
    d.clear()
    now = time.localtime(time.time() + TZ_OFFSET)
    _draw_dashboard(d, data, hourly, now, refresh_min, battery, F_HERO, F_BIG, F_MED, F_LAB)
    print("Recorded commands:", len(d._cmds))
    d.render()
    _free_fonts("barlow_bold_56", "barlow_bold_40",
                "barlow_bold_28", "archivo_bold_13")
    print("Free mem end:", gc.mem_free())


# ---------------------------------------------------------------
#  Status screens (captive portal, network errors, etc.)
# ---------------------------------------------------------------
def render_status(title, lines, color_title=None):
    """Generic status screen:
       title       : str, large centered line at the top (Barlow Bold 40)
       lines       : list of (label, value) tuples
                     label = small explanatory line (Archivo Bold 13)
                     value = highlighted value (Archivo Bold 24)
       color_title : Display.BLACK or Display.RED (default BLACK)
    """
    gc.collect()
    print("Render status:", title)
    buf = _get_buf()
    gc.collect()
    d = Display(buf=buf)
    import barlow_bold_40 as F_TITLE
    import archivo_bold_24 as F_VAL
    import archivo_bold_13 as F_LAB
    gc.collect()

    BLACK, RED = d.BLACK, d.RED
    col_t = color_title if color_title is not None else BLACK

    # Border
    d.rect(0, 0, WIDTH, HEIGHT, BLACK)
    d.rect(1, 1, WIDTH - 2, HEIGHT - 2, BLACK)

    # Centered title
    tw = measure(F_TITLE, title)
    d.text_pro(title, (WIDTH - tw) // 2, 60, F_TITLE, col_t)
    d.hline(80, 118, WIDTH - 160, BLACK)

    # Lines block: vertically centered but capped at y=200
    # (otherwise a single line gets lost in the middle of the void)
    n = len(lines)
    block_h = 65
    total_h = n * block_h
    avail_top = 140
    avail_bot = HEIGHT - 30
    center_y0 = avail_top + (avail_bot - avail_top - total_h) // 2
    y0 = min(center_y0, 200)

    for i, (label, value) in enumerate(lines):
        y = y0 + i * block_h
        lw = measure(F_LAB, label)
        d.text_pro(label, (WIDTH - lw) // 2, y, F_LAB, BLACK)
        vw = measure(F_VAL, value)
        d.text_pro(value, (WIDTH - vw) // 2, y + 22, F_VAL, BLACK)

    d.render()
    _free_fonts("barlow_bold_40", "archivo_bold_24", "archivo_bold_13")
    print("Render status done, free mem:", gc.mem_free())


def render_portal_screen(ssid, password, ip="192.168.4.1"):
    """Display WiFi setup info while the captive portal is running.
    If password is empty ("" or None), the PASSWORD line is omitted
    (open network).
    Frees the framebuffer after rendering — the portal runs until reboot,
    we no longer need the panel, and ESP-IDF needs this RAM for the
    DHCP server (otherwise the phone won't get an IP)."""
    lines = [("CONNECT TO WIFI:", ssid)]
    if password:
        lines.append(("PASSWORD:", password))
    lines.append(("THEN OPEN IN A BROWSER:", "http://" + ip))
    render_status("WIFI SETUP", lines)
    free_buffer()


def render_error(title, message, retry_min=2):
    """Display an error screen (red title + message + retry delay)."""
    lines = [("DETAIL:", message)]
    if retry_min > 0:
        unit = "MINUTE" if retry_min == 1 else "MINUTES"
        lines.append(("NEXT ATTEMPT IN:", "{} {}".format(retry_min, unit)))
    render_status(title, lines, color_title=Display.RED)


def demo_dashboard():
    mock_data = {
        "pv_today":   14.2, "pv_now_kw":  2.4,
        "inj_today":  6.8,  "conso_day":  7.3,
        "cost_day":   2.14, "surplus_kw": 2.1,
        "surplus_ok": True, "tarif":      "HP",
        "t_ext":      8.5,  "t_buand":    17.8,
        "lever":      "05:42", "coucher": "21:38",
        "inj_pct":    48,   "auto_pct":   52,
        "wifi_rssi":  -62,
    }
    mock_hourly = [0.05, 0.08, 0.12, 0.18, 0.30, 0.48, 0.62, 0.85,
                   0.95, 1.10, 1.20, 1.30, 1.40, 1.42, 1.30, 1.18,
                   1.00, 0.80, 0.55, 0.35, 0.20, 0.10, 0.05, 0.02]
    mock_battery = {"percent": 73, "voltage": 3.85, "charging": True}
    render_dashboard(mock_data, mock_hourly, refresh_min=10, battery=mock_battery)


if __name__ == "__main__":
    demo_dashboard()
