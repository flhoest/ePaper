# GNI ePaper Dashboard

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
- **Autonomie batterie** — l'ESP32 dort ~99 % du temps (~30 µA en deep sleep) et ne se réveille que toutes les 10 minutes pour rafraîchir l'écran. Sur LiPo 8200 mAh avec boost converter, on table sur ~65 jours d'autonomie à 10 min de refresh.

Les données proviennent d'une instance Home Assistant locale via son API REST. Pas de dépendance cloud, pas d'abonnement.

---

## Matériel

### Composants principaux (en service)

| Élément | Référence / modèle | Rôle |
|---|---|---|
| Dalle e-paper | Waveshare 7,5" B V2 (BWR 800×480) | Affichage tricolore noir / blanc / rouge |
| Carte de pilotage | Waveshare ESP32 e-Paper Driver Board (USB-C) | SPI vers la dalle + WiFi + deep sleep |
| Câble nappe | Inclus avec la dalle | FFC 24 broches |

### Composants énergie (assemblage à finaliser)

| Élément | Référence | Statut |
|---|---|---|
| Batterie LiPo 1S | Fayerkar 8200 mAh, PCM intégrée, JST PH | Reçue |
| Module de charge USB-C | TP4056 + protection (Amazon B0BZSB3SBN) | Reçu |
| Boost converter 5V | Aihasd 0,9-5V → 5V (pack de 5, B07HB3C13D) ou 134N3P 5V 1A | **À recevoir** |
| Jauge de charge | Adafruit MAX17048 (I²C 0x36, ref Adafruit 5580) | **Commandée** |

### Brochage ESP32 → dalle e-paper

| Signal dalle | Pin ESP32 |
|---|---|
| CLK (SPI clock) | GPIO 13 |
| DIN (MOSI) | GPIO 14 |
| CS  | GPIO 15 |
| DC  | GPIO 27 |
| RST | GPIO 26 |
| BUSY | GPIO 25 |

### Brochage I²C pour la jauge MAX17048 (à venir)

| Signal | Pin ESP32 |
|---|---|
| SDA | GPIO 21 |
| SCL | GPIO 22 |
| VCC | 3,3 V |
| GND | GND |

### Câblage de l'alimentation cible

```
                 USB-C  ◀─── chargeur secteur / port USB
                   │
                   ▼
              TP4056 (charge & protection)
                   │
                   ▼
              LiPo 8200 mAh ──► Boost 5V ──► ESP32 (entrée USB-C)
                                  ▲
                                  │
                          MAX17048 (I²C, mesure %)
```

Pour l'instant l'alimentation se fait directement sur USB-C depuis un chargeur secteur ou un powerbank — voir [Dépannage](#dépannage) pour les pièges du powerbank.

---

## Maquette

Layout 800 × 480 px, deux colonnes séparées par un trait vertical fin :

```
┌─────────────────────────────────────────────────────────────────────┐
│ VEN. 29 MAI                                              0,0 kW     │
│ CERFONTAINE                                       PRODUCTION PV-    │
│                                                   MAINTENANT        │
│─────────────────────────────────────────│ ─────────────────────────│
│ ■ PRODUCTION SOLAIRE                    │ ■ RESEAU                  │
│ PRODUIT AUJOURD'HUI    INJECTE RESEAU   │ CONSOMME.JOUR  COUT.JOUR  │
│ 18,3 kWh               5,7 kWh          │  8,4 kWh        2,53 EUR  │
│                                         │ ┌─────────────────────────┐│
│ AUTOCONSOMME 69%         INJECTE 31%    │ │ TARIF EN COURS      HC ││
│ █████████████░░░░░░░░░░░░               │ └─────────────────────────┘│
│                                         │                            │
│ PRODUCTION HORAIRE        ■HP ■HC       │ ■ TEMPERATURES             │
│      █                                  │ EXTERIEUR     BUANDERIE    │
│      █ █                                │  20,7°         24,6°       │
│      █ █ █ █                            │                            │
│  █ █ █ █ █ █ █ █                        │ ┌──── ■ SURPLUS ──────────┐│
│  █ █ █ █ █ █ █ █ █ █                    │ │                         ││
│  12h    15h    18h    21h               │ │       INSUFFISANT       ││
│─────────────────────────────────────────│ └─────────────────────────┘│
│ [🔋 73%] LEVER 03:36 - COUCHER 19:44   HOME ASSISTANT - MAJ 29/05 - 23:45 (refresh 10 min) 📶│
└─────────────────────────────────────────────────────────────────────┘
```

Couleurs : **rouge** pour les valeurs et alertes importantes (production solaire, tarif HP, température extérieure, surplus dispo, batterie faible) ; **noir** pour tout le reste.

L'histogramme en bas à gauche montre la production demi-horaire sur les 12 dernières heures (24 barres de 30 min). Les barres en HP sont rouges, en HC noires. Labels seulement à 12h, 15h, 18h, 21h pour rester lisible.

L'icône WiFi en bas à droite (style smartphone : point + 3 arcs en éventail) indique la force du signal RSSI mesurée pendant le cycle. Nombre d'arcs pleins selon les seuils dBm : 3 (excellent, > -55), 2 (bon, -55 à -70), 1 (faible, -70 à -85), 0 (mauvais, < -85).

---

## Architecture logicielle

Quatre modules Python sur la flash de l'ESP32, plus les modules de fonts compilés :

```
/
├── main.py                  ← orchestrateur du cycle complet
├── provisioning.py          ← WiFi (config.json) ou portail captif
├── epaper_ha_client.py      ← API Home Assistant + bucketing histogramme
├── display.py               ← pilote UC8179 + layout dashboard
├── battery.py               ← jauge MAX17048 (lecture %, charging)
├── config.json              ← credentials WiFi + URL/token HA
├── barlow_bold_56.py        ← font "héro" (hour value du PV)
├── barlow_bold_40.py        ← font "big" (date, pv_now, surplus)
├── barlow_bold_28.py        ← font "medium" (chiffres secondaires)
├── archivo_bold_24.py       ← font écrans de statut
└── archivo_bold_13.py       ← font "label" (titres et footer)
```

### Le cycle (main.py)

1. **Pré-allocation framebuffer** (avant tout import non-trivial) — `bytearray(48000)` est alloué en premier dans la heap MicroPython pour éviter la fragmentation. Ce buffer servira à la composition de l'image avant envoi à la dalle.

2. **WiFi connect** — `provisioning.ensure_provisioned()` lit `config.json` et connecte le STA. Si `config.json` est absent ou WiFi inaccessible, bascule en mode portail captif (cf. limitations).

3. **Récupération HA** — `epaper_ha_client.fetch_dashboard()` interroge les 14 entités configurées en parallèle (1 requête REST chacune, GET `/api/states/<entity_id>`), puis `hourly_buckets()` interroge l'historique pour reconstruire l'histogramme demi-horaire.

4. **Libération réseau** — `WLAN.active(False)` pour récupérer la RAM ESP-IDF, puis `gc.collect()` côté Python.

5. **Lecture batterie** — `battery.read()` interroge le MAX17048 en I²C (renvoie `None` si pas câblé, sans erreur).

6. **Rendu ePaper** — `display.render_dashboard(data, hourly, refresh_min, battery)` charge les polices, compose le framebuffer 48 Ko (plan noir + plan rouge), envoie à la dalle, attend le refresh (~20 s), met la dalle en deep sleep.

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

Le filtre `| as_local` convertit le datetime de UTC vers la timezone configurée dans HA (Paramètres → Système → Général). Sans ce filtre, le dashboard affichera des heures décalées de 1-2 h.

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

---

## Installation et premier démarrage

### Pré-requis (Mac/Linux)

```bash
pip install mpremote esptool
```

### 1. Flasher MicroPython sur l'ESP32 (une seule fois)

```bash
# Mettre l'ESP32 en mode bootloader (maintenir BOOT, presser RESET, relâcher BOOT)
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX erase_flash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX --baud 460800 \
    write_flash -z 0x1000 ESP32_GENERIC-20251215-v1.28.0.bin
```

Le firmware doit être MicroPython >= 1.23 (testé sur 1.28). Télécharger sur https://micropython.org/download/ESP32_GENERIC/.

### 2. Déployer le code

Tous les fichiers à mettre sur la flash :

```bash
python3 -m mpremote cp main.py provisioning.py epaper_ha_client.py \
                      display.py battery.py \
                      barlow_bold_56.py barlow_bold_40.py \
                      barlow_bold_28.py archivo_bold_24.py \
                      archivo_bold_13.py \
                      config.json :
```

Vérifier :

```bash
python3 -m mpremote ls
```

### 3. Premier boot

D�brancher / rebrancher l'USB-C, ou :

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
| Compose framebuffer + render ePaper | 20-22 s | ~80 mA (pic à 50 mA pendant refresh) |
| Entrée deep sleep | < 1 s | — |
| **Total actif** | **~30 s** | **~150 mA moyen** |

Puis deep sleep : **~30 µA** pendant ~9 min 30.

### Estimation autonomie (LiPo 8200 mAh, boost 80% rendement)

| Refresh | Cycles/jour | Conso jour | Autonomie |
|---|---|---|---|
| 5 min | 288 | ~360 mAh | ~23 jours |
| 10 min | 144 | ~180 mAh | ~46 jours |
| 15 min | 96 | ~120 mAh | ~68 jours |
| 30 min | 48 | ~60 mAh | ~135 jours |

À 10 min, c'est l'équivalent de presque 7 semaines sans recharger. À 15 min, plus de 2 mois. C'est le compromis recommandé : on n'a pas besoin de l'info à la minute près, mais une fois par quart d'heure suffit pour décider de brancher un équipement quand le soleil est bon.

### Comportement en cas d'erreur

| Erreur | Comportement |
|---|---|
| WiFi inaccessible (3 retries) | Écran d'erreur affiché, retry dans 2 min |
| HA inaccessible | Écran d'erreur affiché, retry dans 2 min |
| Une seule entité absente | Affichage `--` à la place de la valeur, cycle normal |
| MemoryError pendant le rendu | Écran d'erreur, retry dans 2 min |
| OOM avant le rendu | Reboot complet via watchdog (~5 s) |
| config.json absent | Bascule en portail captif (cf. limitations) |

L'écran ne reste donc jamais figé sur de l'info périmée : soit une vraie mise à jour, soit un message d'erreur explicite avec la date du dernier essai.

---

## Lecture du dashboard

### Zone HEADER (haut)

- **Date du jour** en grand à gauche (`VEN. 29 MAI`)
- **Localité** (`CERFONTAINE`) en petit dessous
- **Production PV actuelle** en grand rouge à droite (`2,4 kW`) — c'est l'info que tu regardes en premier le matin pour voir si le soleil est généreux

### Colonne GAUCHE : production solaire

- **Produit aujourd'hui** : cumul depuis 00:00 en kWh
- **Injecté réseau** : cumul depuis 00:00 en kWh (ce que tu as renvoyé au réseau parce que tu en produisais plus que tu en consommais)
- **Barre autoconsommé / injecté** : split visuel du jour. Plus la zone noire (autoconsommé) est large, mieux c'est financièrement.
- **Histogramme production horaire** : courbe du jour. 24 barres = les 12 dernières heures par tranche de 30 min. Les barres en heures pleines (7-11h et 17-22h) sont **rouges**, en heures creuses **noires**. Permet de voir d'un coup d'œil :
  - Si la matinée a été productive
  - Si un nuage est passé à 14h
  - Si on est dans la phase de production déclinante de fin de journée

### Colonne DROITE : réseau, températures, surplus

- **Consommé jour** : kWh achetés au réseau depuis 00:00 (HP + HC additionnés)
- **Coût jour** : euros depuis 00:00 selon la grille ORES 2026
- **Tarif en cours** : `HC` (heures creuses, fond blanc) ou `HP` (heures pleines, fond rouge). Sert à décider si tu lances la machine maintenant ou si tu attends 22h.
- **Températures** : extérieur (rouge, pour attirer l'œil — c'est l'info "habille-toi en partant") et buanderie (noir).
- **Encadré SURPLUS** : la zone la plus importante du dashboard.
  - Si `binary_sensor.surplus_solaire_stable` est ON et que `surplus_kw > 0,05` → affichage `X,X kW DISPONIBLE` en grand rouge → tu peux brancher la voiture, démarrer le lave-vaisselle, etc.
  - Sinon → `INSUFFISANT` en grand noir → laisse tomber, le surplus n'est pas stable

### Zone FOOTER (bas)

- **Batterie** (gauche, si la jauge MAX17048 est câblée) : icône batterie + `XX%` + mention `USB` en rouge si en charge. Pictogramme rouge si batterie < 20 %.
- **Lever / Coucher du soleil** (centre gauche)
- **Source + horodatage + intervalle refresh** (droite) — sert à voir si le dashboard est à jour ou s'il est figé depuis 3 h pour une raison X.
- **Force du signal WiFi** (extrême droite) : icône style smartphone (point central + arcs en éventail). Nombre d'arcs pleins indique la réception au moment du dernier fetch HA :
  - 3 arcs : signal excellent (> -55 dBm)
  - 2 arcs : signal bon (-55 à -70 dBm)
  - 1 arc : signal faible (-70 à -85 dBm)
  - point seul : signal mauvais (< -85 dBm) — le dashboard a probablement du mal à fetcher HA
  - icône absente : le RSSI n'a pas pu être lu (ne devrait jamais arriver en mode dashboard puisque le WiFi est forcément actif)

---

## Dépannage

### Le dashboard ne s'est pas rafraîchi cette nuit

**Cause la plus probable** : **auto-shutoff du powerbank USB**. Tous les powerbanks USB grand public ont un mode "économie" qui coupe la sortie quand le courant tiré tombe sous un seuil (typiquement 50-100 mA). En deep sleep l'ESP32 ne tire que ~30 µA, donc le powerbank croit que rien n'est branché et coupe.

**Vérifications** :
- Tester sur une alimentation secteur (chargeur USB-C) → si pas de problème pendant 24 h, c'est confirmé
- Sur certains powerbanks, double-cliquer le bouton active un mode "small device" / "trickle mode"

**Solution propre** : finir l'assemblage hardware avec le boost converter. LiPo → Boost 5V → ESP32 ne souffre pas d'auto-shutoff (le boost converter tire en continu).

### "WiFi Out of Memory" au premier cycle

ESP-IDF n'a pas assez de heap pour les buffers WiFi. Causes possibles :
- Un cycle précédent n'a pas libéré le WiFi proprement (réseau ou socket zombie)
- L'ordre des allocations en Python a privé ESP-IDF de RAM

**Solution** : déjà géré côté code par le pattern WiFi-first / display-last. Si récidive, soft-reset (`machine.reset()`) ou physique (débrancher/rebrancher) pour repartir d'un état frais.

### Lever / coucher du soleil décalés de 1-2 heures

Cause : le template HA qui produit ces sensors lit `state_attr('sun.sun','next_rising')` qui renvoie un timestamp ISO **en UTC**. Si le template fait juste `strftime('%H:%M')` sur ce timestamp, il ressort tel quel en UTC, sans conversion vers la timezone locale.

Fix : appliquer le filtre `| as_local` dans le template HA (voir section *Configuration des entités HA*). Aucune modification du code dashboard nécessaire — au prochain cycle, les bonnes valeurs apparaîtront automatiquement. Bonus : DST géré automatiquement par HA (hiver UTC+1, été UTC+2).

### Histogramme avec des barres bizarres

Si tu vois des écarts louches entre l'histogramme et la courbe HA :
- Vérifier que `TZ_OFFSET` est correct (2*3600 en été, 1*3600 en hiver)
- Vérifier dans les logs `hourly_buckets:` que le `GET .../history/period/...` couvre bien la bonne fenêtre

L'interpolation linéaire entre points historiques est sensible aux trous. Si HA n'a logué qu'un point par heure, l'interpolation reste correcte mais l'incertitude grandit. `significant_changes_only` est activé pour ne pas surcharger la requête.

### Glyphes `?` à la place du texte

L'une des polices `barlow_bold_XX.py` n'a pas le caractère demandé dans son charset. Les fonts sont générées avec `font_to_py` sur un sous-ensemble pour économiser la RAM.

**Solution rapide** : utiliser une autre police déjà chargée qui a le glyphe (typiquement F_BIG = barlow_bold_40 a presque tout l'alphabet).

**Solution propre** : regénérer la police avec `font_to_py -c "AÀBCD...stuvw...0123456789,. " barlow-bold.ttf 28 barlow_bold_28.py` en passant tous les caractères nécessaires en `-c`.

### Le portail captif ne fonctionne pas

Le mode portail captif (`PORTAL_RENDER=True`, déclenché quand `config.json` est absent) est **expérimental sur MicroPython 1.28**. Symptôme : l'AP `GNI-ePaper-Setup` est visible mais le téléphone ne reçoit pas d'IP par DHCP.

**Workaround pour l'instant** : créer `config.json` à la main avec un éditeur de texte, puis `mpremote cp config.json :`. C'est 30 secondes de boulot la première fois et c'est tout.

### Intervenir sur un device autonome

```bash
# Voir les logs en direct (interrompt le deep sleep si on est entre 2 cycles)
python3 -m mpremote
# Ctrl+] pour quitter

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
| 2 | Pas de gestion DST automatique pour `TZ_OFFSET` côté ESP32 | Mineur | Ajuster manuellement 2 fois par an (lever/coucher sont DST-aware côté HA via `as_local`) |
| 3 | Tous les fonts en charset partiel | Mineur | Tester avant de mettre un nouveau texte ; regénérer la police si besoin |
| 4 | Refresh ePaper bloque pendant ~20 s | Inhérent | Aucun (limite physique de l'encre) |
| 5 | Powerbank auto-shutoff incompatible avec deep sleep | Majeur | Utiliser une alim secteur ou un setup LiPo + boost dédié |
| 6 | Aucune mesure batterie tant que le MAX17048 n'est pas câblé | Mineur | `battery.read()` retourne `None` → footer n'affiche pas l'info |
| 7 | Histogramme nécessite `significant_changes_only` sur le sensor cumulatif | Inhérent | Le sensor doit logguer assez de points (~1/15 min minimum) |
| 8 | Marge mémoire serrée (~12-15 Ko libres après render) | Majeur | À surveiller si on ajoute des features. Compilation en `.mpy` recommandée si on touche au plafond |

---

## Annexe A — Code source

Tous les fichiers sont dans `/mnt/user-data/outputs/` (côté sandbox) et sur la flash de l'ESP32 (côté production).

### main.py (~110 lignes)

Orchestrateur du cycle. Allocation framebuffer en tête (anti-fragmentation), import lazy de `display`, gestion des erreurs et deep sleep en bas.

### provisioning.py (~330 lignes)

- `connect_sta(cfg, timeout=20)` : 3 retries avec `esp.osdebug(None)`, `AP_IF.active(False)` explicite, `gc.collect()`, diagnostic ESP-IDF heap pour debug.
- `start_portal(...)` : monte un AP `GNI-ePaper-Setup` (ouvert, channel 6, max_clients 1), serveur HTTP minimal, scan WiFi pour proposer les SSID, génère `config.json` puis reboot.
- `ensure_provisioned(on_portal_start)` : enchaîne `connect_sta` puis fallback `start_portal` si `config.json` est absent ou les credentials sont obsolètes.

### epaper_ha_client.py (~250 lignes)

- `sync_time()` : appel NTP, mise à jour de l'horloge interne
- `_get(path)` : helper GET vers l'API HA avec retry et timeout
- `_parse_iso_utc(s)` : parse les timestamps ISO renvoyés par HA
- `fetch_dashboard()` : récupère les 14 entités et compose le dict pour le rendu. Inclut la capture du `wifi_rssi` via `network.WLAN(network.STA_IF).status("rssi")` pendant que la connexion est encore active.
- `hourly_buckets(entity, nb=24, bucket_min=30)` : récupère l'historique, interpole linéairement entre les points, retourne la liste des 24 valeurs demi-horaires sur les 12 dernières heures

### display.py (~660 lignes)

- Constantes layout (WIDTH, HEIGHT, MARGIN, LX, LW, RX, RW, BULLET, etc.)
- `Display` : pilote SPI bas niveau pour le contrôleur UC8179 (init, plan noir, plan rouge, refresh, sleep)
- `Display.text_pro(s, x, y, font, color)` : rendu de texte glyph-par-glyph en MONO_HLSB
- `_is_hp(hour)` : grille tarifaire ORES 2026 (HP : 7-11h et 17-22h, tous les jours)
- `_fr(x, decimals)` : format français des nombres (virgule au lieu du point)
- `_draw_wifi_icon(d, x, y, rssi)` : icône WiFi style smartphone (point + 3 arcs concentriques en éventail), tracée comme polyligne épaisse pour des courbes nettes. Bounding box 30×22 px. Seuils dBm pour le nombre d'arcs : -55 / -70 / -85.
- `_draw_dashboard(d, data, hourly, now, refresh_min, battery, F_HERO, F_BIG, F_MED, F_LAB)` : compose le layout complet
- `render_dashboard(data, hourly, refresh_min=10, battery=None)` : entry point publique
- `render_status(title, lines, color=BLACK)` : écrans génériques pour erreurs / portail / boot
- `render_portal_screen(ssid, password)` : écran info quand le device est en mode portail
- `render_error(title, msg, retry_min)` : écran d'erreur avec délai de retry
- `demo_dashboard()` : test en local avec data mockée (utile pour itérer sur le layout)

### battery.py (~80 lignes)

- `_read_fuel_gauge()` : I²C `scan()` puis lecture registres VCELL et SOC du MAX17048
- `_read_adc()` : fallback ADC sur GPIO34 si pas de fuel gauge (moins précis)
- `usb_present()` : détection présence USB via GPIO (à câbler)
- `read()` : retourne `{"percent", "voltage", "charging"}` ou `None` si jauge absente
- `status_text()` : helper texte affichable

### Fonts (générées avec font_to_py de Peter Hinch)

- `barlow_bold_56.py` (13 Ko) — chiffres + lettres header
- `barlow_bold_40.py` (23 Ko) — date, pv_now, surplus
- `barlow_bold_28.py` (8 Ko) — chiffres secondaires
- `archivo_bold_24.py` (31 Ko) — écrans de statut
- `archivo_bold_13.py` (13 Ko) — labels et footer

Pour regénérer avec un charset différent :

```bash
font_to_py -c "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-/:°€%" \
           -x Barlow-Bold.ttf 28 barlow_bold_28.py
```

L'option `-x` est importante : produit du MONO_HLSB (compatible avec `Display.text_pro`).

---

## Annexe B — Boîtier

Trois options du moins au plus engageant :

### Option 1 (recommandée) : cadre IKEA RÖDALM 21×30 cm

- Cadre photo en panneau de fibres de bois + papier métallisé, dispo en blanc et autres coloris
- **Dimensions extérieures** : 23×32 cm, **profondeur intérieure 3 cm (30 mm)**
- **Surface utile sans passe-partout : 21×30 cm** — la dalle 7,5" fait 17×11 cm, donc elle loge dedans avec une marge propre de 2 cm de chaque côté
- 3 cm de profondeur = pile poil pour loger la carte ESP32 driver board derrière la dalle, plus le câble USB-C
- Design pensé pour placer la photo « à l'avant ou à l'arrière du cadre » → tu choisis si la dalle est plein contre la vitre (recommandé pour le contraste) ou en retrait
- Dos renforcé contre la déformation d'après IKEA
- Référence Belgique : 105.488.86 — **4,99 €**

#### Validation profondeur (30 mm disponibles)

| Élément | Épaisseur | Source |
|---|---|---|
| Vitre plastique avant du cadre | ~1 mm | RÖDALM |
| Dalle ePaper raw 7,5" | **0,91 mm** | Spec Waveshare officielle : 170,2 × 111,2 × 0,91 mm |
| Carte ESP32 driver board (PCB + USB-C) | ~5 mm | PCB 1,6 mm + connecteur USB-C ~3 mm au-dessus |
| LiPo Fayerkar 8200 mAh | **~12-15 mm** | Typique pour un 1S 8000+ mAh — **à vérifier au pied à coulisse à la réception du pack** |
| Rayon de pliage du FFC ribbon | ~3 mm | Recommandation Waveshare pour préserver le ribbon |
| Petites cartes (TP4056, MAX17048, boost 5V) | 4-7 mm | Glissées dans les coins libres |
| Mousse de calage + back carton | ~2 mm | Calage + fond du cadre |

**Astuce layout : tout sauf empiler**

La carte ESP32 (~80×30 mm) ne couvre qu'une petite partie de la surface derrière la dalle (170×111 mm). Le LiPo (~100×55 mm) doit donc être placé **à côté** de la carte ESP32, pas derrière elle :

```
┌───────────────────────────────┐  ← vue depuis l'arrière du cadre
│                               │
│   [zone libre 100×80 mm]      │  ← coller le LiPo ici à plat
│                               │
│  ┌──────────────────────────┐ │
│  │  driver board ESP32      │ │  ← contre la dalle, ribbon vers le coin
│  └──────────────────────────┘ │
│                               │
└───────────────────────────────┘
```

Avec ce layout côte-à-côte, l'épaisseur maximale est celle de la batterie (12-15 mm), pas la somme dalle + batterie + driver. Bilan :

```
1 mm  (vitre plastique avant)
+ 1 mm  (dalle ePaper)
+ 15 mm (LiPo, pire cas — driver board passe en parallèle)
+ 3 mm  (rayon FFC ribbon)
+ 2 mm  (mousse de calage)
+ 1 mm  (back carton)
= 23 mm  →  marge de 7 mm sur les 30 mm dispo. OK.
```

**Si le LiPo s'avère plus épais** (> 18 mm en mesure réelle), 3 alternatives :
- Sortir le LiPo du cadre (boîtier déporté avec câble qui passe par le bas)
- Passer à 2× LiPo 4000 mAh ~10 mm en parallèle = 8000 mAh à plat
- Passer au RÖDALM **30×40 cm** (mêmes 30 mm de profondeur, mais surface dispo qui permet d'étaler les composants plus librement)

#### Étapes d'intégration

1. Enlever le passe-partout (la dalle remplit déjà toute la zone visuelle)
2. Découper le carton du fond au cutter pour loger la carte ESP32 (laisser passer le FFC ribbon vers la dalle)
3. Caler la dalle contre la vitre avec du double-face mousse fine (1 mm) sur les bords
4. Coller le LiPo à côté de la carte ESP32 (double-face mousse 3M)
5. Découper un trou discret dans le bas du cadre pour le câble USB-C de charge (ou interrupteur si version batterie pure)
6. Refermer le cadre, c'est fini

**Avantages** : 5 € de matos, mise en œuvre en 1h, intégration salon discrète, pas de 3D printing.
**Inconvénient** : épaisseur finale 3,2 cm sur le mur — pour ouvrir et accéder à l'électronique il faut démonter le fond (clips ou agrafes IKEA).

### Option 2 : boîtier 3D imprimé

Fichier `epaper_case.py` (OpenSCAD ou FreeCAD) à générer / customiser :

- 195 × 280 × 22 mm extérieur
- Fenêtre de visu 800×480 px = 165 × 100 mm
- Logement carte ESP : 50 × 70 mm avec passage USB-C
- Logement LiPo 8200 mAh : 110 × 65 × 10 mm
- Vis M3 ou clip d'assemblage
- Imprimer en PETG (résistance UV, pas de gauchissement quand exposé au soleil derrière une fenêtre)

### Option 3 : sandwich plexi laser

- 2 plaques de plexi 3 mm découpées laser : avant (avec fenêtre de visu) + arrière (fermée)
- Spacers en alu ou nylon de 22 mm aux 4 coins
- Vis M3 longues qui traversent l'ensemble
- Très propre visuellement, totalement transparent → laisse voir le câblage si on aime
- Inconvénient : coût accès laser, dimensions à faire valider avant la coupe

---

## Annexe C — Roadmap & idées

### À court terme

- [ ] Recevoir le boost converter 5V (Aihasd ou 134N3P)
- [ ] Recevoir la jauge MAX17048
- [ ] Câbler le tout (LiPo + TP4056 + boost + MAX17048) et tester 48h
- [ ] Vérifier autonomie réelle vs estimée
- [ ] Imprimer / acheter le boîtier

### À moyen terme

- [ ] Compiler les modules Python en `.mpy` avec `mpy-cross` pour économiser ~30 % de RAM (utile si on veut ajouter des features)
- [ ] DNS hijack dans le portail captif pour pop-up auto-redirect sur iOS/Android
- [ ] Fix du portail captif (probablement attendre MicroPython 1.29 ou 1.30 qui corrigeront la régression WiFi 1.28)
- [ ] Affichage de la prévision météo du lendemain (besoin d'ajouter une entité HA)

### Idées exploratoires

- [ ] Bouton physique sur la carte pour forcer un refresh sans attendre les 10 min (réveil par GPIO en deep sleep)
- [ ] Mode "nuit" avec refresh à 30 min ou désactivé entre 23h et 6h pour économiser la batterie
- [ ] Page de statistiques détaillées sur appui long du bouton (autoconso semaine, économie cumulée, etc.)
- [ ] Intégration au tableau Home Assistant avec mqtt remote command (push depuis HA → forcer un refresh)
- [ ] Multi-page : alterner dashboard énergie / dashboard météo / dashboard agenda à chaque cycle
- [ ] Version XL avec dalle 13" / 800×1280 si Waveshare en sort un jour à prix raisonnable

---

*Dernière mise à jour : 30 mai 2026 — version 2.1 (icône WiFi RSSI dans le footer + capture rssi côté client HA + fix template HA lever/coucher avec `as_local` + validation profondeur RÖDALM)*

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
- **Battery life** — the ESP32 sleeps ~99 % of the time (~30 µA in deep sleep) and only wakes every 10 minutes to refresh the display. On an 8200 mAh LiPo with a boost converter, expected battery life is ~65 days at a 10-minute refresh interval.

Data comes from a local Home Assistant instance via its REST API. No cloud dependency, no subscription.

---

## Hardware

### Main components (in service)

| Item | Reference / model | Role |
|---|---|---|
| E-paper panel | Waveshare 7.5" B V2 (BWR 800×480) | Tricolor black / white / red display |
| Driver board | Waveshare ESP32 e-Paper Driver Board (USB-C) | SPI to panel + WiFi + deep sleep |
| Ribbon cable | Included with the panel | FFC 24 pins |

### Power components (assembly to finalize)

| Item | Reference | Status |
|---|---|---|
| LiPo 1S battery | HXJNLDC 8200 mAh, integrated PCM, JST PH | Received |
| USB-C charging module | TP4056 + protection (Amazon B0BZSB3SBN) | Received |
| 5V boost converter | TPS61023 recommended, or MT3608 | **To order** |
| Fuel gauge | Adafruit MAX17048 (I²C 0x36, Adafruit part 5580) | **On order** |

### ESP32 → e-paper panel pinout

| Panel signal | ESP32 pin |
|---|---|
| CLK (SPI clock) | GPIO 13 |
| DIN (MOSI) | GPIO 14 |
| CS  | GPIO 15 |
| DC  | GPIO 27 |
| RST | GPIO 26 |
| BUSY | GPIO 25 |

### I²C pinout for the MAX17048 fuel gauge (upcoming)

| Signal | ESP32 pin |
|---|---|
| SDA | GPIO 21 |
| SCL | GPIO 22 |
| VCC | 3.3 V |
| GND | GND |

### Target power wiring

```
                 USB-C  ◀─── wall charger / USB port
                   │
                   ▼
              TP4056 (charge & protection)
                   │
                   ▼
              LiPo 8200 mAh ──► Boost 5V ──► ESP32 (USB-C input)
                                  ▲
                                  │
                          MAX17048 (I²C, % reading)
```

For now the device is powered directly via USB-C from a wall charger or powerbank — see [Troubleshooting](#troubleshooting) for the powerbank pitfalls.

---

## Layout mockup

800 × 480 px layout, two columns separated by a thin vertical line:

```
┌─────────────────────────────────────────────────────────────────────┐
│ FRI. 29 MAY                                              0.0 kW     │
│ CITYNAME                                          PV PRODUCTION -   │
│                                                   NOW               │
│─────────────────────────────────────────│ ─────────────────────────│
│ ■ SOLAR PRODUCTION                      │ ■ GRID                    │
│ PRODUCED TODAY         GRID EXPORT      │ USED TODAY     COST TODAY │
│ 18.3 kWh               5.7 kWh          │  8.4 kWh        2.53 EUR  │
│                                         │ ┌─────────────────────────┐│
│ SELF-USED 69%            EXPORTED 31%   │ │ CURRENT RATE       OFF ││
│ █████████████░░░░░░░░░░░░               │ └─────────────────────────┘│
│                                         │                            │
│ HOURLY PRODUCTION         ■PK ■OFF      │ ■ TEMPERATURES             │
│      █                                  │ OUTDOOR       LAUNDRY      │
│      █ █                                │  20.7°C        24.6°C      │
│      █ █ █ █                            │                            │
│  █ █ █ █ █ █ █ █                        │ ┌──── ■ SURPLUS ──────────┐│
│  █ █ █ █ █ █ █ █ █ █                    │ │                         ││
│  12h    15h    18h    21h               │ │       INSUFFICIENT      ││
│─────────────────────────────────────────│ └─────────────────────────┘│
│ [🔋 73%] SUNRISE 03:36 - SUNSET 19:44  HOME ASSISTANT - UPD 29/05 - 23:45 (refresh 10 min) 📶│
└─────────────────────────────────────────────────────────────────────┘
```

Colors: **red** for important values and alerts (solar production, peak rate, outdoor temperature, surplus available, low battery); **black** for everything else.

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
├── battery.py               ← MAX17048 fuel gauge (% reading, charging)
├── config.json              ← WiFi credentials + HA URL/token
├── barlow_bold_56.py        ← "hero" font (hourly PV value)
├── barlow_bold_40.py        ← "big" font (date, pv_now, surplus)
├── barlow_bold_28.py        ← "medium" font (secondary numbers)
├── archivo_bold_24.py       ← status screens font
└── archivo_bold_13.py       ← "label" font (titles and footer)
```

**Note**: ship only one of `display.py` (French UI) or `display_en.py` (English UI) — they are mutually exclusive. The Python file you actually copy to the ESP32 must be named `display.py` regardless of language, since `main.py` imports `display`. Rename `display_en.py` to `display.py` if you want the English version on the device.

### The cycle (main.py)

1. **Framebuffer pre-allocation** (before any non-trivial import) — `bytearray(48000)` is allocated first in the MicroPython heap to avoid fragmentation. This buffer is used to compose the image before sending to the panel.

2. **WiFi connect** — `provisioning.ensure_provisioned()` reads `config.json` and connects the STA. If `config.json` is missing or WiFi is unreachable, falls back to captive portal mode (see limitations).

3. **HA fetch** — `epaper_ha_client.fetch_dashboard()` queries the 14 configured entities (1 REST request each, GET `/api/states/<entity_id>`), then `hourly_buckets()` queries history to rebuild the 30-minute histogram.

4. **Network release** — `WLAN.active(False)` to reclaim ESP-IDF RAM, then `gc.collect()` on the Python side.

5. **Battery read** — `battery.read()` queries the MAX17048 over I²C (returns `None` if not wired, no error raised).

6. **ePaper render** — `display.render_dashboard(data, hourly, refresh_min, battery)` loads the fonts, composes the 48 KB framebuffer (black plane + red plane), sends to the panel, waits for the refresh (~20 s), puts the panel into deep sleep.

7. **ESP32 deep sleep** — `machine.deepsleep(REFRESH_SEC * 1000)`. On wake, full hard reset → back to step 1.

### Memory strategy (critical point)

The ESP32 has a tight RAM budget, shared between:

- **MicroPython heap** (Python objects) — ~165 KB free at fresh boot
- **ESP-IDF heap** (WiFi, mbed-TLS, framebuf C, etc.) — ~120 KB free at fresh boot

The full cycle is designed to never exceed these limits:

| Phase | Python heap free | ESP-IDF heap free |
|---|---|---|
| Boot | 165 KB | 120 KB |
| After 48 KB framebuffer alloc | 113 KB | 120 KB |
| WiFi active (display not loaded) | 92 KB | 42 KB |
| During HA fetch | 90 KB | 40 KB |
| After WiFi released | 110 KB | 100 KB |
| Display + 4 fonts loaded (47 KB bytecode) | 47 KB | 95 KB |
| During ePaper render | 42 KB | 95 KB |
| End of cycle | 42 KB | 100 KB |

**Why `display` is imported after WiFi**: `display.py` + its 4 fonts consumes ~25 KB of ESP-IDF heap on import alone (framebuf in C, internal allocations). If display is loaded before WiFi, ESP-IDF doesn't have enough left for the WiFi buffers (~40 KB needed) → `WiFi Out of Memory` on the first `sta.active(True)`.

### HA entity configuration

In `epaper_ha_client.py`, `ENT` dict:

```python
ENT = {
    "pv_today":   "sensor.pv_production_today_thingspeak_2",  # daily kWh total
    "pv_now":     "sensor.pv_production_thingspeak",          # power W
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

**HA template for sunrise/sunset** — known pitfall:

The `next_rising` and `next_setting` attributes of `sun.sun` are in **UTC**. A naive template using `strftime` will therefore output UTC, not local. Correct template (DST-aware automatically):

```yaml
template:
  - sensor:
      - name: "Sunrise"
        unique_id: jour_lever
        state: >
          {% set t = as_datetime(state_attr('sun.sun','next_rising')) | as_local %}
          {{ t.strftime('%H:%M') if t else 'unavailable' }}
      - name: "Sunset"
        unique_id: jour_coucher
        state: >
          {% set t = as_datetime(state_attr('sun.sun','next_setting')) | as_local %}
          {{ t.strftime('%H:%M') if t else 'unavailable' }}
```

The `| as_local` filter converts the datetime from UTC to the timezone configured in HA (Settings → System → General). Without this filter, the dashboard will show times offset by 1-2 hours.

### Peak/off-peak schedule (ORES 2026)

```python
def _is_hp(hour):
    # Peak hours: 7-11 AM AND 5-10 PM, every day (weekends included)
    return (7 <= hour < 11) or (17 <= hour < 22)
```

No more weekday/weekend distinction since January 1, 2026.

### 30-minute bucketing (epaper_ha_client.py)

24 buckets of 30 min over the last 12 hours:

1. History request: `GET /api/history/period/<iso>?filter_entity_id=sensor.pv_production_today_thingspeak_2&minimal_response&significant_changes_only&no_attributes`
2. Parse the ISO timestamps of each point
3. For each slot boundary (every 30 min over the 12 h window), **linear interpolation** between the 2 surrounding points (the sensor is cumulative and monotonic, except for the midnight reset)
4. Slot production = difference between 2 interpolated boundaries
5. Midnight reset handling: if the diff is negative, take the value after the reset

Without interpolation, with `significant_changes_only` the points are spaced 10-20 min apart on average, so taking the "last point before boundary" introduces a systemic error (sometimes 25 % error per bucket).

---

## Configuration

### config.json

To copy onto the ESP32 flash (`mpremote cp config.json :`):

```json
{
  "wifi_ssid": "YourNetwork",
  "wifi_pass": "YourPassword",
  "ha_url":    "http://192.168.x.x:8123",
  "ha_token":  "eyJhbGciOiJIUzI1NiIs..."
}
```

The HA token is obtained inside Home Assistant: *User profile → Long-lived access tokens → Create token*. Keep this token confidential — it grants full HA access.

### Constants in main.py

```python
REFRESH_SEC   = 600      # 10 minutes between refreshes
DEEP_SLEEP    = True     # False to stay awake (dev)
PORTAL_RENDER = True     # show portal screen if WiFi fails
```

### Constants in epaper_ha_client.py and display.py

```python
TZ_OFFSET = 2 * 3600     # CEST (Brussels summer time)
                         # CET (winter time) = 1 * 3600
```

To be adjusted manually at DST changes (spring/fall) — no automatic DST handling for simplicity.

### Constants in display_en.py (English version only)

```python
CITY_NAME = "CITYNAME"   # <- replace with your city
```

---

## Installation and first boot

### Prerequisites (Mac/Linux)

```bash
pip install mpremote esptool
```

### 1. Flash MicroPython on the ESP32 (one time)

```bash
# Put the ESP32 in bootloader mode (hold BOOT, press RESET, release BOOT)
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX erase_flash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX --baud 460800 \
    write_flash -z 0x1000 ESP32_GENERIC-20251215-v1.28.0.bin
```

Firmware must be MicroPython >= 1.23 (tested on 1.28). Download from https://micropython.org/download/ESP32_GENERIC/.

### 2. Deploy the code

All files to put on flash (use either `display.py` for French OR rename `display_en.py` to `display.py` for English, never both):

```bash
# For English UI: first rename the English file
cp display_en.py display.py

# Then copy everything
python3 -m mpremote cp main.py provisioning.py epaper_ha_client.py \
                      display.py battery.py \
                      barlow_bold_56.py barlow_bold_40.py \
                      barlow_bold_28.py archivo_bold_24.py \
                      archivo_bold_13.py \
                      config.json :
```

Verify:

```bash
python3 -m mpremote ls
```

### 3. First boot

Unplug / re-plug the USB-C, or:

```bash
python3 -m mpremote reset
```

To follow the first cycle's logs:

```bash
python3 -m mpremote
# Ctrl+] to exit without rebooting
```

### 4. Subsequent cycles

The cycle continues automatically, no Mac needed. To intervene later, see [Troubleshooting](#troubleshooting).

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
| Compose framebuffer + render ePaper | 20-22 s | ~80 mA (peaks at 50 mA during refresh) |
| Enter deep sleep | < 1 s | — |
| **Total active** | **~30 s** | **~150 mA average** |

Then deep sleep: **~30 µA** for ~9 min 30 s.

### Battery life estimate (LiPo 8200 mAh, boost 80% efficiency)

| Refresh | Cycles/day | Daily consumption | Battery life |
|---|---|---|---|
| 5 min | 288 | ~360 mAh | ~23 days |
| 10 min | 144 | ~180 mAh | ~46 days |
| 15 min | 96 | ~120 mAh | ~68 days |
| 30 min | 48 | ~60 mAh | ~135 days |

At 10 min, that's equivalent to almost 7 weeks without recharging. At 15 min, more than 2 months. The recommended trade-off: you don't need minute-by-minute info, but once every quarter-hour is enough to decide whether to plug in an appliance when the sun is good.

### Error handling behavior

| Error | Behavior |
|---|---|
| WiFi unreachable (3 retries) | Error screen displayed, retry in 2 min |
| HA unreachable | Error screen displayed, retry in 2 min |
| A single entity missing | Display `--` instead of the value, normal cycle |
| MemoryError during render | Error screen, retry in 2 min |
| OOM before render | Full reboot via watchdog (~5 s) |
| Missing config.json | Falls back to captive portal (see limitations) |

So the screen never freezes on stale info: either a real update, or an explicit error message with the last attempt's timestamp.

---

## Reading the dashboard

### HEADER zone (top)

- **Today's date** large on the left (`FRI. 29 MAY`)
- **City** (`CITYNAME`) small below
- **Current PV production** large red on the right (`2.4 kW`) — that's the info you check first thing in the morning to see if the sun is generous

### LEFT column: solar production

- **Produced today**: cumulative since 00:00 in kWh
- **Grid export**: cumulative since 00:00 in kWh (what you returned to the grid because you produced more than you consumed)
- **Self-used / Exported bar**: visual day split. The wider the black zone (self-used), the better financially.
- **Hourly production histogram**: today's curve. 24 bars = last 12 hours in 30-min increments. Peak-hour bars (7-11 AM and 5-10 PM) are **red**, off-peak bars are **black**. Lets you see at a glance:
  - Whether the morning was productive
  - If a cloud passed at 2 PM
  - If you're in the declining production phase of late day

### RIGHT column: grid, temperatures, surplus

- **Used today**: kWh purchased from the grid since 00:00 (peak + off-peak combined)
- **Cost today**: euros since 00:00 per the ORES 2026 schedule
- **Current rate**: `OFF` (off-peak, white background) or `PK` (peak, red background). Helps decide whether to start the washing machine now or wait until 10 PM.
- **Temperatures**: outdoor (red, to draw the eye — it's the "dress accordingly" info) and laundry (black).
- **SURPLUS box**: the most important zone of the dashboard.
  - If `binary_sensor.surplus_solaire_stable` is ON and `surplus_kw > 0.05` → shows `X.X kW AVAILABLE` in large red → you can plug in the car, start the dishwasher, etc.
  - Otherwise → `INSUFFICIENT` in large black → forget it, the surplus isn't stable

### FOOTER zone (bottom)

- **Battery** (left, if the MAX17048 fuel gauge is wired) : battery icon + `XX%` + red `USB` indicator when charging. Red icon if battery < 20 %.
- **Sunrise / Sunset** (center-left)
- **Source + timestamp + refresh interval** (right) — useful to see if the dashboard is up to date or stuck for 3 hours for some reason.
- **WiFi signal strength** (far right): smartphone-style icon (center dot + fan arcs). Number of solid arcs indicates reception at the last HA fetch:
  - 3 arcs: excellent signal (> -55 dBm)
  - 2 arcs: good signal (-55 to -70 dBm)
  - 1 arc: weak signal (-70 to -85 dBm)
  - dot only: poor signal (< -85 dBm) — the dashboard is probably struggling to fetch HA
  - icon missing: RSSI couldn't be read (should never happen in dashboard mode since WiFi is necessarily active)

---

## Troubleshooting

### The dashboard didn't refresh overnight

**Most likely cause**: **USB powerbank auto-shutoff**. All consumer USB powerbanks have a "trickle" mode that cuts the output when the drawn current drops below a threshold (typically 50-100 mA). In deep sleep the ESP32 only draws ~30 µA, so the powerbank thinks nothing is plugged in and cuts power.

**Checks**:
- Test on a wall power supply (USB-C charger) → if no issue for 24 h, confirmed
- On some powerbanks, double-clicking the button activates a "small device" / "trickle mode"

**Proper fix**: complete the hardware assembly with the boost converter. LiPo → Boost 5V → ESP32 doesn't suffer from auto-shutoff (the boost converter draws continuously).

### "WiFi Out of Memory" on the first cycle

ESP-IDF doesn't have enough heap for the WiFi buffers. Possible causes:
- A previous cycle didn't release WiFi cleanly (zombie socket or interface)
- The Python allocation order starved ESP-IDF of RAM

**Fix**: already handled in code via the WiFi-first / display-last pattern. If it recurs, soft-reset (`machine.reset()`) or physical reset (unplug/replug) to start from a fresh state.

### Sunrise / sunset times offset by 1-2 hours

Cause: the HA template producing these sensors reads `state_attr('sun.sun','next_rising')` which returns an ISO timestamp in **UTC**. If the template just does `strftime('%H:%M')` on this timestamp, it outputs UTC as-is, without conversion to the local timezone.

Fix: apply the `| as_local` filter in the HA template (see *HA entity configuration* section). No dashboard code change needed — at the next cycle, the correct values appear automatically. Bonus: DST handled automatically by HA (UTC+1 winter, UTC+2 summer).

### Histogram with weird bars

If you see odd discrepancies between the histogram and the HA chart:
- Check that `TZ_OFFSET` is correct (2*3600 in summer, 1*3600 in winter)
- Check in the logs that `hourly_buckets: GET .../history/period/...` covers the right window

Linear interpolation between historical points is sensitive to gaps. If HA only logged one point per hour, interpolation remains correct but uncertainty grows. `significant_changes_only` is enabled to avoid overloading the request.

### `?` glyphs instead of text

One of the `barlow_bold_XX.py` fonts doesn't have the requested character in its charset. Fonts are generated with `font_to_py` on a subset to save RAM.

**Quick fix**: use another already-loaded font that has the glyph (typically F_BIG = barlow_bold_40 has almost the full alphabet).

**Proper fix**: regenerate the font with `font_to_py -c "ABCD...stuvw...0123456789,. " barlow-bold.ttf 28 barlow_bold_28.py` passing all needed characters via `-c`.

### The captive portal doesn't work

The captive portal mode (`PORTAL_RENDER=True`, triggered when `config.json` is missing) is **experimental on MicroPython 1.28**. Symptom: the `GNI-ePaper-Setup` AP is visible but the phone doesn't get an IP via DHCP.

**Current workaround**: create `config.json` manually with a text editor, then `mpremote cp config.json :`. It's a 30-second job the first time, and that's it.

### Servicing an autonomous device

```bash
# Watch logs live (interrupts deep sleep if between 2 cycles)
python3 -m mpremote
# Ctrl+] to exit

# Push a new code version
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
| 2 | No automatic DST handling for `TZ_OFFSET` on ESP32 | Minor | Adjust manually twice a year (sunrise/sunset are DST-aware on HA via `as_local`) |
| 3 | All fonts have partial charsets | Minor | Test before adding new text; regenerate the font if needed |
| 4 | ePaper refresh blocks for ~20 s | Inherent | None (physical ink limit) |
| 5 | Powerbank auto-shutoff incompatible with deep sleep | Major | Use wall power or a dedicated LiPo + boost setup |
| 6 | No battery measurement until MAX17048 is wired | Minor | `battery.read()` returns `None` → footer doesn't show the info |
| 7 | Histogram requires `significant_changes_only` on the cumulative sensor | Inherent | The sensor must log enough points (~1 / 15 min minimum) |
| 8 | Tight memory margin (~12-15 KB free after render) | Major | Watch out if adding features. Compilation to `.mpy` recommended if reaching the ceiling |

---

## Appendix A — Source code

All files are in `/mnt/user-data/outputs/` (sandbox side) and on the ESP32 flash (production side).

### main.py (~110 lines)

Cycle orchestrator. Framebuffer allocation up front (anti-fragmentation), lazy import of `display`, error handling and deep sleep at the bottom.

### provisioning.py (~330 lines)

- `connect_sta(cfg, timeout=20)`: 3 retries with `esp.osdebug(None)`, explicit `AP_IF.active(False)`, `gc.collect()`, ESP-IDF heap diagnostic for debug.
- `start_portal(...)`: starts an AP `GNI-ePaper-Setup` (open, channel 6, max_clients 1), minimal HTTP server, WiFi scan to offer SSID choices, generates `config.json` then reboots.
- `ensure_provisioned(on_portal_start)`: chains `connect_sta` then falls back to `start_portal` if `config.json` is missing or credentials are stale.

### epaper_ha_client.py (~250 lines)

- `sync_time()`: NTP call, updates the internal clock
- `_get(path)`: GET helper to the HA API with retry and timeout
- `_parse_iso_utc(s)`: parses ISO timestamps returned by HA
- `fetch_dashboard()`: fetches the 14 entities and composes the dict for rendering. Includes capturing `wifi_rssi` via `network.WLAN(network.STA_IF).status("rssi")` while the connection is still active.
- `hourly_buckets(entity, nb=24, bucket_min=30)`: fetches history, linearly interpolates between points, returns the list of 24 half-hourly values over the last 12 hours

### display.py / display_en.py (~660 lines)

The two files are identical in structure and API; only the UI strings, comments, and number formatting differ. Pick one and ship it as `display.py`.

- Layout constants (WIDTH, HEIGHT, MARGIN, LX, LW, RX, RW, BULLET, etc.)
- `Display`: low-level SPI driver for the UC8179 controller (init, black plane, red plane, refresh, sleep)
- `Display.text_pro(s, x, y, font, color)`: glyph-by-glyph text rendering in MONO_HLSB
- `_is_hp(hour)`: ORES 2026 tariff schedule (peak: 7-11 AM and 5-10 PM, every day)
- `_fr(x, decimals)` (French) or `_fmt(x, decimals)` (English): number formatting (comma vs dot decimal separator)
- `_draw_wifi_icon(d, x, y, rssi)`: smartphone-style WiFi icon (dot + 3 concentric fan arcs), drawn as a thick polyline for crisp curves. Bounding box 30×22 px. dBm thresholds for number of arcs: -55 / -70 / -85.
- `_draw_dashboard(d, data, hourly, now, refresh_min, battery, F_HERO, F_BIG, F_MED, F_LAB)`: composes the full layout
- `render_dashboard(data, hourly, refresh_min=10, battery=None)`: public entry point
- `render_status(title, lines, color=BLACK)`: generic screens for errors / portal / boot
- `render_portal_screen(ssid, password)`: info screen when the device is in portal mode
- `render_error(title, msg, retry_min)`: error screen with retry delay
- `demo_dashboard()`: local test with mocked data (useful to iterate on the layout)

### battery.py (~80 lines)

- `_read_fuel_gauge()`: I²C `scan()` then reads VCELL and SOC registers of the MAX17048
- `_read_adc()`: fallback ADC on GPIO34 if no fuel gauge (less precise)
- `usb_present()`: USB presence detection via GPIO (to wire)
- `read()`: returns `{"percent", "voltage", "charging"}` or `None` if gauge absent
- `status_text()`: text helper for display

### Fonts (generated with font_to_py by Peter Hinch)

- `barlow_bold_56.py` (13 KB) — header digits + letters
- `barlow_bold_40.py` (23 KB) — date, pv_now, surplus
- `barlow_bold_28.py` (8 KB) — secondary digits
- `archivo_bold_24.py` (31 KB) — status screens
- `archivo_bold_13.py` (13 KB) — labels and footer

To regenerate with a different charset:

```bash
font_to_py -c "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-/:°€%" \
           -x Barlow-Bold.ttf 28 barlow_bold_28.py
```

The `-x` option is important: produces MONO_HLSB (compatible with `Display.text_pro`).

**For the English version**, make sure to include letters needed for `INSUFFICIENT`, `AVAILABLE`, `SUNRISE`, `SUNSET`, `OUTDOOR`, `LAUNDRY`, `PK`, `OFF`, `UPD` (most are already in a typical alphabetic charset, just make sure F/O/W/X/Y/Z are included if previously omitted).

---

## Appendix B — Enclosure

Three options, from least to most engaging:

### Option 1 (recommended): cheap photo frame ~17×22 cm

- Wood-fiber + glass / acrylic photo frame, available at most furniture / supermarket stores for 2-5 €
- **Inside dimensions** : ≥17 × 22 cm so the ePaper panel (170 × 112 mm) fits with proper margin
- **Inside depth** : ≥25 mm ideal, 30 mm is comfortable
- **Removable back** : essential for accessing the electronics
- Original test case for this project used a 2 € wood-grain frame with passe-partout (mat board) — works perfectly, the mat hides the panel borders and the wood grain frame looks elegant

#### Depth validation (target ~30 mm)

| Element | Thickness | Source |
|---|---|---|
| Front plastic glazing of frame | ~1 mm | typical |
| Raw 7.5" ePaper panel | **0.91 mm** | Official Waveshare spec: 170.2 × 111.2 × 0.91 mm |
| ESP32 driver board (PCB + USB-C) | ~5 mm | PCB 1.6 mm + USB-C connector ~3 mm above |
| LiPo HXJNLDC 8200 mAh | **~12 mm** | 7565121 = 75 × 65 × 12.1 mm per manufacturer label |
| FFC ribbon bend radius | ~3 mm | Waveshare recommendation to preserve the ribbon |
| Small boards (TP4056, MAX17048, boost 5V) | 4-7 mm | tucked into free corners |
| Foam shim + back cardboard | ~2 mm | shimming + frame back |

**Layout tip: anything but stacking**

The ESP32 board (~80×30 mm) only covers a small portion of the area behind the panel (170×111 mm). The LiPo (~100×55 mm) should therefore be placed **next to** the ESP32 board, not behind it:

```
┌───────────────────────────────┐  ← view from the back of the frame
│                               │
│   [free zone 100×80 mm]       │  ← stick the LiPo here, flat
│                               │
│  ┌──────────────────────────┐ │
│  │  ESP32 driver board      │ │  ← against the panel, ribbon to corner
│  └──────────────────────────┘ │
│                               │
└───────────────────────────────┘
```

With this side-by-side layout, the maximum thickness is the battery (12 mm), not the sum panel + battery + driver. Total:

```
1 mm   (front plastic glazing)
+ 1 mm   (ePaper panel)
+ 12 mm  (LiPo, side-by-side with driver board)
+ 3 mm   (FFC ribbon bend radius)
+ 2 mm   (foam shim)
+ 1 mm   (back cardboard)
= 20 mm  →  fits within a 25 mm frame, with 10 mm margin in a 30 mm frame
```

**If the frame is too shallow** (< 20 mm), an alternative: mount the electronics on the **outside** back of the frame using standoffs (~15-20 mm spacers at the corners). The frame can then be any depth — the electronics sit between the frame back and the wall, adding ~20 mm wall offset.

#### Integration steps

1. Remove the mat (the panel already fills the visual zone) OR keep the mat with a window matched to the active area (163 × 98 mm)
2. Cut the cardboard back with a knife to house the ESP32 board (let the FFC ribbon pass to the panel)
3. Shim the panel against the glazing with thin (1 mm) foam double-sided tape on the edges
4. Stick the LiPo next to the ESP32 board (3M foam double-sided)
5. Cut a discreet hole in the bottom of the frame for the USB-C charging cable (or a switch if pure battery version)
6. Close the frame, done

**Pros**: 2-5 € of materials, 1-hour assembly, discreet living-room integration, no 3D printing.
**Cons**: final thickness ~25-30 mm on the wall — to open and access electronics you have to remove the back (clips or staples).

### Option 2: 3D printed enclosure

`epaper_case.py` file (OpenSCAD or FreeCAD) to generate / customize:

- 195 × 280 × 22 mm exterior
- Visual window 800×480 px = 165 × 100 mm
- ESP card housing: 50 × 70 mm with USB-C pass-through
- LiPo 8200 mAh housing: 110 × 65 × 10 mm
- M3 screws or assembly clip
- Print in PETG (UV resistant, no warping when exposed to sunlight behind a window)

### Option 3: laser-cut acrylic sandwich

- 2 plates of 3 mm acrylic laser cut: front (with viewing window) + back (closed)
- 22 mm aluminum or nylon standoffs at the 4 corners
- Long M3 screws going through the assembly
- Very clean visually, fully transparent → shows the wiring if you like
- Drawback: laser access cost, dimensions to validate before cutting

---

## Appendix C — Roadmap & ideas

### Short term

- [ ] Receive the 5V boost converter (TPS61023 or equivalent)
- [ ] Receive the MAX17048 fuel gauge
- [ ] Wire everything up (LiPo + TP4056 + boost + MAX17048) and test 48h
- [ ] Verify real autonomy vs estimated
- [ ] Print / buy the enclosure
- [ ] Design a custom carrier PCB (Fritzing or KiCad) for clean integration behind the frame

### Medium term

- [ ] Compile Python modules to `.mpy` with `mpy-cross` to save ~30 % of RAM (useful if adding features)
- [ ] DNS hijack in the captive portal for auto-redirect pop-up on iOS/Android
- [ ] Fix the captive portal (probably wait for MicroPython 1.29 or 1.30 which will fix the 1.28 WiFi regression)
- [ ] Display tomorrow's weather forecast (needs adding an HA entity)

### Exploratory ideas

- [ ] Physical button on the board to force a refresh without waiting 10 min (GPIO wake from deep sleep)
- [ ] "Night" mode with 30 min refresh or disabled between 11 PM and 6 AM to save battery
- [ ] Detailed statistics page on long button press (weekly self-consumption, cumulative savings, etc.)
- [ ] Home Assistant integration with MQTT remote command (push from HA → force a refresh)
- [ ] Multi-page: alternate energy / weather / calendar dashboards each cycle
- [ ] XL version with 13" / 800×1280 panel if Waveshare releases one at a reasonable price

---

*Last updated: May 31, 2026 — version 3.0 bilingual (full English translation + bilingual TOC + display_en.py reference + 2€ frame option documented)*
