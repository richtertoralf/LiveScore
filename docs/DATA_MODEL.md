# Datenmodell und Persistenz

## Veranstaltungsdatei

Jede Veranstaltung ist ein eigenständiger JSON-State mit `schema_version: 1`.
Das [vollständige Beispiel](../examples/prague-2026.json) enthält einen vorbereiteten
Spielplan mit 6 Teilnehmern, 6 Referees und 14 Spielen. Es ist kein Ergebnisarchiv.

| Feld | Inhalt |
|---|---|
| `schema_version` | unterstützte Formatversion: `1` |
| `revision` | Änderungszähler innerhalb dieser Veranstaltung |
| `event` | Name, Zeitraum, Ort, Logo-Pfad, Score-Bezeichnung, optional Sportprofil |
| `play_areas` | Wettkampfflächen mit stabiler ID und freier Bezeichnung |
| `participants` | Teilnehmer mit ID, Name, optional Kurzname, Land und Logo-Pfad |
| `referees` | Referees mit ID, Name und optional Land |
| `matches` | Spielplan, Paarungen, Officials und Spielzustand |
| `active_match_id` | ausgewähltes Spiel oder `null` |
| `events` | Bedienereignisse und Informationen für Undo und Request-Deduplizierung |

Die Veranstaltungs-ID steht im Dateinamen, nicht im portablen State.
IDs sind innerhalb ihrer Kategorie eindeutig. Erlaubt sind Buchstaben, Ziffern,
Bindestrich und Unterstrich, maximal 80 Zeichen; das erste Zeichen ist alphanumerisch.
Datums- und Zeitangaben im Spielplan sind lokale Veranstaltungsangaben;
Ereigniszeitstempel sind UTC im ISO-Format.

Ein Match enthält Planfelder wie `id`, `date`, `time`, `play_area_id`,
`participant_1`, `participant_2`, Platzhalter und `officials` als geordnete Liste
von Referee-IDs. `stage` beschreibt die Turnierphase, `round` die Gruppe oder
Spielrunde. `stage_label` und `round_label` sind optionale englische Anzeigetexte.
Hinzu kommen `status`, `side_l`, `side_r`, `scores`, `control_revision`, `period`,
`intermission` und `counters`.

Länder werden als zweistellige Codes für ISO 3166-1 Alpha-2 geführt, etwa `CZ`,
`DE`, `KZ` und `GR`; ohne Angabe steht `""`. Eingaben werden getrimmt und
großgeschrieben. Dreistellige IOC-/FIFA-Kürzel müssen vor der Eingabe umgesetzt
werden, etwa `CZE → CZ` und `GER → DE`. Logo-Pfade sind nur Metadaten.

## Teilnehmer und Seiten

Scores gehören zum Teilnehmer innerhalb eines Spiels. `L` und `R` sind ausschließlich
Positionen im Programmbild beziehungsweise Overlay:

```json
{
  "side_l": "bsc-praha",
  "side_r": "fc-ingolstadt-04",
  "scores": {"bsc-praha": 2, "fc-ingolstadt-04": 1}
}
```

Ein Seitenwechsel tauscht nur `side_l` und `side_r`: Praha behält 2,
Ingolstadt 1. Frühere Ergebnisse bleiben pro Spiel erhalten. Die öffentliche API
löst die Zuordnung bereits in `left` und `right` auf; siehe [API](API.md).

## Spielzustände

| Aktion | Übergang |
|---|---|
| Paarung und Seiten vorbereiten | `scheduled → ready` |
| Vorbereitung zurücknehmen | `ready → scheduled` |
| Starten | `ready → live` |
| Abschnittspause setzen/aufheben | Status bleibt `live`, `intermission` wird geändert |
| Ergebnis bestätigen | `live/paused → finished` |
| Wiederöffnen | `finished → live` |

`ready` verlangt zwei verschiedene bekannte Teilnehmer, eine gültige
Seitenzuordnung und Scores von null. Score, Counter und Undo sind nur bei
`live` oder `paused` möglich; Seitenwechsel zusätzlich bei `ready`.
Auswählbar sind geplante oder beendete Spiele, solange kein anderes Spiel
`ready`, `live` oder `paused` ist. `idle` ist ein API-Zustand ohne ausgewähltes Spiel,
kein gespeicherter Match-Status.

`paused` und die bisherigen `pause`-/`resume`-Aktionen bleiben ausschließlich für
Bestandsdaten und ältere API-Clients unterstützt. Neue Bedienabläufe benötigen sie
nicht. Die aufbereitete Live-Ausgabe stellt `paused` als `live` dar; der rohe State
und Exporte behalten den gespeicherten Wert. Es ist keine Datenmigration erforderlich.

## Sportprofil

`event.sport_profile` konfiguriert Abschnitte und teilnehmerbezogene Zähler.
Es wird per Veranstaltungs-JSON oder API gesetzt. Beispiel:

```json
{
  "sport": "blind_football",
  "ruleset": "IBSA 2025-2029",
  "periods": 2,
  "period_label": "Halbzeit",
  "counters": [
    {
      "id": "team_fouls",
      "label": "Fouls",
      "scope": "participant",
      "reset_each_period": true,
      "warning_at": 4,
      "critical_at": 5,
      "warning_label": "Nächstes Foul → Double Penalty",
      "critical_label": "Double Penalty"
    }
  ]
}
```

`sport` und `ruleset` sind beschreibende Metadaten. `periods` ist positiv,
`period_label` frei wählbar, Counter-IDs sind eindeutig. Unterstützt wird
`scope: "participant"`. Warnschwellen sind Anzeigehilfen, keine Obergrenzen
und keine automatische Sportregel. Wenn beide Schwellen gesetzt sind, muss
`warning_at` kleiner als `critical_at` sein.

Die Historie liegt unter `counters[counter_id][participant_id][period_als_string]`.
Zähler sind nie an eine Seite gebunden. Beim nächsten Abschnitt startet
`reset_each_period: true` bei null, andernfalls wird der bisherige Wert übernommen.
Fehlende Werte bedeuten null; bei fortlaufenden Zählern wird der letzte vorhandene
Wert übernommen. Unbekannte Referenzen, negative Werte und Nichtnull-Werte für
zukünftige Abschnitte werden abgewiesen. Geplante und vorbereitete Spiele verlangen
Abschnitt 1 und Nullwerte.

`intermission` kennzeichnet ausschließlich eine Pause vor dem nächsten Abschnitt.
Ein Abschnittswechsel und das Spielende setzen sie zurück. Wiederöffnen setzt den
Status direkt auf `live` und stellt keine frühere Abschnittspause automatisch wieder her.
Nach Spielbeginn kann das Profil nicht mehr geändert werden.

Ohne Profil gelten ein Abschnitt und keine Zähler. Fehlende optionale Felder
werden kompatibel ergänzt: `referees`/`officials` als leere Listen,
`period` als `1`, `counters` als `{}`, `intermission` als `false` und zusätzliche
Phasen-/Rundenlabels als `""`. Die Schema-Version bleibt 1;
unbekannte Versionen werden abgewiesen.

## Dateien und Migration

```text
data/
  events/<event-id>.json
  imports/<event-id>.json
  active-event.json
  active-event.json.lock
  tournament.json          # gegebenenfalls unveränderte Legacy-Datei
  tournament.json.lock
```

`imports/` enthält die beim Import gespeicherte Grundlage für das Zurücksetzen.
`active-event.json` enthält `active_event_id` oder `null` sowie `selection_token`.
Die Kennung ändert sich beim Veranstaltungswechsel und bei Ersetzen/Zurücksetzen
der aktiven Veranstaltung. Browser-Kontext und Stream-Metadaten gehören nicht
in einen Veranstaltungsexport.

Ohne Auswahlzeiger wird eine vorhandene Legacy-Datei `tournament.json` oder
die mit `data_file` konfigurierte Datei validiert und als erste Veranstaltung
kopiert und ausgewählt. Das Original bleibt unverändert. Eine Unterbrechung
zwischen Kopie und Auswahl wird beim nächsten Start anhand einer identischen
Kopie fortgesetzt; abweichende oder uneindeutige Daten führen zum Startabbruch.
Ein vorhandener Auswahlzeiger verhindert eine erneute Migration. Beschädigte
Dateien oder eine fehlende aktive Event-Datei werden nicht durch Standarddaten ersetzt.

## Speicherung und Ereignisse

Genau ein Serverprozess besitzt das Datenverzeichnis. Unter einer zentralen
Mutationssperre wird der neue State vollständig validiert, in eine temporäre
Datei im selben Verzeichnis geschrieben, geflusht und mit `fsync` gesichert.
`os.replace` ersetzt die Zieldatei atomar. Erst danach werden Serverzustand und
Browser aktualisiert. Ein Schreibfehler übernimmt die Änderung nicht.

Die Ereignisliste speichert relevante Zustandswechsel und Score-/Zähleraktionen
mit Spiel-/Teilnehmerbezug, Zeitstempel, Revision und Request-ID. Score-Undo markiert
das ursprüngliche Ereignis als zurückgenommen und verweist darauf.
Die Liste bleibt für die Veranstaltung erhalten und ermöglicht auch nach Neustart
die Erkennung wiederholter Spiel-/Konfigurationsrequests. Counter werden mit
Gegenbuchungen korrigiert; Undo betrifft ausschließlich Scores.

Atomare Speicherung ersetzt kein Backup. [Sicherung und Wiederherstellung](INSTALLATION.md#backup)
beschreibt die benötigten Dateien.
