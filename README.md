# HeishaMon Scheduler

Wochen-Zeitsteuerung für Panasonic-Aquarea-Wärmepumpen über
[HeishaMon](https://github.com/heishamon/HeishaMon) — als Home-Assistant-Integration
mit visueller Lovelace-Karte.

![HA 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue)

## Funktionen

- **Wochenplan pro Kanal** in 30-Minuten-Slots, per Drag im Dashboard einzeichnen
- **Kanäle:**
  - Z1/Z2 Heat Shift (Heizkurven-Verschiebung oder Direkt-Temperatur)
  - Warmwasser-Solltemperatur (DHW)
  - Betriebsmodus (Heizen / Kühlen / Auto / DHW / Kombinationen)
  - Flüstermodus (Quiet Mode, Stufe 0–3)
  - Powerful Mode (30/60/90 min)
  - Force DHW
- **Schonender MQTT-Versand:** Kommandos werden gedrosselt (min. 30 s Abstand),
  und nur gesendet, wenn die Pumpe nicht ohnehin schon auf dem Zielwert steht
- **Offline-Erkennung** über das HeishaMon-LWT-Topic inkl. Neuauswertung beim
  Reconnect und `binary_sensor` für die Verfügbarkeit
- **Sensoren** je Kanal (aktueller Planwert, nächste Änderung) und **Schalter**
  zum Aktivieren/Deaktivieren einzelner Kanäle oder des gesamten Plans

## Voraussetzungen

- HeishaMon (Firmware 4.x empfohlen) mit MQTT verbunden
- Home Assistant ≥ 2024.12 mit eingerichteter MQTT-Integration

## Installation

1. Repository als [HACS](https://hacs.xyz)-Custom-Repository hinzufügen oder den
   Ordner `custom_components/heishamon_scheduler` nach `config/custom_components/`
   kopieren.
2. Die Karte `www/heishamon-scheduler-card.js` nach `config/www/` kopieren und
   unter *Einstellungen → Dashboards → Ressourcen* als
   `/local/heishamon-scheduler-card.js` (Typ: Modul) eintragen.
3. Home Assistant neu starten und die Integration **HeishaMon Scheduler** über
   *Einstellungen → Geräte & Dienste* hinzufügen.
4. Dem Dashboard eine Karte vom Typ **HeishaMon Scheduler** hinzufügen.

## Konfiguration

Beim Einrichten werden das MQTT-Basis-Topic (Standard: `panasonic_heat_pump`)
und die gewünschten Kanäle gewählt. Über **Optionen** der Integration lassen
sich nachträglich ändern:

| Option | Bedeutung |
|---|---|
| MQTT Basis-Topic | Muss dem HeishaMon-Basis-Topic entsprechen |
| Zeitplan-Kanäle | Welche Kanäle geplant werden |
| Z1/Z2 Heat Request Min/Max | `-5…5` für Shift-Betrieb, z. B. `20…55` für Direkt-Temperatur |

## Hinweise

- `SetOperationMode` kennt 7 Kommandowerte, der Zustand `Operating_Mode_State`
  meldet aber 9 (Auto wird als Auto-Heizen/Auto-Kühlen gemeldet). Die
  Integration mappt das korrekt.
- Der Plan greift „rückwirkend“: Der zuletzt vor dem aktuellen Zeitpunkt
  liegende Eintrag gilt, auch über Tagesgrenzen hinweg.
