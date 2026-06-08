# =============================================================
#  battery.py  —  Etat batterie / charge pour le dashboard ePaper
#  MicroPython (ESP32)
#
#  Fournit read() -> {"percent", "voltage", "charging"}
#    - charging True  : LiPo en charge (CRATE > seuil positif)
#    - charging False : LiPo en décharge (CRATE négatif ou ~0)
#
#  Détection charge :
#    Mode "fuel_gauge" → registre CRATE (0x16) du MAX17048
#       Donne la pente du % en %/heure, signé. Pas besoin de câbler
#       un GPIO de détection USB.
#    Mode "adc" → GPIO USB_DETECT_PIN (à câbler sur VBUS via diviseur)
# =============================================================
from machine import Pin, I2C, ADC
import time

# ---------------- A ADAPTER selon ton cablage ----------------
MODE = "fuel_gauge"        # "fuel_gauge" ou "adc"

# Jauge MAX17048 (I2C)
I2C_SCL = 21
I2C_SDA = 22
MAX17048_ADDR = 0x36

# Seuil de detection charge via CRATE (en %/heure)
# CRATE > 0.5 %/h  → charge active
# CRATE <= 0.5 %/h → décharge ou idle
# (filtre le bruit autour de zéro)
CRATE_CHARGING_THRESHOLD = 0.5

# Mesure ADC (si MODE = "adc")
ADC_PIN = 34
ADC_DIVIDER = 2.0

# Detection USB / charge (mode ADC uniquement, fallback)
USB_DETECT_PIN = 35
USB_ACTIVE_HIGH = True

# Courbe LiPo 1 cellule : tension -> % (mode ADC)
_LIPO = [(4.20, 100), (4.10, 90), (4.00, 80), (3.90, 70), (3.85, 60),
         (3.80, 55), (3.75, 45), (3.70, 35), (3.65, 25), (3.60, 15),
         (3.50, 8), (3.40, 3), (3.30, 0)]


def _pct_from_v(v):
    if v >= _LIPO[0][0]:
        return 100
    if v <= _LIPO[-1][0]:
        return 0
    for i in range(len(_LIPO) - 1):
        v1, p1 = _LIPO[i]
        v2, p2 = _LIPO[i + 1]
        if v2 <= v <= v1:
            return int(p2 + (p1 - p2) * (v - v2) / (v1 - v2))
    return 0


def _read_fuel_gauge():
    """Lit MAX17048 et renvoie (voltage_V, soc_pct, crate_pct_per_h).

    Le registre CRATE (0x16) est signé 16-bit, en complément à 2.
    Chaque LSB = 0.208 %/heure (datasheet Maxim).
    """
    i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=100000)
    # Pré-check : la jauge est-elle sur le bus ? (sinon timeout I2C = ~1s)
    if MAX17048_ADDR not in i2c.scan():
        raise OSError("MAX17048 absent du bus I2C")

    rv = i2c.readfrom_mem(MAX17048_ADDR, 0x02, 2)   # VCELL
    rs = i2c.readfrom_mem(MAX17048_ADDR, 0x04, 2)   # SOC
    rc = i2c.readfrom_mem(MAX17048_ADDR, 0x16, 2)   # CRATE (signed)

    v   = ((rv[0] << 8) | rv[1]) * 78.125e-6        # V
    soc = ((rs[0] << 8) | rs[1]) / 256.0            # %

    # CRATE en complément à 2
    crate_raw = (rc[0] << 8) | rc[1]
    if crate_raw >= 0x8000:
        crate_raw -= 0x10000
    crate = crate_raw * 0.208                       # %/h

    return v, int(soc + 0.5), crate


def _read_adc():
    adc = ADC(Pin(ADC_PIN))
    adc.atten(ADC.ATTN_11DB)            # plage ~0-3.3 V
    acc = 0
    for _ in range(16):
        try:
            acc += adc.read_uv()        # microvolts (MicroPython recent)
        except AttributeError:
            acc += adc.read() / 4095 * 3.3 * 1e6
        time.sleep_ms(5)
    v_pin = (acc / 16) / 1e6
    v_batt = v_pin * ADC_DIVIDER
    return v_batt, _pct_from_v(v_batt)


def usb_present():
    """Fallback pour le mode ADC : lit un GPIO câblé sur VBUS via diviseur.
    Pas utilisé en mode fuel_gauge (la détection est faite via CRATE)."""
    try:
        val = Pin(USB_DETECT_PIN, Pin.IN).value()
        return (val == 1) if USB_ACTIVE_HIGH else (val == 0)
    except Exception:
        return False


def read():
    """Renvoie {'percent', 'voltage', 'charging'} ou None si jauge absente."""
    try:
        if MODE == "fuel_gauge":
            v, pct, crate = _read_fuel_gauge()
            # Charge active si la pente est nettement positive
            charging = crate > CRATE_CHARGING_THRESHOLD
            print("battery: CRATE = {:+.2f} %/h -> charging={}".format(crate, charging))
        else:
            v, pct = _read_adc()
            charging = usb_present()
    except Exception as e:
        print("battery: jauge non détectée -", e)
        return None

    # Sanity check : tension LiPo 1S = 3.0 - 4.2 V (sinon hardware suspect)
    if v < 2.5:
        return None

    return {"percent":  max(0, min(100, pct)),
            "voltage":  round(v, 2),
            "charging": charging}


def status_text():
    """Texte prêt à afficher (selon ta logique : charge -> 'EN CHARGE', sinon %)."""
    b = read()
    if b is None:
        return "--"
    return "EN CHARGE" if b["charging"] else ("%d%%" % b["percent"])


if __name__ == "__main__":
    print(read())
    print("Affichage:", status_text())
