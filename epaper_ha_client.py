# =============================================================
#  epaper_ha_client.py — Couche réseau du dashboard ePaper (MicroPython)
#
#  Lit ses identifiants depuis un fichier config.json sur la carte :
#    {
#      "wifi_ssid": "...",
#      "wifi_pass": "...",
#      "ha_url"   : "http://192.168.x.y:8123",
#      "ha_token" : "eyJ..."
#    }
#
#  Test :  python3 -m mpremote run epaper_ha_client.py
# =============================================================

import json, network, time, gc

try:
    import requests
except ImportError:
    import urequests as requests


# --- Config (config.json) ---------------------------------------------
def load_config():
    try:
        with open("config.json") as f:
            return json.load(f)
    except OSError:
        return {}


_cfg      = load_config()
WIFI_SSID = _cfg.get("wifi_ssid", "")
WIFI_PASS = _cfg.get("wifi_pass", "")
HA_URL    = _cfg.get("ha_url", "")
HA_TOKEN  = _cfg.get("ha_token", "")
HEADERS   = {"Authorization": "Bearer " + HA_TOKEN,
             "Content-Type":  "application/json"}


# --- Entités du dashboard (alignées sur la maquette v4) ---------------
ENT = {
    "pv_today":   "sensor.pv_production_today_thingspeak_2",
    "pv_now":     "sensor.pv_production_thingspeak",
    "inj_today":  "sensor.injection_reseau_jour",
    "conso_hp":   "sensor.conso_reseau_hp_jour",
    "conso_hc":   "sensor.conso_reseau_hc_jour",
    "cost_day":   "sensor.cout_reseau_total_jour",
    "surplus_w":  "sensor.reseau_puissance_export",
    "surplus_ok": "binary_sensor.surplus_solaire_stable",
    "tarif":      "sensor.tarif_electricite_ores_2026",
    "t_ext":      "sensor.thermometre_exterieur_temperature",
    "t_buand":    "sensor.temperature_buandrie_temperature",
    "lever":      "sensor.jour_lever",
    "coucher":    "sensor.jour_coucher",
}


# --- WiFi (reset propre, fix "Wifi Internal State Error") -------------
def connect_wifi(timeout=20):
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    time.sleep(0.5)
    sta.active(True)
    time.sleep(0.5)
    if not sta.isconnected():
        print("WiFi: connexion à", WIFI_SSID)
        sta.connect(WIFI_SSID, WIFI_PASS)
        t0 = time.time()
        while not sta.isconnected():
            if time.time() - t0 > timeout:
                raise OSError("WiFi: timeout")
            time.sleep(0.5)
    print("WiFi OK ·", sta.ifconfig()[0])
    return sta


def sync_time():
    try:
        import ntptime
        ntptime.settime()
        print("NTP OK")
    except Exception as e:
        print("NTP échec :", e)


# --- API HA -----------------------------------------------------------
def _get(path):
    r = requests.get(HA_URL + path, headers=HEADERS)
    try:
        data = r.json()
    finally:
        r.close()
    gc.collect()
    return data


def get_state(entity):
    try:
        d = _get("/api/states/" + entity)
        s = d.get("state")
        if s in (None, "unknown", "unavailable", ""):
            return None
        return s
    except Exception as e:
        print("get_state", entity, "→", e)
        return None


def get_float(entity, default=0.0):
    s = get_state(entity)
    if s is None:
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def get_bool(entity):
    return get_state(entity) == "on"


def get_history(entity, hours=16):
    now   = time.time()
    start = now - hours * 3600
    tm    = time.gmtime(start)
    iso   = "%04d-%02d-%02dT%02d:%02d:%02d" % tm[:6]
    path  = ("/api/history/period/" + iso +
             "?filter_entity_id=" + entity +
             "&minimal_response&significant_changes_only&no_attributes")
    out = []
    try:
        data = _get(path)
        if data and isinstance(data, list) and data[0]:
            for pt in data[0]:
                st = pt.get("state")
                if st in (None, "unknown", "unavailable", ""):
                    continue
                try:
                    out.append(float(st.replace(",", ".")))
                except (ValueError, AttributeError):
                    continue
    except Exception as e:
        print("get_history", entity, "→", e)
    return out


# --- Histogramme horaire aligné sur les vraies heures du jour ----------
TZ_OFFSET = 2 * 3600   # CEST = UTC+2 (été belgique)


def _parse_iso_utc(s):
    """Parse un timestamp ISO 8601 UTC depuis HA, renvoie un nombre de secondes
    depuis l'epoch MicroPython (2000-01-01).
    Format attendu : '2026-05-29T15:00:00+00:00' ou avec sous-secondes."""
    try:
        if "T" not in s:
            return None
        date_part, time_part = s.split("T", 1)
        if "." in time_part:
            time_part = time_part.split(".", 1)[0]
        if "Z" in time_part:
            time_part = time_part.split("Z", 1)[0]
        elif "+" in time_part:
            time_part = time_part.split("+", 1)[0]
        Y, M, D = [int(x) for x in date_part.split("-")]
        h, mn, sc = [int(x) for x in time_part.split(":")]
        return time.mktime((Y, M, D, h, mn, sc, 0, 0))
    except Exception:
        return None


def hourly_buckets(entity_cumulatif, nb=24, bucket_min=30):
    """Production par tranche de `bucket_min` minutes (kWh), fenêtre glissante
    de `nb` slots se terminant à l'heure courante.

    Par défaut : 24 tranches de 30 min = fenêtre 12h, slots alignés sur
    :00 et :30 par rapport à minuit local.

    Utilise le sensor CUMULATIF du jour (resetting à minuit, ex:
    sensor.pv_production_today_thingspeak_2). Combiné à
    `significant_changes_only`, la volumétrie de la réponse HA reste
    raisonnable (~50-200 points pour 12h) et ça tient en RAM.

    Algorithme :
      1. Fetch l'historique avec timestamps depuis ~10 min avant le start
      2. Pour chaque frontière de slot, interpole linéairement entre les
         2 points encadrants (sensor cumulatif et monotone hors reset)
      3. Diff entre frontières consécutives = production sur le slot
      4. Gère le reset à minuit (diff négatif → on prend la nouvelle valeur)
    """
    import gc
    gc.collect()
    now_utc = time.time()
    local = time.localtime(now_utc + TZ_OFFSET)

    midnight_local_utc = now_utc - (local[3] * 3600 + local[4] * 60 + local[5])
    now_min_local = local[3] * 60 + local[4]
    # Fin du slot 30-min en cours (arrondi sup)
    end_slot_min   = (now_min_local // bucket_min + 1) * bucket_min
    start_slot_min = end_slot_min - nb * bucket_min        # peut être négatif (hier soir)
    fetch_start_utc = midnight_local_utc + start_slot_min * 60 - 600

    tm = time.gmtime(fetch_start_utc)
    iso = "%04d-%02d-%02dT%02d:%02d:%02d" % tm[:6]
    path = ("/api/history/period/" + iso +
            "?filter_entity_id=" + entity_cumulatif +
            "&minimal_response&significant_changes_only&no_attributes")
    print("hourly_buckets: GET", path)

    points = []
    raw_count = 0
    try:
        data = _get(path)
        if data and isinstance(data, list) and data[0]:
            raw_count = len(data[0])
            for pt in data[0]:
                st = pt.get("state")
                lc = pt.get("last_changed") or pt.get("last_updated")
                if st in (None, "unknown", "unavailable", "") or not lc:
                    continue
                ts = _parse_iso_utc(lc) if isinstance(lc, str) else None
                if ts is None:
                    continue
                try:
                    val = float(st.replace(",", "."))
                    points.append((ts, val))
                except (ValueError, AttributeError):
                    continue
    except Exception as e:
        print("hourly_buckets fetch:", e)
        return [0.0] * nb

    print("  HA: %d points bruts, %d parsés" % (raw_count, len(points)))

    if not points:
        return [0.0] * nb
    points.sort(key=lambda p: p[0])

    # Interpolation linéaire pour chaque frontière de slot (nb+1 frontières)
    boundary = {}
    for i in range(nb + 1):
        target = midnight_local_utc + (start_slot_min + i * bucket_min) * 60
        if i == nb:
            target = min(target, now_utc)

        prev_p = None
        next_p = None
        for ts, val in points:
            if ts <= target:
                prev_p = (ts, val)
            else:
                next_p = (ts, val)
                break

        if prev_p is None and next_p is None:
            continue
        if prev_p is None:
            boundary[i] = next_p[1]
        elif next_p is None:
            boundary[i] = prev_p[1]
        else:
            t1, v1 = prev_p
            t2, v2 = next_p
            if t2 <= t1 or v2 < v1:
                boundary[i] = v1
            else:
                frac = (target - t1) / (t2 - t1)
                boundary[i] = v1 + frac * (v2 - v1)

    # Diff entre frontières interpolées = production du slot
    buckets = []
    for i in range(nb):
        v1 = boundary.get(i)
        v2 = boundary.get(i + 1)
        if v1 is not None and v2 is not None:
            d = v2 - v1
            if d < 0:
                d = v2
            buckets.append(max(0.0, d))
        else:
            buckets.append(0.0)

    print("  buckets kWh:", [round(b, 2) for b in buckets])
    return buckets


# --- Dashboard groupé -------------------------------------------------
def _local_hhmm(s):
    """Convertit une heure UTC retournée par HA en HH:MM local.

    Accepte 3 formats :
      - "HH:MM" ou "HH:MM:SS"   (state brut du template HA)
      - "YYYY-MM-DDTHH:MM:SS..." (timestamp ISO)
      - None / unknown / unavailable → "--:--"
    Applique TZ_OFFSET et gère le wrap autour de minuit.
    """
    if not s or s in ("unknown", "unavailable"):
        return "--:--"
    try:
        if "T" in s:
            t_part = s.split("T", 1)[1]
            hh = int(t_part[:2])
            mm = int(t_part[3:5])
        else:
            parts = s.split(":")
            hh = int(parts[0])
            mm = int(parts[1])
    except (ValueError, IndexError):
        return s  # format inconnu, on rend tel quel
    total_min = (hh * 60 + mm + TZ_OFFSET // 60) % (24 * 60)
    return "%02d:%02d" % (total_min // 60, total_min % 60)


def fetch_dashboard():
    d = {}
    d["pv_today"]   = get_float(ENT["pv_today"])
    d["pv_now_kw"]  = get_float(ENT["pv_now"]) / 1000.0
    d["inj_today"]  = get_float(ENT["inj_today"])
    d["conso_day"]  = get_float(ENT["conso_hp"]) + get_float(ENT["conso_hc"])
    d["cost_day"]   = get_float(ENT["cost_day"])
    d["surplus_kw"] = get_float(ENT["surplus_w"]) / 1000.0
    d["surplus_ok"] = get_bool(ENT["surplus_ok"])
    d["tarif"]      = get_state(ENT["tarif"]) or "?"
    d["t_ext"]      = get_float(ENT["t_ext"])
    d["t_buand"]    = get_float(ENT["t_buand"])
    d["lever"]      = get_state(ENT["lever"]) or "--:--"
    d["coucher"]    = get_state(ENT["coucher"]) or "--:--"
    # Force du signal WiFi (dBm) capturée tant que la connexion est active
    try:
        import network
        d["wifi_rssi"] = network.WLAN(network.STA_IF).status("rssi")
    except (OSError, AttributeError, ImportError):
        d["wifi_rssi"] = None
    if d["pv_today"] > 0.05:
        d["inj_pct"] = int(d["inj_today"] / d["pv_today"] * 100 + 0.5)
    else:
        d["inj_pct"] = 0
    d["auto_pct"] = max(0, 100 - d["inj_pct"])
    return d


# --- Démo -------------------------------------------------------------
def main():
    connect_wifi()
    sync_time()
    print()
    print("=== Dashboard ===")
    for k, v in fetch_dashboard().items():
        print("  %-11s : %s" % (k, v))
    print()
    print("=== Histogramme horaire (kWh, ~16h) ===")
    print(" ", hourly_buckets(ENT["pv_today"]))


if __name__ == "__main__":
    main()
