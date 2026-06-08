# i2c_scan.py
# Balaye plusieurs combinaisons GPIO pour trouver le MAX17048 (adresse 0x36)
# Usage : python3 -m mpremote run i2c_scan.py

from machine import Pin, I2C, SoftI2C

# Couples (sda, scl) probables sur ESP32-WROOM-32 + Waveshare e-Paper driver
COMBINATIONS = [
    (21, 22),  # Standard ESP32
    (22, 21),  # Swap classique
    (4, 5),
    (5, 4),
    (16, 17),
    (17, 16),
    (18, 19),
    (19, 18),
    (32, 33),
    (33, 32),
    (0, 2),
    (2, 0),
]

TARGET = 0x36  # MAX17048

print("=" * 60)
print("Scan I2C - recherche du MAX17048 (0x36 = 54 decimal)")
print("=" * 60)
print()

found = []

for sda_pin, scl_pin in COMBINATIONS:
    # 1) Tente Hardware I2C bus 0
    try:
        i2c = I2C(0, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=100000)
        devs = i2c.scan()
        if devs:
            mark = " <<< MAX17048 !" if TARGET in devs else ""
            print("HW I2C(0) SDA={} SCL={} -> {}{}".format(
                sda_pin, scl_pin, devs, mark))
            if TARGET in devs:
                found.append(("HW", 0, sda_pin, scl_pin))
    except Exception as e:
        pass  # combinaison non supportee, on continue

    # 2) Tente Software I2C (bit-banged, plus tolerant)
    try:
        i2c = SoftI2C(sda=Pin(sda_pin), scl=Pin(scl_pin), freq=100000)
        devs = i2c.scan()
        if devs:
            mark = " <<< MAX17048 !" if TARGET in devs else ""
            print("SW I2C    SDA={} SCL={} -> {}{}".format(
                sda_pin, scl_pin, devs, mark))
            if TARGET in devs:
                found.append(("SW", None, sda_pin, scl_pin))
    except Exception as e:
        pass

print()
print("=" * 60)
if found:
    print("Resultat : {} combinaison(s) trouvee(s) avec MAX17048 :".format(len(found)))
    for typ, bus, sda, scl in found:
        bus_str = "(bus={})".format(bus) if bus is not None else ""
        print("  -> {} I2C {} SDA=Pin({}) SCL=Pin({})".format(typ, bus_str, sda, scl))
    print()
    print("Utilise cette config dans battery.py")
else:
    print("AUCUNE combinaison ne trouve le MAX17048.")
    print()
    print("Causes probables :")
    print("  1. Faux contact Dupont sur SDA, SCL, VIN ou GND")
    print("  2. Fil casse a l'interieur du sertissage")
    print("  3. MAX17048 chip endommage (I2C HS mais LED VIN OK)")
    print("  4. Court entre SDA ou SCL et la masse")
    print()
    print("-> Tester la continuite des 4 fils au multimetre")
print("=" * 60)
