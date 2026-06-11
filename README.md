# ePaper Dashboard

Supporting blog post : https://www.lets-talk-about.tech/2026/06/home-assistant-solar-self-consumption.html

> 🇫🇷 Tableau de bord énergie domestique sur dalle e-paper 7,5" tricolore alimenté par Home Assistant.<br>
> 🇬🇧 Home energy dashboard on a 7.5" tricolor e-paper panel powered by Home Assistant.<br>
> ESP32 + MicroPython + Waveshare 7.5" B V2 BWR (800×480) + LiPo battery.

---

## 🌐 Languages / Langues

- [🇫🇷 **Documentation française**](#-documentation-française) — version originale
- [🇬🇧 **English documentation**](#-english-documentation) — full translation

---
---

# 🇫🇷 Documentation française

## Table des matières (FR)

1. [Présentation du projet](#présentation-du-projet)
2. [Matériel](#matériel)
3. [Maquette](#maquette)
4. [Architecture logicielle](#architecture-logicielle)
5. [Configuration](#configuration)
6. [Installation et premier démarrage](#installation-et-premier-démarrage)
7. [Cycle de fonctionnement et autonomie](#cycle-de-fonctionnement-et-autonomie)
8. [Lecture du dashboard](#lecture-du-dashboard)
9. [Dépannage](#dépannage)
10. [Limitations connues](#limitations-connues)
11. [Annexe A — Code source](#annexe-a--code-source)
12. [Annexe B — Boîtier](#annexe-b--boîtier)
13. [Annexe C — Roadmap & idées](#annexe-c--roadmap--idées)

---

## Présentation du projet

L'objectif est un affichage permanent et économe en énergie qui rapporte, d'un coup d'œil, l'état du système électrique de la maison :

- production photovoltaïque (cumul du jour, puissance instantanée, histogramme demi-horaire sur 12 h)
- réseau (consommation jour, coût jour, tarif HP/HC en cours)
- températures clés (extérieur, buanderie)
- indication actionnable « tu peux brancher un équipement » avec la puissance disponible quand le surplus est suffisant

Choix de la dalle e-paper pour deux raisons :

- **Persistance** — l'image reste affichée sans consommation. Pas de back-light, pas de scintillement, lisible en plein jour comme un livre.
- **Autonomie batterie** — l'ESP32 dort ~99 % du temps (~30 µA en deep sleep) et ne se réveille que toutes les 10 minutes pour rafraîchir l'écran. Sur LiPo 8200 mAh avec le Seeed Lipo Rider Plus (charge + boost intégrés), test d'autonomie réelle en cours : ~0,23 %/h mesuré, soit ~15-16 jours projetés sur une charge complète.

Les données proviennent d'une instance Home Assistant locale via son API REST. Pas de dépendance cloud, pas d'abonnement.

---

## Matériel

### Composants principaux (tous en service)

| Élément | Référence / modèle | Rôle |
|---|---|---|
| Dalle e-paper | Waveshare 7,5" B V2 (BWR 800×480) | Affichage tricolore noir / blanc / rouge |
| Carte de pilotage | Waveshare ESP32 e-Paper Driver Board (USB-C) | SPI vers la dalle + WiFi + deep sleep |
| Câble nappe | Inclus avec la dalle | FFC 24 broches |
| Batterie LiPo 1S | HXJNLDC 8200 mAh, PCM intégrée, JST PH | Cellule lithium-polymère 3,7V |
| Charge + boost USB-C | Seeed Lipo Rider Plus (charge LiPo via USB-C + boost 5V/2,4A) | Remplace TP4056 + boost séparés |
| Jauge de charge | Adafruit MAX17048 (I²C 0x36, ref Adafruit 5580) | Lecture % batterie + détection charge via registre CRATE |
| Adaptateur polarité JST PH | Câble custom soudé (Chinois ↔ Adafruit) | Adapte la polarité du LiPo HXJNLDC vers la convention Adafruit |
| Câble JST PH inverseur | Câble custom soudé (Adafruit ↔ Seeed) | Inverse la polarité entre MAX17048 (Adafruit) et Lipo Rider Plus (Seeed) |
| Câble USB-A → USB-C | Court (~15 cm) | Relie la sortie boost du Lipo Rider Plus à l'ESP32 |

### Brochage ESP32 → dalle e-paper

| Signal dalle | Pin ESP32 |
|---|---|
| CLK (SPI clock) | GPIO 13 |
| DIN (MOSI) | GPIO 14 |
| CS  | GPIO 15 |
| DC  | GPIO 27 |
| RST | GPIO 26 |
| BUSY | GPIO 25 |

### Brochage I²C pour la jauge MAX17048

| Signal | Pin ESP32 |
|---|---|
| **SDA** | **GPIO 22** |
| **SCL** | **GPIO 21** |
| VIN | 3,3 V |
| GND | GND |

⚠️ **Attention** : sur le module MAX17048 d'Adafruit (ref 5580), le pin **SDA est physiquement plus proche du bord SCL** de l'ESP32. Il est très facile de croiser ces 2 fils par mégarde. Si `battery.read()` retourne `None`, la première chose à vérifier est l'ordre SDA/SCL — voir le script `i2c_scan.py` dans le repo qui balaye les combinaisons GPIO automatiquement.

### Câblage de l'alimentation (chaîne complète)

```
USB-C charger (optionnel) ──► Lipo Rider Plus (USB-C in)
                                     │
LiPo HXJNLDC                          │
   │                                  │
   ▼                                  │
[adaptateur polarité Chinois→Adafruit]│
   │                                  │
   ▼                                  │
MAX17048 JST#1                        │
   │ (passthrough interne)            │
   ▼                                  │
MAX17048 JST#2                        │
   │                                  │
[câble JST PH INVERSEUR Adafruit→Seeed]
   │                                  │
   ▼                                  │
Lipo Rider Plus JST "Li-po" ◀─────────┘
   │
   ▼ (boost 5V interne)
USB-A out ──► [câble USB-A→USB-C] ──► ESP32 (USB-C input)

MAX17048 headers (VIN, GND, SDA, SCL)
   │
   ▼ (4 fils Dupont)
ESP32 (3V3, GND, GPIO 22, GPIO 21)
```

Cette topologie a 3 vertus :
1. Le **MAX17048 en passthrough** mesure la batterie sans dévier de courant
2. Le **Lipo Rider Plus** combine charge USB-C + boost 5V en un seul module fiable (2,4A continu)
3. **L'ESP32 est alimenté par le boost**, jamais directement par la LiPo — protégé contre les sous-tensions

---

## Maquette

Layout 800 × 480 px, deux colonnes séparées par un trait vertical fin :

```
┌─────────────────────────────────────────────────────────────────────┐
│ VEN. 6 JUN                                              2,4 kW      │
│ CERFONTAINE                                       PRODUCTION PV -   │
│                                                   MAINTENANT        │
│─────────────────────────────────────────│ ─────────────────────────│
│ ■ PRODUCTION SOLAIRE                    │ ■ RESEAU                  │
│ PRODUIT AUJOURD'HUI    INJECTE RESEAU   │ CONSOMME.JOUR  COUT.JOUR  │
│ 10,1 kWh               5,8 kWh          │  4,7 kWh        1,39 EUR  │
│                                         │ ┌─────────────────────────┐│
│ AUTOCONSOMME 43%         INJECTE 57%    │ │ TARIF EN COURS      HP ││
│ ████████░░░░░░░░░░░░░░░░░               │ └─────────────────────────┘│
│                                         │                            │
│ PRODUCTION HORAIRE        ■HP ■HC       │ ■ TEMPERATURES             │
│      █ █                                │ EXTERIEUR     BUANDERIE    │
│      █ █ █                              │  16,9°         21,2°       │
│      █ █ █ █ █                          │                            │
│      █ █ █ █ █ █ █ █                    │ ┌──── ■ SURPLUS ──────────┐│
│  █ █ █ █ █ █ █ █ █ █ █ █                │ │       1,8 kW            ││
│  12h    15h    18h    21h               │ │      DISPONIBLE         ││
│─────────────────────────────────────────│ └─────────────────────────┘│
│ [🔋 87%] LEVER 05:30 - COUCHER 21:51   HOME ASSISTANT - MAJ 08/06 - 14:23 (refresh 10 min) 📶│
└─────────────────────────────────────────────────────────────────────┘
```

Couleurs : **rouge** pour les valeurs et alertes importantes (production solaire, tarif HP, température extérieure, surplus dispo) ; **noir** pour tout le reste.

### Icône batterie (footer bas-gauche)

L'icône batterie (corps 20×10 px + tip 2×4 px + texte `XX%`) change de couleur selon l'état :

| État | Icône | Texte |
|---|---|---|
| Normal (≥ 20%, hors charge) | **noir** | **noir** |
| Faible (< 20%, hors charge) | **rouge** | **rouge** |
| En charge (USB-C branché sur Lipo Rider Plus, tout %) | **rouge** | **rouge** |

La détection « en charge » se fait via le **registre CRATE** du MAX17048 (0x16, signé 16-bit, unité 0,208 %/heure) : si la pente est > 0,5 %/h, on considère que la batterie charge. Cette méthode évite de câbler un GPIO supplémentaire pour détecter la présence du chargeur USB.

L'histogramme en bas à gauche montre la production demi-horaire sur les 12 dernières heures (24 barres de 30 min). Les barres en HP sont rouges, en HC noires. Labels seulement à 12h, 15h, 18h, 21h pour rester lisible.

L'icône WiFi en bas à droite (style smartphone : point + 3 arcs en éventail) indique la force du signal RSSI mesurée pendant le cycle. Nombre d'arcs pleins selon les seuils dBm : 3 (excellent, > -55), 2 (bon, -55 à -70), 1 (faible, -70 à -85), 0 (mauvais, < -85).

---

## Architecture logicielle

Cinq modules Python sur la flash de l'ESP32, plus les modules de fonts compilés :

```
/
├── main.py                  ← orchestrateur du cycle complet
├── provisioning.py          ← WiFi (config.json) ou portail captif
├── epaper_ha_client.py      ← API Home Assistant + bucketing histogramme
├── display.py               ← pilote UC8179 + layout dashboard (FR)
├── display_en.py            ← idem en anglais (utilise l'un OU l'autre)
├── battery.py               ← jauge MAX17048 (% + CRATE pour détection charge)
├── config.json              ← credentials WiFi + URL/token HA
├── barlow_bold_56.py        ← font "héro" (hour value du PV)
├── barlow_bold_40.py        ← font "big" (date, pv_now, surplus)
├── barlow_bold_28.py        ← font "medium" (chiffres secondaires)
├── archivo_bold_24.py       ← font écrans de statut
└── archivo_bold_13.py       ← font "label" (titres et footer)
```

**Note** : ne déployer que l'un de `display.py` (UI française) ou `display_en.py` (UI anglaise) — ils sont mutuellement exclusifs. Le fichier copié sur l'ESP32 doit s'appeler `display.py` quel que soit le langage (puisque `main.py` fait `import display`).

### Le cycle (main.py)

1. **Pré-allocation framebuffer** (avant tout import non-trivial) — `bytearray(48000)` est alloué en premier dans la heap MicroPython pour éviter la fragmentation. Ce buffer servira à la composition de l'image avant envoi à la dalle.

2. **WiFi connect** — `provisioning.ensure_provisioned()` lit `config.json` et connecte le STA. Si `config.json` est absent ou WiFi inaccessible, bascule en mode portail captif (cf. limitations).

3. **Récupération HA** — `epaper_ha_client.fetch_dashboard()` interroge les 14 entités configurées (1 requête REST chacune, GET `/api/states/<entity_id>`), puis `hourly_buckets()` interroge l'historique pour reconstruire l'histogramme demi-horaire.

4. **Libération réseau** — `WLAN.active(False)` pour récupérer la RAM ESP-IDF, puis `gc.collect()` côté Python.

5. **Lecture batterie** — `bat = battery.read()` interroge le MAX17048 en I²C (lit VCELL + SOC + CRATE), renvoie `{"percent", "voltage", "charging"}` ou `None` si la jauge est absente.

6. **Rendu ePaper** — `display.render_dashboard(data, hourly, refresh_min, battery=bat)` charge les polices, compose le framebuffer 48 Ko (plan noir + plan rouge), envoie à la dalle, attend le refresh (~20 s), met la dalle en deep sleep.

7. **Deep sleep ESP32** — `machine.deepsleep(REFRESH_SEC * 1000)`. Au réveil, hard reset complet → retour à l'étape 1.

### Stratégie mémoire (point critique)

L'ESP32 a un budget RAM serré, partagé entre :

- **heap MicroPython** (objets Python) — ~165 Ko libres au boot frais
- **heap ESP-IDF** (WiFi, mbed-TLS, framebuf C, etc.) — ~120 Ko libres au boot frais

Le cycle complet est conçu pour ne jamais dépasser ces limites :

| Phase | Heap Python libre | Heap ESP-IDF libre |
|---|---|---|
| Boot | 165 Ko | 120 Ko |
| Après alloc framebuffer 48 Ko | 113 Ko | 120 Ko |
| WiFi actif (sans display chargé) | 92 Ko | 42 Ko |
| Pendant fetch HA | 90 Ko | 40 Ko |
| Après libération WiFi | 110 Ko | 100 Ko |
| Display + 4 fonts chargés (47 Ko de bytecode) | 47 Ko | 95 Ko |
| Pendant render ePaper | 42 Ko | 95 Ko |
| Fin de cycle | 42 Ko | 100 Ko |

**Pourquoi importer `display` après le WiFi** : `display.py` + ses 4 polices consomme ~25 Ko de heap ESP-IDF rien qu'à l'import (framebuf en C, allocations internes). Si on charge display avant le WiFi, l'ESP-IDF n'a plus assez pour les buffers WiFi (~40 Ko nécessaires) → `WiFi Out of Memory` au premier `sta.active(True)`.

### Configuration des entités HA

Dans `epaper_ha_client.py`, dict `ENT` :

```python
ENT = {
    "pv_today":   "sensor.pv_production_today_thingspeak_2",  # cumul jour kWh
    "pv_now":     "sensor.pv_production_thingspeak",          # puissance W
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
```

**Template HA pour lever/coucher du soleil** — pièges connus :

Les attributs `next_rising` et `next_setting` de `sun.sun` sont en **UTC**. Un template naïf avec `strftime` ressort donc en UTC, pas en local. Bon template (DST-aware automatique) :

```yaml
template:
  - sensor:
      - name: "Jour - Lever"
        unique_id: jour_lever
        state: >
          {% set t = as_datetime(state_attr('sun.sun','next_rising')) | as_local %}
          {{ t.strftime('%H:%M') if t else 'unavailable' }}
      - name: "Jour - Coucher"
        unique_id: jour_coucher
        state: >
          {% set t = as_datetime(state_attr('sun.sun','next_setting')) | as_local %}
          {{ t.strftime('%H:%M') if t else 'unavailable' }}
```

### Détection charge via le registre CRATE du MAX17048

`battery.py` ne câble plus de GPIO pour détecter la présence USB. À la place, il lit le **registre CRATE** (0x16) du MAX17048 qui renvoie la pente de variation du % en signed %/heure :

- **CRATE > +0,5 %/h** → charge active (icône batterie passe en rouge)
- **CRATE entre -0,5 et +0,5 %/h** → idle ou décharge faible (icône noire)
- **CRATE < -0,5 %/h** → décharge active

```python
def _read_fuel_gauge():
    i2c = I2C(0, scl=Pin(21), sda=Pin(22), freq=100000)
    if MAX17048_ADDR not in i2c.scan():
        raise OSError("MAX17048 absent du bus I2C")
    rv = i2c.readfrom_mem(MAX17048_ADDR, 0x02, 2)   # VCELL
    rs = i2c.readfrom_mem(MAX17048_ADDR, 0x04, 2)   # SOC
    rc = i2c.readfrom_mem(MAX17048_ADDR, 0x16, 2)   # CRATE (signed)
    v   = ((rv[0] << 8) | rv[1]) * 78.125e-6
    soc = ((rs[0] << 8) | rs[1]) / 256.0
    crate_raw = (rc[0] << 8) | rc[1]
    if crate_raw >= 0x8000:
        crate_raw -= 0x10000              # complément à 2
    crate = crate_raw * 0.208             # %/h selon datasheet
    return v, int(soc + 0.5), crate
```

⏱️ **Temps de convergence** : le MAX17048 met **~30-60 secondes** après le branchement USB-C pour que CRATE reflète la nouvelle pente (moyenne glissante). Donc juste après plug, on peut encore voir le CRATE négatif précédent — c'est normal et corrigé au cycle suivant.

### Grille tarifaire HP/HC (ORES 2026)

```python
def _is_hp(hour):
    # Heures pleines : 7h-11h ET 17h-22h, tous les jours (week-ends inclus)
    return (7 <= hour < 11) or (17 <= hour < 22)
```

Plus de distinction semaine/week-end depuis le 1er janvier 2026.

### Bucketing demi-horaire (epaper_ha_client.py)

24 buckets de 30 min sur les 12 dernières heures :

1. Requête historique : `GET /api/history/period/<iso>?filter_entity_id=sensor.pv_production_today_thingspeak_2&minimal_response&significant_changes_only&no_attributes`
2. Parse des timestamps ISO de chaque point
3. Pour chaque frontière de slot (toutes les 30 min sur la fenêtre 12 h), **interpolation linéaire** entre les 2 points encadrants (le sensor étant cumulatif et monotone, sauf reset à minuit)
4. Production du slot = différence entre 2 frontières interpolées
5. Gestion du reset minuit : si la diff est négative, on prend la valeur après reset

Sans interpolation, avec `significant_changes_only` les points sont espacés de 10-20 min en moyenne, donc prendre le « dernier point avant la frontière » introduit une erreur systémique (parfois 25 % d'erreur par bucket).

---

## Configuration

### config.json

À déposer sur la flash de l'ESP32 (`mpremote cp config.json :`) :

```json
{
  "wifi_ssid": "TonReseau",
  "wifi_pass": "MotDePasse",
  "ha_url":    "http://192.168.x.x:8123",
  "ha_token":  "eyJhbGciOiJIUzI1NiIs..."
}
```

Le token HA s'obtient dans Home Assistant : *Profil utilisateur → Tokens d'accès longue durée → Créer un token*. Garder ce token confidentiel — il donne accès complet à HA.

### Constantes dans main.py

```python
REFRESH_SEC   = 600      # 10 minutes entre 2 refresh
DEEP_SLEEP    = True     # False pour rester réveillé (dev)
PORTAL_RENDER = True     # afficher écran portail si WiFi KO
```

### Constantes dans epaper_ha_client.py et display.py

```python
TZ_OFFSET = 2 * 3600     # CEST (heure d'été belge)
                         # CET (heure d'hiver) = 1 * 3600
```

À ajuster manuellement aux changements d'heure (printemps/automne) — pas de gestion DST automatique pour simplifier.

### Constantes dans battery.py

```python
I2C_SCL = 21
I2C_SDA = 22
CRATE_CHARGING_THRESHOLD = 0.5   # %/h, seuil de détection charge
```

---

## Installation et premier démarrage

### Pré-requis (Mac/Linux)

```bash
pip install mpremote esptool
```

### 1. Flasher MicroPython sur l'ESP32 (une seule fois)

```bash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX erase-flash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX --baud 460800 \
    write-flash -z 0x1000 ESP32_GENERIC-20260406-v1.28.0.bin
```

Le firmware doit être MicroPython >= 1.23 (testé sur 1.28). Télécharger sur https://micropython.org/download/ESP32_GENERIC/.

### 2. Déployer le code (version française)

```bash
python3 -m mpremote cp \
    main.py \
    provisioning.py \
    epaper_ha_client.py \
    display.py \
    battery.py \
    config.json \
    barlow_bold_56.py \
    barlow_bold_40.py \
    barlow_bold_28.py \
    archivo_bold_24.py \
    archivo_bold_13.py \
    :
```

**Pour la version anglaise**, remplacer `display.py` par `display_en.py` qu'on renomme :

```bash
# Pousser display_en.py renommé en display.py
python3 -m mpremote cp display_en.py :display.py
```

Vérifier :

```bash
python3 -m mpremote ls
```

### 3. Premier boot

Débrancher / rebrancher l'USB-C, ou :

```bash
python3 -m mpremote reset
```

Pour suivre les logs du premier cycle :

```bash
python3 -m mpremote
# Ctrl+] pour quitter sans rebooter
```

### 4. Cycle suivant

Le cycle s'enchaîne tout seul, plus besoin du Mac. Pour intervenir plus tard, voir [Dépannage](#dépannage).

---

## Cycle de fonctionnement et autonomie

### Déroulé d'un cycle (~30 secondes actives)

| Étape | Durée | Conso ESP32 |
|---|---|---|
| Boot (hard reset depuis deep sleep) | 1 s | ~100 mA |
| WiFi connect | 2-4 s | ~150 mA (pic à 250 mA) |
| Sync NTP | 1 s | ~120 mA |
| Fetch 14 entités HA + historique | 2-4 s | ~120 mA |
| WiFi off + GC | 1 s | ~80 mA |
| Lecture MAX17048 | < 0,1 s | ~80 mA |
| Compose framebuffer + render ePaper | 20-22 s | ~80 mA (pic à 50 mA pendant refresh) |
| Entrée deep sleep | < 1 s | — |
| **Total actif** | **~30 s** | **~150 mA moyen** |

Puis deep sleep : **~30 µA** pendant ~9 min 30.

### Estimation autonomie (LiPo 8200 mAh, Lipo Rider Plus boost ~85% rendement)

| Refresh | Cycles/jour | Conso jour | Autonomie estimée |
|---|---|---|---|
| 5 min | 288 | ~360 mAh | ~23 jours |
| 10 min | 144 | ~180 mAh | ~46 jours |
| 15 min | 96 | ~120 mAh | ~68 jours |
| 30 min | 48 | ~60 mAh | ~135 jours |

### Mesure réelle (test en cours depuis le 6 juin 2026)

| Date / heure | % batterie | Tension | CRATE |
|---|---|---|---|
| 6 juin, 13:00 | 98% | ~4,18 V | — (point de départ) |
| 8 juin, 13:00 | 87% | 4,06 V | -0,23 %/h moyen |

Pente mesurée : **0,23 %/h** sur 48h en autonomie pure → **autonomie réelle projetée : ~15-16 jours** sur une charge complète avec refresh toutes les 10 min. À noter que la pente s'accélère typiquement en dessous de 20% (S-curve LiPo), donc l'arrêt complet du système est attendu vers le **21-22 juin 2026**.

### Comportement en cas d'erreur

| Erreur | Comportement |
|---|---|
| WiFi inaccessible (3 retries) | Écran d'erreur affiché, retry dans 2 min |
| HA inaccessible | Écran d'erreur affiché, retry dans 2 min |
| Une seule entité absente | Affichage `--` à la place de la valeur, cycle normal |
| MAX17048 absent du bus I2C | `battery.read()` retourne `None`, footer sans icône batterie |
| MemoryError pendant le rendu | Écran d'erreur, retry dans 2 min |
| OOM avant le rendu | Reboot complet via watchdog (~5 s) |
| config.json absent | Bascule en portail captif (cf. limitations) |

L'écran ne reste donc jamais figé sur de l'info périmée : soit une vraie mise à jour, soit un message d'erreur explicite avec la date du dernier essai.

---

## Lecture du dashboard

### Zone HEADER (haut)

- **Date du jour** en grand à gauche (`VEN. 6 JUN`)
- **Localité** (`CERFONTAINE`) en petit dessous
- **Production PV actuelle** en grand rouge à droite (`2,4 kW`) — c'est l'info que tu regardes en premier le matin pour voir si le soleil est généreux

### Colonne GAUCHE : production solaire

- **Produit aujourd'hui** : cumul depuis 00:00 en kWh
- **Injecté réseau** : cumul depuis 00:00 en kWh (ce que tu as renvoyé au réseau parce que tu en produisais plus que tu en consommais)
- **Barre autoconsommé / injecté** : split visuel du jour. Plus la zone noire (autoconsommé) est large, mieux c'est financièrement.
- **Histogramme production horaire** : courbe du jour. 24 barres = les 12 dernières heures par tranche de 30 min. Les barres en heures pleines (7-11h et 17-22h) sont **rouges**, en heures creuses **noires**.

### Colonne DROITE : réseau, températures, surplus

- **Consommé jour** : kWh achetés au réseau depuis 00:00 (HP + HC additionnés)
- **Coût jour** : euros depuis 00:00 selon la grille ORES 2026
- **Tarif en cours** : `HC` (heures creuses, fond blanc) ou `HP` (heures pleines, fond rouge)
- **Températures** : extérieur (rouge) et buanderie (noir)
- **Encadré SURPLUS** :
  - Si `binary_sensor.surplus_solaire_stable` est ON et `surplus_kw > 0,05` → `X,X kW DISPONIBLE` en grand rouge
  - Sinon → `INSUFFISANT` en grand noir

### Zone FOOTER (bas)

- **Batterie** (gauche, si MAX17048 câblé) : icône batterie 20×10 px + `XX%`. **L'icône entière passe en rouge** quand la batterie est en charge (USB-C branché, détecté via CRATE > 0,5 %/h) ou quand le niveau est faible (< 20%). Sinon tout est en noir.
- **Lever / Coucher du soleil** (centre gauche)
- **Source + horodatage + intervalle refresh** (droite)
- **Force du signal WiFi** (extrême droite) : 3 arcs (excellent > -55 dBm) à 0 (point seul, < -85 dBm)

---

## Dépannage

### Piège polarité Adafruit ↔ Seeed (le plus subtil)

🪤 **Le piège qui coûte 2 heures** : Adafruit et Seeed utilisent des conventions de polarité **opposées** sur leur connecteur JST PH 2-pin batterie. Le MAX17048 (Adafruit) attend `+` sur la broche A, le Lipo Rider Plus (Seeed) attend `+` sur la broche B.

Si on relie directement les deux connecteurs avec un câble JST PH droit, **la polarité s'inverse** entre les deux modules → impossible de charger la LiPo proprement.

**Solution** : insérer un **câble JST PH inverseur** (câble custom soudé avec les fils croisés rouge↔noir) entre la sortie du MAX17048 et l'entrée du Lipo Rider Plus.

**Vérification avant branchement** :
1. Multimètre en V DC sur la sortie JST du MAX17048 → repère la polarité réelle (rouge vers `+` Adafruit)
2. Multimètre en V DC sur l'entrée JST du Lipo Rider Plus (avec USB-C branché, sans LiPo) → relève `+4,22V` côté `+` Seeed
3. Si les deux pins `+` ne sont pas sur le même côté du connecteur, **le câble doit croiser**

### MAX17048 non détecté (battery.read() retourne None)

Vérifications dans l'ordre :

1. **Pins SDA/SCL inversés** — le piège classique. Le câblage physique correct est :
   - `SDA → ESP32 GPIO 22`
   - `SCL → ESP32 GPIO 21`
   - Lance `i2c_scan.py` (dispo dans le repo) qui balaye les 12 combinaisons GPIO × HW/SW I²C → te dira lequel marche
2. **Header pins non soudés** sur le MAX17048 (les modules Adafruit 5580 sont livrés sans header soudé) — souder les 6 pins en haut du module
3. **Continuité des fils Dupont** au multimètre (continuité entre les 2 extrémités)
4. **Présence électrique** : tension entre GND et VIN du MAX17048 doit être 3,3V (alim par l'ESP32)

### `mpremote run` vs `mpremote cp` (le piège discret)

🪤 `mpremote run script.py` exécute le **fichier local** sur l'ESP32 temporairement. Il ne **modifie pas la flash** de l'ESP32.

Si tu édites `battery.py` localement et que tu fais `mpremote run battery.py`, ça marche. Mais au cycle suivant, `main.py` charge l'**ancien** `battery.py` resté sur la flash → comportement inchangé.

**Solution** : toujours `mpremote cp battery.py :battery.py` après une modification locale pour persister sur la flash.

### Le dashboard ne s'est pas rafraîchi cette nuit

**Cause la plus probable historiquement** : auto-shutoff du powerbank USB. **Résolu** depuis qu'on utilise le Lipo Rider Plus qui maintient la sortie 5V active en permanence (pas d'auto-shutoff sous faible courant).

Autres causes :
- Batterie LiPo vide (vérifier le %)
- WiFi en panne (vérifier l'écran d'erreur affiché)
- ESP32 planté (rare, mais possible — soft reset via débranchage/rebranchage)

### "WiFi Out of Memory" au premier cycle

ESP-IDF n'a pas assez de heap pour les buffers WiFi. Solution : déjà géré côté code par le pattern WiFi-first / display-last. Si récidive, soft-reset pour repartir d'un état frais.

### Lever / coucher du soleil décalés de 1-2 heures

Cause : le template HA renvoie un timestamp ISO en UTC. Fix : appliquer le filtre `| as_local` dans le template HA (voir section *Configuration des entités HA*). Aucune modification du code dashboard nécessaire.

### Icône batterie ne passe pas en rouge quand le chargeur est branché

Le MAX17048 a une **moyenne glissante sur ~30-60 secondes** pour calculer CRATE. Après avoir branché l'USB-C, attendre au moins 1 minute avant de vérifier — au prochain cycle de 10 min, l'icône sera rouge si la charge est confirmée.

Si après plusieurs cycles l'icône reste noire alors que la batterie monte :
- Vérifier que `battery.py` lit bien le **registre CRATE (0x16)** et non `usb_present()` (ancien code obsolète)
- Lire la sortie console : `battery: CRATE = +X.XX %/h -> charging=True/False`

### Glyphes `?` à la place du texte

L'une des polices `barlow_bold_XX.py` ou `archivo_bold_XX.py` n'a pas le caractère demandé dans son charset. Solution : regénérer la police avec `font_to_py -c "AÀBCD...stuvw...0123456789,. " barlow-bold.ttf 28 barlow_bold_28.py` en passant tous les caractères nécessaires.

### Le portail captif ne fonctionne pas

Le mode portail captif (`PORTAL_RENDER=True`, déclenché quand `config.json` est absent) est **expérimental sur MicroPython 1.28**. Workaround : créer `config.json` à la main avec un éditeur de texte, puis `mpremote cp config.json :`.

### Intervenir sur un device autonome (cadre déjà accroché)

```bash
# Voir les logs en direct (interrompt le deep sleep si on est entre 2 cycles)
python3 -m mpremote

# Pousser une nouvelle version de code
python3 -m mpremote cp <fichier> :
python3 -m mpremote reset

# Désactiver l'autonomie (revenir en REPL pur)
python3 -m mpremote rm main.py
python3 -m mpremote reset
```

---

## Limitations connues

| # | Limitation | Sévérité | Workaround |
|---|---|---|---|
| 1 | Portail captif KO sur MicroPython 1.28 | Mineur | Créer `config.json` à la main |
| 2 | Pas de gestion DST automatique pour `TZ_OFFSET` côté ESP32 | Mineur | Ajuster manuellement 2 fois par an |
| 3 | Tous les fonts en charset partiel | Mineur | Tester avant de mettre un nouveau texte |
| 4 | Refresh ePaper bloque pendant ~20 s | Inhérent | Aucun (limite physique de l'encre) |
| 5 | Polarité Adafruit ↔ Seeed inversée sur JST PH | Majeur | Câble inverseur custom soudé (cf. dépannage) |
| 6 | MAX17048 ESD-sensitive | Mineur | Manipulation avec précautions, garder un spare |
| 7 | Délai 30-60s pour détection charge via CRATE | Mineur | Patienter 1 cycle après le branchement USB-C |
| 8 | Histogramme nécessite `significant_changes_only` sur le sensor cumulatif | Inhérent | Le sensor doit logguer assez de points (~1/15 min minimum) |
| 9 | Marge mémoire serrée (~12-15 Ko libres après render) | Majeur | À surveiller si on ajoute des features |
| 10 | LiPo plafonne à ~98% (pas 100%) | Mineur | Comportement normal des chargeurs CC/CV qui s'arrêtent avant 100% pour préserver la cellule |

---

## Annexe A — Code source

### main.py (~120 lignes)

Orchestrateur du cycle. Allocation framebuffer en tête (anti-fragmentation), import lazy de `display`, lecture batterie en fin de cycle, gestion des erreurs et deep sleep en bas.

### provisioning.py (~330 lignes)

- `connect_sta(cfg, timeout=20)` : 3 retries avec diagnostic ESP-IDF heap pour debug
- `start_portal(...)` : monte un AP `GNI-ePaper-Setup`, serveur HTTP minimal, scan WiFi
- `ensure_provisioned(on_portal_start)` : enchaîne `connect_sta` puis fallback `start_portal`

### epaper_ha_client.py (~250 lignes)

- `sync_time()` : appel NTP
- `_get(path)` : helper GET vers l'API HA
- `fetch_dashboard()` : récupère les 14 entités, capture aussi `wifi_rssi` via `WLAN.status("rssi")`
- `hourly_buckets(entity, nb=24, bucket_min=30)` : histogramme avec interpolation linéaire

### display.py / display_en.py (~660 lignes)

Les deux fichiers sont identiques en structure et API ; seuls les strings UI, commentaires et format des nombres diffèrent. Choisir l'un et le déployer comme `display.py`.

- `Display` : pilote SPI bas niveau pour le contrôleur UC8179
- `_draw_wifi_icon(d, x, y, rssi)` : icône WiFi style smartphone (point + 3 arcs)
- `_draw_dashboard(...)` : compose le layout complet incluant l'icône batterie unifiée en rouge si en charge
- `render_dashboard(data, hourly, refresh_min=10, battery=None)` : entry point publique
- Le bloc batterie utilise une couleur unique `icon_color = RED if (charging or is_low) else BLACK` qui s'applique à tous les éléments (corps, tip, remplissage, texte)

### battery.py (~110 lignes)

- `_read_fuel_gauge()` : I²C scan, lecture des registres **VCELL (0x02), SOC (0x04) et CRATE (0x16)** du MAX17048
- Conversion CRATE complément à 2 → %/h signé via le coefficient 0,208 (datasheet)
- `read()` : retourne `{"percent", "voltage", "charging"}` avec `charging = (crate > 0.5)` ou `None` si jauge absente
- Constantes : `I2C_SCL = 21`, `I2C_SDA = 22`, `CRATE_CHARGING_THRESHOLD = 0.5`
- Print debug : `battery: CRATE = +X.XX %/h -> charging=True/False` à chaque lecture

### i2c_scan.py (utilitaire dans le repo)

Script de diagnostic qui balaye 12 combinaisons GPIO × HW/SW I²C pour identifier la config qui détecte le MAX17048. Utile pour valider le câblage physique avant de lancer un cycle complet.

### Fonts (générées avec font_to_py de Peter Hinch)

- `barlow_bold_56.py` (13 Ko) — chiffres + lettres header
- `barlow_bold_40.py` (23 Ko) — date, pv_now, surplus
- `barlow_bold_28.py` (8 Ko) — chiffres secondaires
- `archivo_bold_24.py` (31 Ko) — écrans de statut
- `archivo_bold_13.py` (13 Ko) — labels et footer

Pour regénérer :

```bash
font_to_py -c "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-/:°€%" \
           -x Barlow-Bold.ttf 28 barlow_bold_28.py
```

---

## Annexe B — Boîtier

**Solution adoptée : cadre photo bois ~17×22 cm avec passe-partout sur mesure** ✅

L'intégration finale utilise un cadre photo bois grand public (acheté en magasin de bricolage / supermarché pour ~2-15 € selon la qualité du bois). Caractéristiques minimales :

- **Dimensions intérieures** : ≥ 17 × 22 cm pour loger la dalle (170 × 112 mm)
- **Profondeur intérieure** : ≥ 25 mm (idéal 30 mm pour le confort)
- **Dos amovible** : essentiel pour accéder à l'électronique
- **Passe-partout off-white ou crème** : 1,5-2 mm d'épaisseur, découpé pour exposer la zone active (163 × 98 mm) — cache les bordures de la dalle et donne un rendu professionnel

### Layout interne (vue arrière)

```
┌───────────────────────────────────────┐
│                                       │  ← vue arrière du cadre
│  ┌─────────┐  ┌────────────────────┐ │
│  │  LiPo   │  │  ESP32 driver      │ │  ← collés au scotch double-face
│  │ 75×65mm │  │  board + nappe FFC │ │     mousse fine (1-2 mm)
│  │         │  │                    │ │
│  └─────────┘  └────────────────────┘ │
│       │                              │
│       ▼                              │
│  ┌─────────┐    ┌─────────┐          │
│  │MAX17048 │    │Lipo     │          │
│  │         │    │Rider Plus│         │
│  └─────────┘    └─────────┘          │
│       │                              │
│       └── 4 fils Dupont I²C ─────────┘
│           vers ESP32                   │
│                                        │
│       Câble USB-C charger sort par     │
│       le bas du cadre (trou discret)   │
│                                        │
└───────────────────────────────────────┘
```

### Validation profondeur (cadre 25-30 mm)

| Élément | Épaisseur | Source |
|---|---|---|
| Vitre plastique avant du cadre | ~1 mm | typique |
| Passe-partout (mat board) | 1,5-2 mm | au choix |
| Dalle ePaper raw 7,5" | **0,91 mm** | Spec Waveshare officielle |
| Nappe FFC (rayon de pliage) | ~3 mm | recommandation Waveshare |
| LiPo HXJNLDC 8200 mAh (7565121) | **12 mm** | mesure réelle |
| Carte ESP32 driver board (PCB + USB-C) | ~5 mm | PCB 1,6 mm + connecteur ~3 mm |
| Lipo Rider Plus + MAX17048 | ~5 mm chacun | petites cartes plates |
| Mousse de calage + back carton | ~2 mm | calage final |

Layout côte-à-côte (pas en stack) : épaisseur dominante = celle du LiPo (12 mm) + ~5 mm de cartes = **~17 mm utilisés** dans le cadre de 25 mm. 8 mm de marge pour les câbles et le pliage FFC.

### Étapes d'intégration

1. **Préparer le passe-partout** : découper la fenêtre à 163 × 98 mm pour exposer la zone active
2. **Coller la dalle contre la vitre** avec du double-face mousse fine (1 mm) sur les bords
3. **Placer la batterie** à gauche du dos avec du double-face mousse 3 mm (vérifier qu'elle ne gondole pas)
4. **Placer l'ESP32 driver board** au centre/droite avec son scotch double-face
5. **Câbler la chaîne énergie** : LiPo → adaptateur polarité → MAX17048 → câble inverseur → Lipo Rider Plus → USB-A vers ESP32
6. **Câbler l'I²C** : 4 fils Dupont entre MAX17048 et ESP32 (3V3, GND, P22 SDA, P21 SCL)
7. **Souder éventuellement les pins du Lipo Rider Plus** pour câblage direct 5V/GND (alternative au câble USB-A→USB-C pour gagner de la place)
8. **Faire passer le câble USB-C charger** par un trou discret au bas du cadre (~5 mm de diamètre)
9. **Fermer le dos** : carton de fond avec mousse de calage, clipsage du cadre

**Coût total enclosure** : ~5-10 € avec un cadre IKEA / supermarché.

### Alternatives explorées

- **Boîtier 3D imprimé** : possible mais nécessite un imprimante PETG (résistance UV)
- **Sandwich plexi laser** : plus esthétique mais coût d'accès à une découpe laser
- **Cadre IKEA RÖDALM 21×30** : marche aussi (validé 30 mm profondeur), mais le cadre bois 17×22 cm donne un rendu plus chaleureux

---

## Annexe C — Roadmap & idées

### Réalisé ✅

- [x] Software complet (5 modules MicroPython + 5 polices)
- [x] Détection charge via registre CRATE du MAX17048 (sans GPIO USB-detect)
- [x] Intégration battery dans main.py + display.py (icône rouge en charge)
- [x] Hardware autonome complet : LiPo + Lipo Rider Plus + MAX17048
- [x] Câble adaptateur polarité Chinois→Adafruit
- [x] Câble JST PH inverseur Adafruit→Seeed
- [x] Intégration finale dans cadre photo bois avec passe-partout
- [x] Version bilingue (FR + EN) du dashboard

### En cours 🔬

- [ ] Test d'autonomie complète sur une charge (démarré 6 juin 2026 à 98%, arrêt système attendu ~21-22 juin)

### À court terme

- [ ] Souder les pins 5V/GND du Lipo Rider Plus pour câblage direct ESP32 (élimination du câble USB-A→USB-C deleyCON)
- [ ] Désigner un PCB carrier custom (KiCad) pour clean integration définitive
- [ ] Compiler les modules Python en `.mpy` avec `mpy-cross` pour économiser ~30% de RAM

### À moyen terme

- [ ] Pin EN du Lipo Rider Plus contrôlé par GPIO ESP32 pour couper le boost en deep sleep → +30% d'autonomie attendue
- [ ] DNS hijack dans le portail captif pour pop-up auto-redirect sur iOS/Android
- [ ] Fix du portail captif (probablement attendre MicroPython 1.29+)
- [ ] Affichage de la prévision météo du lendemain

### Idées exploratoires

- [ ] Bouton physique pour forcer un refresh (réveil par GPIO en deep sleep)
- [ ] Mode "nuit" avec refresh à 30 min entre 23h-6h
- [ ] Statistiques détaillées sur appui long (autoconso semaine, économie cumulée)
- [ ] Intégration HA bidirectionnelle (push depuis HA → force refresh via MQTT)
- [ ] Multi-page : alterner énergie / météo / agenda
- [ ] Version XL avec dalle 13" / 800×1280

---

*Dernière mise à jour : 8 juin 2026 — version 4.0 (hardware finalisé : Lipo Rider Plus + MAX17048 en service, détection charge via registre CRATE, icône batterie rouge en charge, intégration cadre bois complète, correction brochage I²C SDA→GPIO22/SCL→GPIO21)*

---
---

# 🇬🇧 English documentation

## Table of contents (EN)

1. [Project overview](#project-overview)
2. [Hardware](#hardware)
3. [Layout mockup](#layout-mockup)
4. [Software architecture](#software-architecture)
5. [Configuration](#configuration-1)
6. [Installation and first boot](#installation-and-first-boot)
7. [Operating cycle and battery life](#operating-cycle-and-battery-life)
8. [Reading the dashboard](#reading-the-dashboard)
9. [Troubleshooting](#troubleshooting)
10. [Known limitations](#known-limitations)
11. [Appendix A — Source code](#appendix-a--source-code)
12. [Appendix B — Enclosure](#appendix-b--enclosure)
13. [Appendix C — Roadmap & ideas](#appendix-c--roadmap--ideas)

---

## Project overview

The goal is a permanent, energy-efficient display that reports, at a glance, the state of the home's electrical system:

- photovoltaic production (today's total, instantaneous power, 30-minute histogram over 12 h)
- grid usage (today's consumption, today's cost, current peak/off-peak rate)
- key temperatures (outdoor, laundry room)
- actionable "you can plug in an appliance" indication with the available power when surplus is sufficient

The e-paper panel was chosen for two reasons:

- **Persistence** — the image stays on screen without consuming power. No backlight, no flicker, readable in broad daylight like a book.
- **Battery life** — the ESP32 sleeps ~99 % of the time (~30 µA in deep sleep) and only wakes every 10 minutes to refresh the display. On an 8200 mAh LiPo with the Seeed Lipo Rider Plus (integrated charge + 5V boost), real-world autonomy test in progress: ~0.23 %/h measured, projected ~15-16 days on a full charge.

Data comes from a local Home Assistant instance via its REST API. No cloud dependency, no subscription.

---

## Hardware

### Main components (all in service)

| Item | Reference / model | Role |
|---|---|---|
| E-paper panel | Waveshare 7.5" B V2 (BWR 800×480) | Tricolor black / white / red display |
| Driver board | Waveshare ESP32 e-Paper Driver Board (USB-C) | SPI to panel + WiFi + deep sleep |
| Ribbon cable | Included with the panel | FFC 24 pins |
| LiPo 1S battery | HXJNLDC 8200 mAh, integrated PCM, JST PH | 3.7V lithium polymer cell |
| Charger + USB-C boost | Seeed Lipo Rider Plus (LiPo charging via USB-C + 5V/2.4A boost) | Replaces separate TP4056 + boost converter |
| Fuel gauge | Adafruit MAX17048 (I²C 0x36, Adafruit part 5580) | Battery % reading + charge detection via CRATE register |
| JST PH polarity adapter | Custom soldered cable (Chinese ↔ Adafruit) | Adapts the HXJNLDC LiPo polarity to Adafruit convention |
| JST PH inverter cable | Custom soldered cable (Adafruit ↔ Seeed) | Reverses polarity between MAX17048 (Adafruit) and Lipo Rider Plus (Seeed) |
| USB-A to USB-C cable | Short (~15 cm) | Connects the Lipo Rider Plus boost output to the ESP32 |

### ESP32 → e-paper panel pinout

| Panel signal | ESP32 pin |
|---|---|
| CLK (SPI clock) | GPIO 13 |
| DIN (MOSI) | GPIO 14 |
| CS  | GPIO 15 |
| DC  | GPIO 27 |
| RST | GPIO 26 |
| BUSY | GPIO 25 |

### I²C pinout for the MAX17048 fuel gauge

| Signal | ESP32 pin |
|---|---|
| **SDA** | **GPIO 22** |
| **SCL** | **GPIO 21** |
| VIN | 3.3 V |
| GND | GND |

⚠️ **Warning**: on the Adafruit MAX17048 module (part 5580), the **SDA pin is physically closer to the SCL edge** of the ESP32. It's very easy to cross these 2 wires accidentally. If `battery.read()` returns `None`, the first thing to check is the SDA/SCL order — see the `i2c_scan.py` script in the repo that sweeps GPIO combinations automatically.

### Full power chain wiring

```
USB-C charger (optional) ──► Lipo Rider Plus (USB-C in)
                                     │
LiPo HXJNLDC                          │
   │                                  │
   ▼                                  │
[polarity adapter Chinese→Adafruit]   │
   │                                  │
   ▼                                  │
MAX17048 JST#1                        │
   │ (internal passthrough)           │
   ▼                                  │
MAX17048 JST#2                        │
   │                                  │
[JST PH INVERTER cable Adafruit→Seeed]│
   │                                  │
   ▼                                  │
Lipo Rider Plus JST "Li-po" ◀─────────┘
   │
   ▼ (internal 5V boost)
USB-A out ──► [USB-A→USB-C cable] ──► ESP32 (USB-C input)

MAX17048 headers (VIN, GND, SDA, SCL)
   │
   ▼ (4 Dupont wires)
ESP32 (3V3, GND, GPIO 22, GPIO 21)
```

This topology has 3 virtues:
1. The **MAX17048 in passthrough** measures the battery without deviating current
2. The **Lipo Rider Plus** combines USB-C charging + 5V boost in one reliable module (2.4A continuous)
3. **The ESP32 is powered by the boost**, never directly by the LiPo — protected against undervoltage

---

## Layout mockup

800 × 480 px layout, two columns separated by a thin vertical line:

```
┌─────────────────────────────────────────────────────────────────────┐
│ FRI. 6 JUN                                              2.4 kW      │
│ CITYNAME                                          PV PRODUCTION -   │
│                                                   NOW               │
│─────────────────────────────────────────│ ─────────────────────────│
│ ■ SOLAR PRODUCTION                      │ ■ GRID                    │
│ PRODUCED TODAY         GRID EXPORT      │ USED TODAY     COST TODAY │
│ 10.1 kWh               5.8 kWh          │  4.7 kWh        1.39 EUR  │
│                                         │ ┌─────────────────────────┐│
│ SELF-USED 43%            EXPORTED 57%   │ │ CURRENT RATE       PK  ││
│ ████████░░░░░░░░░░░░░░░░░               │ └─────────────────────────┘│
│                                         │                            │
│ HOURLY PRODUCTION         ■PK ■OFF      │ ■ TEMPERATURES             │
│      █ █                                │ OUTDOOR       LAUNDRY      │
│      █ █ █                              │  16.9°C        21.2°C      │
│      █ █ █ █ █                          │                            │
│      █ █ █ █ █ █ █ █                    │ ┌──── ■ SURPLUS ──────────┐│
│  █ █ █ █ █ █ █ █ █ █ █ █                │ │       1.8 kW            ││
│  12h    15h    18h    21h               │ │      AVAILABLE          ││
│─────────────────────────────────────────│ └─────────────────────────┘│
│ [🔋 87%] SUNRISE 05:30 - SUNSET 21:51  HOME ASSISTANT - UPD 08/06 - 14:23 (refresh 10 min) 📶│
└─────────────────────────────────────────────────────────────────────┘
```

Colors: **red** for important values and alerts (solar production, peak rate, outdoor temperature, surplus available); **black** for everything else.

### Battery icon (bottom-left footer)

The battery icon (20×10 px body + 2×4 px tip + `XX%` text) changes color based on state:

| State | Icon | Text |
|---|---|---|
| Normal (≥ 20%, not charging) | **black** | **black** |
| Low (< 20%, not charging) | **red** | **red** |
| Charging (USB-C plugged in, any %) | **red** | **red** |

Charging detection uses the **CRATE register** of the MAX17048 (0x16, signed 16-bit, unit 0.208 %/hour): if the slope is > 0.5 %/h, the battery is considered charging. This method avoids wiring an extra GPIO for USB detection.

The bottom-left histogram shows 30-minute production over the last 12 hours (24 half-hour bars). Peak-hour bars are red, off-peak bars are black. Hour labels only at 12h, 15h, 18h, 21h to stay readable.

The WiFi icon at bottom-right (smartphone-style: dot + 3 fan arcs) indicates the RSSI signal strength measured during the cycle. Number of solid arcs per dBm threshold: 3 (excellent, > -55), 2 (good, -55 to -70), 1 (weak, -70 to -85), 0 (poor, < -85).

---

## Software architecture

Five Python modules on the ESP32 flash, plus the compiled font modules:

```
/
├── main.py                  ← orchestrates the complete cycle
├── provisioning.py          ← WiFi (config.json) or captive portal
├── epaper_ha_client.py      ← Home Assistant API + histogram bucketing
├── display.py               ← UC8179 driver + dashboard layout (French)
├── display_en.py            ← same in English (use ONE or the OTHER)
├── battery.py               ← MAX17048 fuel gauge (% + CRATE for charging)
├── config.json              ← WiFi credentials + HA URL/token
├── barlow_bold_56.py        ← "hero" font (hourly PV value)
├── barlow_bold_40.py        ← "big" font (date, pv_now, surplus)
├── barlow_bold_28.py        ← "medium" font (secondary numbers)
├── archivo_bold_24.py       ← status screens font
└── archivo_bold_13.py       ← "label" font (titles and footer)
```

**Note**: ship only one of `display.py` (French UI) or `display_en.py` (English UI) — they are mutually exclusive. The Python file you actually copy to the ESP32 must be named `display.py` regardless of language (since `main.py` does `import display`).

### The cycle (main.py)

1. **Framebuffer pre-allocation** (before any non-trivial import) — `bytearray(48000)` is allocated first in the MicroPython heap to avoid fragmentation.

2. **WiFi connect** — `provisioning.ensure_provisioned()` reads `config.json` and connects the STA. Falls back to captive portal if needed.

3. **HA fetch** — `epaper_ha_client.fetch_dashboard()` queries the 14 configured entities, then `hourly_buckets()` queries history to rebuild the 30-minute histogram.

4. **Network release** — `WLAN.active(False)` to reclaim ESP-IDF RAM, then `gc.collect()`.

5. **Battery read** — `bat = battery.read()` queries the MAX17048 via I²C (reads VCELL + SOC + CRATE), returns `{"percent", "voltage", "charging"}` or `None`.

6. **ePaper render** — `display.render_dashboard(data, hourly, refresh_min, battery=bat)` composes the 48 KB framebuffer (black plane + red plane), sends to the panel.

7. **ESP32 deep sleep** — `machine.deepsleep(REFRESH_SEC * 1000)`. On wake, full hard reset.

### Memory strategy (critical point)

The ESP32 has a tight RAM budget, shared between:

- **MicroPython heap** (Python objects) — ~165 KB free at fresh boot
- **ESP-IDF heap** (WiFi, mbed-TLS, framebuf C, etc.) — ~120 KB free at fresh boot

| Phase | Python heap free | ESP-IDF heap free |
|---|---|---|
| Boot | 165 KB | 120 KB |
| After 48 KB framebuffer alloc | 113 KB | 120 KB |
| WiFi active (display not loaded) | 92 KB | 42 KB |
| During HA fetch | 90 KB | 40 KB |
| After WiFi released | 110 KB | 100 KB |
| Display + 4 fonts loaded | 47 KB | 95 KB |
| During ePaper render | 42 KB | 95 KB |
| End of cycle | 42 KB | 100 KB |

**Why `display` is imported after WiFi**: `display.py` + its 4 fonts consumes ~25 KB of ESP-IDF heap on import alone. If display is loaded before WiFi, ESP-IDF doesn't have enough left for WiFi buffers (~40 KB needed) → `WiFi Out of Memory`.

### HA entity configuration

In `epaper_ha_client.py`, `ENT` dict:

```python
ENT = {
    "pv_today":   "sensor.pv_production_today_thingspeak_2",
    "pv_now":     "sensor.pv_production_thingspeak",
    "inj_today":  "sensor.injection_reseau_jour",
    # ... 11 more
}
```

**HA template for sunrise/sunset** — known pitfall: the `next_rising` and `next_setting` attributes of `sun.sun` are in **UTC**. Apply the `| as_local` filter in the HA template (DST-aware automatically):

```yaml
template:
  - sensor:
      - name: "Sunrise"
        unique_id: jour_lever
        state: >
          {% set t = as_datetime(state_attr('sun.sun','next_rising')) | as_local %}
          {{ t.strftime('%H:%M') if t else 'unavailable' }}
```

### Charge detection via MAX17048 CRATE register

`battery.py` no longer needs a GPIO to detect USB presence. Instead, it reads the **CRATE register** (0x16) of the MAX17048 which returns the signed slope of % variation in %/hour:

- **CRATE > +0.5 %/h** → active charging (battery icon turns red)
- **CRATE between -0.5 and +0.5 %/h** → idle or weak discharge (black icon)
- **CRATE < -0.5 %/h** → active discharge

```python
def _read_fuel_gauge():
    i2c = I2C(0, scl=Pin(21), sda=Pin(22), freq=100000)
    if MAX17048_ADDR not in i2c.scan():
        raise OSError("MAX17048 absent du bus I2C")
    rv = i2c.readfrom_mem(MAX17048_ADDR, 0x02, 2)   # VCELL
    rs = i2c.readfrom_mem(MAX17048_ADDR, 0x04, 2)   # SOC
    rc = i2c.readfrom_mem(MAX17048_ADDR, 0x16, 2)   # CRATE (signed)
    v   = ((rv[0] << 8) | rv[1]) * 78.125e-6
    soc = ((rs[0] << 8) | rs[1]) / 256.0
    crate_raw = (rc[0] << 8) | rc[1]
    if crate_raw >= 0x8000:
        crate_raw -= 0x10000              # two's complement
    crate = crate_raw * 0.208             # %/h per datasheet
    return v, int(soc + 0.5), crate
```

⏱️ **Convergence time**: the MAX17048 takes **~30-60 seconds** after USB-C plug-in for CRATE to reflect the new slope (sliding average). So immediately after plug, CRATE can still show the previous negative value — this is normal and corrects itself on the next cycle.

### Peak/off-peak schedule (ORES 2026)

```python
def _is_hp(hour):
    # Peak hours: 7-11 AM AND 5-10 PM, every day (weekends included)
    return (7 <= hour < 11) or (17 <= hour < 22)
```

### 30-minute bucketing

24 buckets of 30 min over the last 12 hours, with linear interpolation between irregularly-spaced HA history points (the cumulative monotonic sensor allows clean interpolation).

---

## Configuration

### config.json

```json
{
  "wifi_ssid": "YourNetwork",
  "wifi_pass": "YourPassword",
  "ha_url":    "http://192.168.x.x:8123",
  "ha_token":  "eyJhbGciOiJIUzI1NiIs..."
}
```

### Constants in main.py

```python
REFRESH_SEC   = 600      # 10 minutes between refreshes
DEEP_SLEEP    = True     # False to stay awake (dev)
PORTAL_RENDER = True
```

### Constants in epaper_ha_client.py and display.py

```python
TZ_OFFSET = 2 * 3600     # CEST (Brussels summer time)
                         # CET (winter time) = 1 * 3600
```

### Constants in display_en.py (English version only)

```python
CITY_NAME = "CITYNAME"   # <- replace with your city
```

### Constants in battery.py

```python
I2C_SCL = 21
I2C_SDA = 22
CRATE_CHARGING_THRESHOLD = 0.5   # %/h threshold for charge detection
```

---

## Installation and first boot

### Prerequisites (Mac/Linux)

```bash
pip install mpremote esptool
```

### 1. Flash MicroPython on the ESP32 (one time)

```bash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX erase-flash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX --baud 460800 \
    write-flash -z 0x1000 ESP32_GENERIC-20260406-v1.28.0.bin
```

### 2. Deploy the code (French version)

```bash
python3 -m mpremote cp \
    main.py \
    provisioning.py \
    epaper_ha_client.py \
    display.py \
    battery.py \
    config.json \
    barlow_bold_56.py \
    barlow_bold_40.py \
    barlow_bold_28.py \
    archivo_bold_24.py \
    archivo_bold_13.py \
    :
```

**For the English version**, replace `display.py` with `display_en.py` renamed:

```bash
# Push display_en.py renamed to display.py
python3 -m mpremote cp display_en.py :display.py
```

Verify:

```bash
python3 -m mpremote ls
```

### 3. First boot

```bash
python3 -m mpremote reset
```

To follow the first cycle's logs:

```bash
python3 -m mpremote
# Ctrl+] to exit without rebooting
```

---

## Operating cycle and battery life

### Cycle breakdown (~30 active seconds)

| Step | Duration | ESP32 current |
|---|---|---|
| Boot (hard reset from deep sleep) | 1 s | ~100 mA |
| WiFi connect | 2-4 s | ~150 mA (peaks at 250 mA) |
| NTP sync | 1 s | ~120 mA |
| Fetch 14 HA entities + history | 2-4 s | ~120 mA |
| WiFi off + GC | 1 s | ~80 mA |
| MAX17048 read | < 0.1 s | ~80 mA |
| Compose framebuffer + render ePaper | 20-22 s | ~80 mA |
| Enter deep sleep | < 1 s | — |
| **Total active** | **~30 s** | **~150 mA avg** |

Then deep sleep: **~30 µA** for ~9 min 30.

### Battery life estimate (LiPo 8200 mAh, Lipo Rider Plus boost ~85% efficiency)

| Refresh | Cycles/day | Daily consumption | Battery life |
|---|---|---|---|
| 5 min | 288 | ~360 mAh | ~23 days |
| 10 min | 144 | ~180 mAh | ~46 days |
| 15 min | 96 | ~120 mAh | ~68 days |
| 30 min | 48 | ~60 mAh | ~135 days |

### Real-world measurement (test in progress since June 6, 2026)

| Date / time | Battery % | Voltage | CRATE |
|---|---|---|---|
| June 6, 13:00 | 98% | ~4.18 V | — (starting point) |
| June 8, 13:00 | 87% | 4.06 V | -0.23 %/h average |

Measured slope: **0.23 %/h** over 48h in pure autonomy → **projected real autonomy: ~15-16 days** on a full charge with 10-min refresh. Note the slope typically accelerates below 20% (LiPo S-curve), so complete system shutdown is expected around **June 21-22, 2026**.

---

## Reading the dashboard

(Same structure as French version — refer to the layout mockup above for visual reference.)

- **HEADER**: today's date + city + current PV production (red)
- **LEFT column**: solar production + self-use / export bar + hourly histogram
- **RIGHT column**: grid usage + cost + current rate + temperatures + surplus availability
- **FOOTER**: battery (red when charging or low) + sunrise/sunset + last update timestamp + WiFi RSSI icon

---

## Troubleshooting

### Adafruit ↔ Seeed polarity trap (the most subtle)

🪤 **The pitfall that costs 2 hours**: Adafruit and Seeed use **opposite** polarity conventions on their JST PH 2-pin battery connector. The MAX17048 (Adafruit) expects `+` on pin A, the Lipo Rider Plus (Seeed) expects `+` on pin B.

If you directly link the two connectors with a straight JST PH cable, **the polarity reverses** between the two modules → can't charge the LiPo properly.

**Solution**: insert a **JST PH inverter cable** (custom soldered cable with red↔black wires crossed) between the MAX17048 output and the Lipo Rider Plus input.

**Verification before plugging**:
1. Multimeter in V DC on the MAX17048 JST output → identifies actual polarity (red toward `+` Adafruit)
2. Multimeter in V DC on the Lipo Rider Plus JST input (with USB-C plugged, no LiPo) → reads `+4.22V` on the `+` Seeed side
3. If the two `+` pins are not on the same side of the connector, **the cable must cross**

### MAX17048 not detected (battery.read() returns None)

Checks in order:

1. **SDA/SCL pins swapped** — classic pitfall. Correct physical wiring:
   - `SDA → ESP32 GPIO 22`
   - `SCL → ESP32 GPIO 21`
   - Run `i2c_scan.py` (in the repo) which sweeps the 12 GPIO × HW/SW I²C combinations
2. **Header pins not soldered** on the MAX17048 (Adafruit 5580 modules ship without soldered headers)
3. **Continuity of Dupont wires** with a multimeter
4. **Electrical presence**: voltage between GND and VIN of the MAX17048 should be 3.3V

### `mpremote run` vs `mpremote cp` (the silent pitfall)

🪤 `mpremote run script.py` executes the **local file** on the ESP32 temporarily. It does **not modify the ESP32 flash**.

If you edit `battery.py` locally and run `mpremote run battery.py`, it works. But on the next cycle, `main.py` loads the **old** `battery.py` still on the flash → unchanged behavior.

**Solution**: always `mpremote cp battery.py :battery.py` after a local modification to persist on flash.

### Dashboard didn't refresh overnight

**Most likely historical cause**: USB powerbank auto-shutoff. **Resolved** since switching to the Lipo Rider Plus which keeps the 5V output active continuously (no auto-shutoff under low current).

### "WiFi Out of Memory" on first cycle

ESP-IDF doesn't have enough heap for WiFi buffers. Already handled in code via the WiFi-first / display-last pattern. If it recurs, soft-reset to start from a fresh state.

### Sunrise/sunset offset by 1-2 hours

Apply the `| as_local` filter in the HA template (see *HA entity configuration*).

### Battery icon doesn't turn red when charger is plugged in

The MAX17048 has a **sliding average of ~30-60 seconds** to compute CRATE. After plugging USB-C, wait at least 1 minute before checking — at the next 10-min cycle, the icon will be red if charging is confirmed.

If the icon stays black for multiple cycles while the battery is rising:
- Verify `battery.py` is reading the **CRATE register (0x16)**, not the obsolete `usb_present()` function
- Read console output: `battery: CRATE = +X.XX %/h -> charging=True/False`

### `?` glyphs instead of text

One of the fonts doesn't have the requested character in its charset. Regenerate the font with `font_to_py` passing all needed characters via `-c`.

### Captive portal doesn't work

Experimental on MicroPython 1.28. Workaround: create `config.json` manually and `mpremote cp config.json :`.

### Servicing an autonomous device (frame already mounted)

```bash
# Watch logs live
python3 -m mpremote

# Push a new version
python3 -m mpremote cp <file> :
python3 -m mpremote reset

# Disable autonomy (back to plain REPL)
python3 -m mpremote rm main.py
python3 -m mpremote reset
```

---

## Known limitations

| # | Limitation | Severity | Workaround |
|---|---|---|---|
| 1 | Captive portal broken on MicroPython 1.28 | Minor | Create `config.json` manually |
| 2 | No automatic DST handling for `TZ_OFFSET` | Minor | Manual adjust twice a year |
| 3 | All fonts have partial charsets | Minor | Test before adding new text |
| 4 | ePaper refresh blocks for ~20 s | Inherent | None (physical ink limit) |
| 5 | Adafruit ↔ Seeed JST PH polarity reversed | Major | Custom soldered inverter cable |
| 6 | MAX17048 is ESD-sensitive | Minor | Handle with care, keep a spare |
| 7 | 30-60s delay for CRATE charge detection | Minor | Wait 1 cycle after USB-C plug |
| 8 | Histogram requires `significant_changes_only` | Inherent | Sensor must log ~1 / 15 min minimum |
| 9 | Tight memory margin (~12-15 KB after render) | Major | Watch out when adding features |
| 10 | LiPo plateaus at ~98% (not 100%) | Minor | Normal CC/CV charger behavior, preserves cell |

---

## Appendix A — Source code

### main.py (~120 lines)

Cycle orchestrator. Framebuffer allocation up front, lazy import of `display`, battery reading at end of cycle, error handling and deep sleep at the bottom.

### provisioning.py (~330 lines)

WiFi connection (3 retries) and captive portal fallback.

### epaper_ha_client.py (~250 lines)

HA REST API client. Fetches 14 entities + history for the histogram with linear interpolation.

### display.py / display_en.py (~660 lines)

Both files are identical in structure and API; only UI strings, comments, and number formatting differ. Pick one and ship it as `display.py`.

- `Display`: low-level SPI driver for the UC8179 controller
- `_draw_wifi_icon(d, x, y, rssi)`: smartphone-style WiFi icon
- `_draw_dashboard(...)`: composes the full layout including the unified red battery icon when charging
- `render_dashboard(data, hourly, refresh_min=10, battery=None)`: public entry point
- The battery block uses a single color `icon_color = RED if (charging or is_low) else BLACK` that applies to all elements (body, tip, fill, text)

### battery.py (~110 lines)

- `_read_fuel_gauge()`: I²C scan, reads MAX17048 **VCELL (0x02), SOC (0x04) and CRATE (0x16)** registers
- Two's complement conversion of CRATE → signed %/h via the 0.208 coefficient (datasheet)
- `read()`: returns `{"percent", "voltage", "charging"}` with `charging = (crate > 0.5)` or `None` if gauge absent
- Constants: `I2C_SCL = 21`, `I2C_SDA = 22`, `CRATE_CHARGING_THRESHOLD = 0.5`
- Debug print: `battery: CRATE = +X.XX %/h -> charging=True/False` on each read

### i2c_scan.py (utility in repo)

Diagnostic script that sweeps 12 GPIO × HW/SW I²C combinations to identify the config that detects the MAX17048.

### Fonts

Same as French version.

---

## Appendix B — Enclosure

**Adopted solution: wooden photo frame ~17×22 cm with custom passe-partout** ✅

Final integration uses a consumer wooden photo frame (purchased at a hardware store / supermarket for ~2-15 €). Minimum specs:

- **Inside dimensions**: ≥ 17 × 22 cm to fit the panel (170 × 112 mm)
- **Inside depth**: ≥ 25 mm (ideal 30 mm for comfort)
- **Removable back**: essential for accessing the electronics
- **Off-white or cream passe-partout (mat board)**: 1.5-2 mm thick, cut to expose the active area (163 × 98 mm)

### Internal layout (rear view)

```
┌───────────────────────────────────────┐
│                                       │
│  ┌─────────┐  ┌────────────────────┐ │
│  │  LiPo   │  │  ESP32 driver      │ │  ← stuck with foam double-sided tape
│  │ 75×65mm │  │  board + FFC ribbon│ │
│  └─────────┘  └────────────────────┘ │
│                                        │
│  ┌─────────┐    ┌─────────┐           │
│  │MAX17048 │    │Lipo     │           │
│  │         │    │Rider Plus│          │
│  └─────────┘    └─────────┘           │
│       │                                │
│       └── 4 I²C Dupont wires ──────────┘
│           to ESP32                      │
│                                         │
│       USB-C charger cable exits         │
│       through a discreet hole at        │
│       the bottom of the frame           │
│                                         │
└───────────────────────────────────────┘
```

### Depth validation (25-30 mm frame)

| Element | Thickness |
|---|---|
| Frame front plastic glazing | ~1 mm |
| Passe-partout (mat board) | 1.5-2 mm |
| Raw 7.5" ePaper panel | 0.91 mm |
| FFC ribbon bend radius | ~3 mm |
| LiPo HXJNLDC 8200 mAh | 12 mm |
| ESP32 driver board | ~5 mm |
| Lipo Rider Plus + MAX17048 | ~5 mm each |
| Foam shim + back cardboard | ~2 mm |

Side-by-side layout (not stacked): dominant thickness = LiPo (12 mm) + ~5 mm boards = **~17 mm used** in the 25 mm frame. 8 mm margin for cables and FFC bend.

### Integration steps

1. **Prepare the passe-partout**: cut the window to 163 × 98 mm
2. **Stick the panel against the glazing** with thin (1 mm) foam double-sided tape
3. **Place the battery** on the left side with 3 mm foam double-sided tape
4. **Place the ESP32 driver board** in the center/right with its double-sided tape
5. **Wire the energy chain**: LiPo → polarity adapter → MAX17048 → inverter cable → Lipo Rider Plus → USB-A to ESP32
6. **Wire the I²C**: 4 Dupont wires between MAX17048 and ESP32 (3V3, GND, P22 SDA, P21 SCL)
7. **Optionally solder Lipo Rider Plus pins** for direct 5V/GND wiring (alternative to USB-A→USB-C cable)
8. **Route the USB-C charger cable** through a discreet hole at the bottom of the frame (~5 mm diameter)
9. **Close the back**: foam shim + back cardboard, frame clips

**Total enclosure cost**: ~5-10 € with an IKEA / supermarket frame.

---

## Appendix C — Roadmap & ideas

### Done ✅

- [x] Complete software (5 MicroPython modules + 5 fonts)
- [x] Charge detection via MAX17048 CRATE register (no GPIO USB-detect needed)
- [x] Battery integration in main.py + display.py (red icon when charging)
- [x] Complete autonomous hardware: LiPo + Lipo Rider Plus + MAX17048
- [x] Chinese→Adafruit polarity adapter cable
- [x] Adafruit→Seeed JST PH inverter cable
- [x] Final integration in wooden photo frame with passe-partout
- [x] Bilingual version (FR + EN) of the dashboard

### In progress 🔬

- [ ] Full single-charge autonomy test (started June 6, 2026 at 98%, system shutdown expected ~June 21-22)

### Short term

- [ ] Solder Lipo Rider Plus 5V/GND pins for direct ESP32 wiring (eliminates the USB-A→USB-C deleyCON cable)
- [ ] Design a custom carrier PCB (KiCad) for clean final integration
- [ ] Compile Python modules to `.mpy` with `mpy-cross` to save ~30% RAM

### Medium term

- [ ] Lipo Rider Plus EN pin controlled by ESP32 GPIO to cut the boost in deep sleep → +30% expected autonomy
- [ ] DNS hijack in the captive portal for auto-redirect on iOS/Android
- [ ] Fix the captive portal (probably wait for MicroPython 1.29+)
- [ ] Display tomorrow's weather forecast

### Exploratory ideas

- [ ] Physical button to force a refresh (GPIO wake from deep sleep)
- [ ] "Night" mode with 30 min refresh between 11 PM - 6 AM
- [ ] Detailed statistics on long button press (weekly self-use, cumulative savings)
- [ ] HA bidirectional integration (push from HA → force refresh via MQTT)
- [ ] Multi-page: alternate energy / weather / calendar
- [ ] XL version with 13" / 800×1280 panel

---

*Last updated: June 8, 2026 — version 4.0 (hardware finalized: Lipo Rider Plus + MAX17048 in service, charge detection via CRATE register, red battery icon when charging, complete wooden frame integration, I²C pinout correction SDA→GPIO22/SCL→GPIO21)*
