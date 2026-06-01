# =============================================================
#  main.py — Dashboard ePaper GNI : cycle complet en boucle
#
#  Au boot :
#    1) Provisioning : connecte le WiFi via config.json,
#       ou lance le portail captif "GNI-ePaper-Setup"
#       (http://192.168.4.1, ouvert) si pas configuré.
#    2) Récupère les données depuis Home Assistant.
#    3) Rafraîchit la dalle ePaper.
#    4) Deep sleep N minutes -> wake -> recommence depuis le boot.
#
#  Stratégie mémoire :
#    - On alloue le framebuffer 48 Ko AVANT tout autre import (fragmentation).
#    - On IMPORTE display.py SEULEMENT À LA FIN, après que WiFi soit fermé.
#      → display.py prend ~25 Ko ESP-IDF (framebuf + fonts), donc tant que WiFi
#        est actif il faut garder cette RAM dispo pour le stack TCP/IP.
# =============================================================

import time, gc, machine

# --- ÉTAPE 0 : pré-allocation anti-fragmentation -------------------
gc.collect()
_FRAMEBUF = bytearray(48000)   # 800 * 480 / 8 = BUFSZ de display.py
gc.collect()
print("Framebuffer 48 Ko réservé, mem libre :", gc.mem_free())

# --- Configuration du cycle ---
REFRESH_SEC   = 600       # 10 minutes entre 2 refresh (en production)
DEEP_SLEEP    = True      # False pour rester réveillé (dev/debug)
PORTAL_RENDER = True


def _import_display():
    """Lazy-load de display.py + injection du framebuffer pré-alloué."""
    import display
    display._BUF = _FRAMEBUF
    return display


def cycle():
    # 1/4 - WiFi : display PAS encore importé, ESP-IDF heap au max
    print()
    print("=== 1/4 : Provisioning WiFi ===")
    import provisioning

    def _show_portal_screen():
        if not PORTAL_RENDER:
            print("PORTAL_RENDER=False -> pas de rendu, suit la console série")
            return
        d = _import_display()
        d.render_portal_screen(
            ssid=provisioning.AP_SSID,
            password=provisioning.AP_PASS,
        )

    provisioning.ensure_provisioned(on_portal_start=_show_portal_screen)

    # 2/4 - HA fetch
    print()
    print("=== 2/4 : Récupération des données HA ===")
    import epaper_ha_client as ha
    ha.sync_time()
    data = ha.fetch_dashboard()
    for k, v in data.items():
        print("  %-12s : %s" % (k, v))
    hourly = ha.hourly_buckets(ha.ENT["pv_today"])
    print("  histogramme :", [round(v, 2) for v in hourly])

    # 3/4 - Libère le WiFi AVANT de charger display
    print()
    print("=== 3/4 : Libération réseau ===")
    import network
    network.WLAN(network.STA_IF).active(False)
    network.WLAN(network.AP_IF).active(False)
    gc.collect()
    print("Mem libre :", gc.mem_free())

    # 4/4 - Render (display importé ici)
    print()
    print("=== 4/4 : Rendu ePaper ===")
    d = _import_display()
    d.render_dashboard(data, hourly, refresh_min=REFRESH_SEC // 60)


# ============= Exécution =============
try:
    cycle()
    next_sleep_ms = REFRESH_SEC * 1000
    print()
    print("Cycle OK.")
except Exception as e:
    print("ERREUR cycle :", e)
    next_sleep_ms = 120 * 1000   # 2 min
    try:
        d = _import_display()
        d.render_error("ERREUR CYCLE", str(e)[:40], retry_min=2)
    except Exception as e2:
        print("Affichage erreur impossible :", e2)

if DEEP_SLEEP:
    print("Deep sleep dans 5 s ({} min)...".format(next_sleep_ms // 60000))
    print("(Ctrl+C maintenant pour interrompre)")
    time.sleep(5)
    machine.deepsleep(next_sleep_ms)
else:
    print("DEEP_SLEEP=False -> on s'arrête là pour le dev.")
