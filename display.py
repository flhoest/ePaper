# =============================================================
#  display.py — Pilote + layout v4 ePaper 7,5" B V2 (BWR 800x480)
#  MicroPython sur ESP32 Waveshare e-Paper Driver Board.
#
#  Phase 2c : refonte layout selon la maquette HTML
#  (bordure noire, puces rouges, sub-colonnes, encadrés, small caps).
#
#  Fichiers requis sur la carte :
#    display.py
#    barlow_bold_56.py    (hero)
#    barlow_bold_40.py    (date title + PV maintenant)
#    barlow_bold_28.py    (nombres secondaires + kWh next-to-hero)
#    archivo_bold_13.py   (tous les labels small caps)
# =============================================================

from machine import Pin, SPI
import framebuf, time, gc

PIN_CS, PIN_DC, PIN_RST, PIN_BUSY = 15, 27, 26, 25
PIN_SCK, PIN_MOSI = 13, 14
WIDTH, HEIGHT = 800, 480
BUFSZ = WIDTH * HEIGHT // 8


# ---------------------------------------------------------------
#  Framebuffer pré-alloué (anti-fragmentation)
#
#  Le heap MicroPython se fragmente vite après quelques imports +
#  parsing JSON + WiFi. Résultat : un bytearray(48000) plus tard
#  échoue ("memory allocation failed") même avec 100+ Ko libres au
#  total — il manque juste 48 Ko CONTIGUS.
#
#  La parade : réserver le buffer dès le boot, avant tout le reste.
#  main.py appelle preallocate_buffer() en première ligne.
# ---------------------------------------------------------------
_BUF = None

def preallocate_buffer():
    """Réserve les 48 Ko du framebuffer pendant que le heap est encore
    contigu. À appeler au plus tôt dans main.py."""
    global _BUF
    if _BUF is None:
        gc.collect()
        _BUF = bytearray(BUFSZ)
        gc.collect()
        print("Framebuffer 48 Ko réservé, mem libre :", gc.mem_free())


def _get_buf():
    """Renvoie le buffer pré-alloué. L'alloue si besoin (fallback)."""
    if _BUF is None:
        preallocate_buffer()
    return _BUF


def free_buffer():
    """Libère le framebuffer 48 Ko. À appeler quand on n'a plus besoin
    de rendu jusqu'au prochain reboot (typiquement après render_portal_screen
    en mode captif). Donne ~48 Ko en plus à ESP-IDF pour les buffers
    WiFi/LWIP/DHCP. Sera re-alloué auto au prochain _get_buf() si besoin."""
    global _BUF
    _BUF = None
    gc.collect()
    print("Framebuffer libéré, mem libre :", gc.mem_free())


# ---------------------------------------------------------------
#  Pilote bas niveau UC8179
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
                print("EPD: timeout sur", label); return
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
#  Couche dessin
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
        print("Mem libre avant render :", gc.mem_free())
        buf = self._buf
        fb  = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.MONO_HLSB)
        fb.fill(1)
        self._render_plane(fb, "black")
        print("EPD: envoi du plan noir...")
        self.epd.send_black(buf)
        fb.fill(0)
        self._render_plane(fb, "red")
        print("EPD: envoi du plan rouge...")
        self.epd.send_red(buf)
        print("EPD: refresh (~20 s)...")
        self.epd.refresh()
        fb = None; gc.collect()
        print("EPD: deep sleep.")
        self.epd.sleep()


# ---------------------------------------------------------------
#  Layout : refonte selon la maquette HTML
# ---------------------------------------------------------------
DAYS_FR  = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"]
MONTHS_FR = ["JAN", "FEV", "MAR", "AVR", "MAI", "JUN",
             "JUL", "AOU", "SEP", "OCT", "NOV", "DEC"]
TZ_OFFSET = 2 * 3600


def _is_hp(hour):
    """Tarif Heure Pleine ORES (grille 2026, depuis le 1er janvier) :
       HP : 7h-11h et 17h-22h, **tous les jours** (semaine et weekend identiques)
       HC : le reste (22h-7h et 11h-17h)"""
    return (7 <= hour < 11) or (17 <= hour < 22)


def _fr(x, decimals=1):
    """Nombre à la française : 14.2 -> '14,2'."""
    return ("{:." + str(decimals) + "f}").format(x).replace(".", ",")


def _draw_wifi_icon(d, x, y, rssi):
    """Icone WiFi style smartphone/laptop : point central + 3 arcs concentriques
    en éventail au-dessus. Bounding box ~30x22 px.

    Technique : chaque arc est tracé comme une polyligne épaisse (carrés 3x3
    placés tous les ~0.7 px le long d'un arc 120°). Donne des courbes nettes
    avec extrémités arrondies, sans escaliers de pixels.

    Seuils dBm:
      > -55 dBm : 3 arcs (excellent)
      -55 a -70 : 2 arcs (bon)
      -70 a -85 : 1 arc  (faible)
      < -85     : aucun (juste le point)
    """
    if rssi is None:
        return
    BLACK = d.BLACK
    if   rssi > -55: bars = 3
    elif rssi > -70: bars = 2
    elif rssi > -85: bars = 1
    else:            bars = 0

    cx = x + 15
    cy = y + 18    # le point est en bas du BB

    # Point central charnu (5x5)
    d.fill_rect(cx - 2, cy - 2, 5, 5, BLACK)
    if bars == 0:
        return

    import math

    def stroke_arc(r, stroke):
        """Arc supérieur (210° → 330° = 120° d'arc) tracé par carrés chevauchants."""
        n_steps = int(r * 3)        # ~0.7 px d'espacement, overlap garanti
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

    # ============ BORDURE EXTÉRIEURE (rect + vlines aux bords pour assurer la visibilité) ============
    d.rect(0, 0, WIDTH, HEIGHT, BLACK)
    d.rect(1, 1, WIDTH - 2, HEIGHT - 2, BLACK)
    # Assurance : un trait vertical à 2 px du bord droit (au cas où la dalle clipperait)
    d.vline(WIDTH - 3, 0, HEIGHT, BLACK)
    d.vline(2,         0, HEIGHT, BLACK)

    # ============ HEADER (y 8..75) ============
    # Date (gauche)
    date_s = "{}. {} {}".format(DAYS_FR[now[6]], now[2], MONTHS_FR[now[1] - 1])
    d.text_pro(date_s, MARGIN, 10, F_BIG, BLACK)
    d.text_pro("CERFONTAINE", MARGIN, 56, F_LAB, BLACK)

    # PV maintenant (droite, rouge)
    pv_s = "{} kW".format(_fr(data.get("pv_now_kw", 0), 1))
    pv_w = measure(F_BIG, pv_s)
    d.text_pro(pv_s, WIDTH - MARGIN - pv_w, 10, F_BIG, RED)
    sub_s = "PRODUCTION PV - MAINTENANT"
    sub_w = measure(F_LAB, sub_s)
    d.text_pro(sub_s, WIDTH - MARGIN - sub_w, 56, F_LAB, BLACK)

    d.hline(MARGIN, 78, WIDTH - 2 * MARGIN, BLACK)

    # ============ COLONNE GAUCHE (x 14..474) ============
    LX = MARGIN
    LW = 460

    # --- Titre PRODUCTION SOLAIRE + HR ---
    sy = 90
    d.fill_rect(LX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("PRODUCTION SOLAIRE", LX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(LX, sy + 19, LW, BLACK)

    # Hero en 2 sub-colonnes
    SUB = LW // 2

    # Sub gauche : PRODUIT AUJOURD'HUI
    d.text_pro("PRODUIT AUJOURD'HUI", LX, sy + 28, F_LAB, BLACK)
    pv_today = _fr(data.get("pv_today", 0), 1)
    d.text_pro(pv_today, LX, sy + 45, F_HERO, BLACK)
    pvt_w = measure(F_HERO, pv_today)
    d.text_pro("kWh", LX + pvt_w + 8, sy + 75, F_MED, BLACK)

    # Sub droite : INJECTÉ RÉSEAU (rouge)
    SX = LX + SUB
    d.text_pro("INJECTÉ RÉSEAU", SX, sy + 28, F_LAB, RED)
    inj_s = _fr(data.get("inj_today", 0), 1)
    d.text_pro(inj_s, SX, sy + 45, F_HERO, RED)
    inj_w = measure(F_HERO, inj_s)
    d.text_pro("kWh", SX + inj_w + 8, sy + 75, F_MED, RED)

    # --- Bar Auto/Inj ---
    bar_y = sy + 145
    bar_h = 26
    auto_pct = data.get("auto_pct", 0)
    inj_pct  = data.get("inj_pct", 0)
    d.text_pro("AUTOCONSOMME {} %".format(auto_pct), LX, bar_y - 16, F_LAB, BLACK)
    inj_lbl = "INJECTE {} %".format(inj_pct)
    d.text_pro(inj_lbl, LX + LW - measure(F_LAB, inj_lbl), bar_y - 16, F_LAB, RED)
    auto_w = int(LW * auto_pct / 100)
    d.fill_rect(LX, bar_y, auto_w, bar_h, BLACK)
    d.fill_rect(LX + auto_w, bar_y, LW - auto_w, bar_h, RED)

    # --- Histogramme : titre + légende ---
    hist_t_y = bar_y + bar_h + 18
    d.text_pro("PRODUCTION HORAIRE", LX, hist_t_y, F_LAB, BLACK)
    # Légende HP/HC alignée à droite
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

    # --- Bars : fenêtre 12h glissante en slots de 30 min (24 barres) ---
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
    # Fenêtre alignée sur le slot 30-min courant (cohérent avec hourly_buckets)
    current_h = now[3]
    current_m = now[4]
    end_slot_min   = (current_h * 60 + current_m) // bucket_min * bucket_min + bucket_min
    window_start_min = end_slot_min - n_bars * bucket_min   # peut être négatif (hier)
    for i, val in enumerate(padded):
        x = LX + i * (bar_pix + gap_pix)
        h_px = int(val / mx * hist_h)
        if h_px < 1 and val > 0: h_px = 1
        hour_of_bucket = ((window_start_min + i * bucket_min) // 60) % 24
        col = RED if _is_hp(hour_of_bucket) else BLACK
        if h_px > 0:
            d.fill_rect(x, hist_base - h_px, bar_pix, h_px, col)
    d.hline(LX, hist_base + 1, LW, BLACK)
    # Étiquettes horaires : 4 labels toutes les 3h aux indices (0, 6, 12, 18)
    axis_y = hist_base + 5
    label_indices = (0, 6, 12, 18)
    for idx in label_indices:
        h = ((window_start_min + idx * bucket_min) // 60) % 24
        lbl = "{}h".format(h)
        x_c = LX + idx * (bar_pix + gap_pix) + bar_pix // 2
        d.text_pro(lbl, x_c - measure(F_LAB, lbl) // 2, axis_y, F_LAB, BLACK)

    # ============ SÉPARATEUR VERTICAL entre colonnes ============
    # Entre fin colonne gauche (x=474) et début colonne droite (x=510)
    d.vline(492, 85, 360, BLACK)

    # ============ COLONNE DROITE (x 510..786) ============
    RX = 510
    RW = WIDTH - RX - MARGIN
    # Split 60/40 pour donner de la place au CONSOMME JOUR vs COUT JOUR
    R_SUB = int(RW * 0.6)

    # --- RÉSEAU ---
    sy = 90
    d.fill_rect(RX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("RESEAU", RX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(RX, sy + 19, RW, BLACK)

    d.text_pro("CONSOMME . JOUR", RX, sy + 28, F_LAB, BLACK)
    conso_s = _fr(data.get("conso_day", 0), 1)
    d.text_pro(conso_s, RX, sy + 42, F_MED, BLACK)
    d.text_pro("kWh", RX + measure(F_MED, conso_s) + 4, sy + 56, F_LAB, BLACK)

    d.text_pro("COUT . JOUR", RX + R_SUB, sy + 28, F_LAB, BLACK)
    cost_s = _fr(data.get("cost_day", 0), 2)
    d.text_pro(cost_s, RX + R_SUB, sy + 42, F_MED, BLACK)
    d.text_pro("EUR", RX + R_SUB + measure(F_MED, cost_s) + 4, sy + 56, F_LAB, BLACK)

    # --- Encadré TARIF EN COURS ---
    tar_y = sy + 90
    tar_h = 36
    d.rect(RX, tar_y, RW, tar_h, BLACK)
    d.text_pro("TARIF EN COURS", RX + 10, tar_y + 12, F_LAB, BLACK)
    tarif = data.get("tarif", "?")
    tarif_color = RED if tarif == "HP" else BLACK
    tw = measure(F_MED, tarif)
    d.text_pro(tarif, RX + RW - tw - 12, tar_y + 4, F_MED, tarif_color)

    # --- TEMPÉRATURES (split 50/50 pour rester équilibré) ---
    sy = 255
    R_SUB_T = RW // 2
    d.fill_rect(RX, sy + 3, BULLET, BULLET, RED)
    d.text_pro("TEMPERATURES", RX + BULLET + 8, sy, F_LAB, BLACK)
    d.hline(RX, sy + 19, RW, BLACK)

    d.text_pro("EXTERIEUR", RX, sy + 28, F_LAB, RED)
    te_s = _fr(data.get("t_ext", 0), 1)
    d.text_pro(te_s, RX, sy + 42, F_MED, RED)
    d.text_pro("°C", RX + measure(F_MED, te_s) + 2, sy + 42, F_MED, RED)

    d.text_pro("BUANDERIE", RX + R_SUB_T, sy + 28, F_LAB, BLACK)
    tb_s = _fr(data.get("t_buand", 0), 1)
    d.text_pro(tb_s, RX + R_SUB_T, sy + 42, F_MED, BLACK)
    d.text_pro("°C", RX + R_SUB_T + measure(F_MED, tb_s) + 2, sy + 42, F_MED, BLACK)

    # --- Encadré SURPLUS DISPO (contenu plus visible : F_MED centré) ---
    surp_y = 350
    surp_h = 95
    d.rect(RX, surp_y, RW, surp_h, BLACK)
    d.fill_rect(RX + 10, surp_y + 12, BULLET, BULLET, RED)
    d.text_pro("SURPLUS", RX + 10 + BULLET + 8, surp_y + 9, F_LAB, BLACK)

    if data.get("surplus_ok") and data.get("surplus_kw", 0) > 0.05:
        sw_s = _fr(data["surplus_kw"], 1) + " kW"
        sw_w = measure(F_BIG, sw_s)
        d.text_pro(sw_s, RX + (RW - sw_w) // 2, surp_y + 28, F_BIG, RED)
        msg2 = "DISPONIBLE"
        mw = measure(F_LAB, msg2)
        d.text_pro(msg2, RX + (RW - mw) // 2, surp_y + 74, F_LAB, RED)
    else:
        msg = "INSUFFISANT"
        mw = measure(F_BIG, msg)
        d.text_pro(msg, RX + (RW - mw) // 2, surp_y + 38, F_BIG, BLACK)

    # ============ FOOTER ============
    foot_y = 456
    d.hline(MARGIN, foot_y - 8, WIDTH - 2 * MARGIN, BLACK)

    # Bloc batterie (optionnel) à gauche, avant LEVER/COUCHER
    foot_l_x = MARGIN
    if battery is not None:
        pct       = battery.get("percent", 0)
        charging  = battery.get("charging", False)
        is_low    = pct < 20
        # Icône batterie : corps 20x10 + tip 2x4, alignée verticalement avec le texte
        bx, by = MARGIN, foot_y + 2
        bw, bh = 20, 10
        d.rect(bx, by, bw, bh, BLACK)
        d.fill_rect(bx + bw, by + 3, 2, bh - 6, BLACK)
        fill_color = RED if (is_low or charging) else BLACK
        fill_w = max(0, min(bw - 2, int((bw - 2) * pct / 100 + 0.5)))
        if fill_w > 0:
            d.fill_rect(bx + 1, by + 1, fill_w, bh - 2, fill_color)
        # Texte pct
        text_x = bx + bw + 4
        text_col = RED if is_low else BLACK
        pct_s = "{}%".format(pct)
        d.text_pro(pct_s, text_x, foot_y, F_LAB, text_col)
        text_x += measure(F_LAB, pct_s)
        # Marqueur "+" si en charge
        if charging:
            d.text_pro("+", text_x + 2, foot_y, F_LAB, RED)
            text_x += measure(F_LAB, "+") + 2
        foot_l_x = text_x + 12        # séparateur visuel avant LEVER

    foot_l = "LEVER {}  -  COUCHER {}".format(
        data.get("lever", "--:--"), data.get("coucher", "--:--"))
    d.text_pro(foot_l, foot_l_x, foot_y, F_LAB, BLACK)
    foot_r = "HOME ASSISTANT  -  MAJ {:02d}/{:02d}  -  {:02d}:{:02d}  (refresh {} min)".format(
        now[2], now[1], now[3], now[4], refresh_min)
    foot_r_w = measure(F_LAB, foot_r)
    # Icône WiFi RSSI tout à droite, juste après le texte (refresh X min)
    rssi = data.get("wifi_rssi")
    icon_offset = (30 + 8) if rssi is not None else 0   # 30 px icône + 8 px de gap
    d.text_pro(foot_r, WIDTH - MARGIN - foot_r_w - icon_offset, foot_y, F_LAB, BLACK)
    if rssi is not None:
        _draw_wifi_icon(d, WIDTH - MARGIN - 30, foot_y - 6, rssi)


def _free_fonts(*names):
    """Libère les modules de polices après un rendu, sinon ils squattent
    ~15-20 Ko de RAM jusqu'au prochain reset. Critique pour le portail
    captif où on rend l'écran AVANT d'activer l'AP — sans free,
    l'AP peut OOM faute de buffers WiFi."""
    import sys
    for n in names:
        if n in sys.modules:
            del sys.modules[n]
    gc.collect()


def render_dashboard(data, hourly, refresh_min=10, battery=None):
    gc.collect()
    print("Mem libre au début du rendu :", gc.mem_free())
    buf = _get_buf()
    gc.collect()
    print("Buffer prêt, mem libre :", gc.mem_free())
    d = Display(buf=buf)
    import barlow_bold_56 as F_HERO
    import barlow_bold_40 as F_BIG
    import barlow_bold_28 as F_MED
    import archivo_bold_13 as F_LAB
    gc.collect()
    print("Polices chargées, mem libre :", gc.mem_free())
    d.clear()
    now = time.localtime(time.time() + TZ_OFFSET)
    _draw_dashboard(d, data, hourly, now, refresh_min, battery, F_HERO, F_BIG, F_MED, F_LAB)
    print("Commandes enregistrées :", len(d._cmds))
    d.render()
    _free_fonts("barlow_bold_56", "barlow_bold_40",
                "barlow_bold_28", "archivo_bold_13")
    print("Mem libre fin :", gc.mem_free())


# ---------------------------------------------------------------
#  Écrans de statut (portail captif, erreurs réseau, etc.)
# ---------------------------------------------------------------
def render_status(title, lines, color_title=None):
    """Écran de statut générique :
       title       : str, grande ligne centrée en haut (Barlow Bold 40)
       lines       : list de tuples (label, value)
                     label = petite ligne explicative (Archivo Bold 13)
                     value = mise en évidence (Archivo Bold 24)
       color_title : Display.BLACK ou Display.RED (défaut BLACK)
    """
    gc.collect()
    print("Render status :", title)
    buf = _get_buf()
    gc.collect()
    d = Display(buf=buf)
    import barlow_bold_40 as F_TITLE
    import archivo_bold_24 as F_VAL
    import archivo_bold_13 as F_LAB
    gc.collect()

    BLACK, RED = d.BLACK, d.RED
    col_t = color_title if color_title is not None else BLACK

    # Bordure
    d.rect(0, 0, WIDTH, HEIGHT, BLACK)
    d.rect(1, 1, WIDTH - 2, HEIGHT - 2, BLACK)

    # Titre centré
    tw = measure(F_TITLE, title)
    d.text_pro(title, (WIDTH - tw) // 2, 60, F_TITLE, col_t)
    d.hline(80, 118, WIDTH - 160, BLACK)

    # Bloc des lignes : centré verticalement mais avec un cap à y=200
    # (sinon une seule ligne se retrouve perdue au milieu du vide)
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
    print("Render status terminé, mem libre :", gc.mem_free())


def render_portal_screen(ssid, password, ip="192.168.4.1"):
    """Affiche les infos de configuration WiFi quand le portail captif tourne.
    Si password est vide ("" ou None), la ligne MOT DE PASSE est omise
    (réseau ouvert).
    Libère le framebuffer après rendu — le portail tourne jusqu'au reboot,
    on n'aura plus besoin de la dalle, et ESP-IDF a besoin de cette RAM
    pour le DHCP server (sinon le téléphone n'obtient pas d'IP)."""
    lines = [("CONNECTE-TOI AU WIFI :", ssid)]
    if password:
        lines.append(("MOT DE PASSE :", password))
    lines.append(("PUIS OUVRE DANS UN NAVIGATEUR :", "http://" + ip))
    render_status("CONFIGURATION WIFI", lines)
    free_buffer()


def render_error(title, message, retry_min=2):
    """Affiche un écran d'erreur (titre rouge + message + délai de retry)."""
    lines = [("DÉTAIL :", message)]
    if retry_min > 0:
        unit = "MINUTE" if retry_min == 1 else "MINUTES"
        lines.append(("PROCHAIN ESSAI DANS :", "{} {}".format(retry_min, unit)))
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
    mock_battery = {"percent": 73, "voltage": 3.85, "charging": False}
    render_dashboard(mock_data, mock_hourly, refresh_min=10, battery=mock_battery)


if __name__ == "__main__":
    demo_dashboard()
