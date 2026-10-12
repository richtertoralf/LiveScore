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
`intermission`, `counters`, `period_scores` und `sets_won`.

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
| Einzelnes Spiel zurücksetzen | `ready/live/paused/finished → scheduled` |

`ready` verlangt zwei verschiedene bekannte Teilnehmer, eine gültige
Seitenzuordnung und Scores von null. Score, Counter und Undo sind nur bei
`live` oder `paused` möglich; Seitenwechsel zusätzlich bei `ready`.
Auswählbar sind geplante oder beendete Spiele, solange kein anderes Spiel
`ready`, `live` oder `paused` ist. `idle` ist ein API-Zustand ohne ausgewähltes Spiel,
kein gespeicherter Match-Status.

`paused` wird ausschließlich als gespeicherter Bestandszustand unterstützt.
Die bisherigen `pause`-/`resume`-API-Aktionen sind entfernt. Die aufbereitete Live-Ausgabe stellt `paused` als `live` dar; der rohe State
und Exporte behalten den gespeicherten Wert. Es ist keine Datenmigration erforderlich.

## Sportprofil

`event.sport_profile` konfiguriert Erfassung und Anzeige, Abschnitte, feste Rollen und teilnehmerbezogene Zähler.
Der Admin pflegt es über **Konfiguration → Sportprofile**. Die Veranstaltung speichert
eine vollständige Kopie, ohne Laufzeitverweis auf die Bibliothek. Beispiel:

```json
{
  "sport": "blind_football",
  "ruleset": "IBSA 2025-2029",
  "periods": 2,
  "period_label": "Halbzeit",
  "translations": {
    "de": {"name": "Blindenfußball", "period_label": "Halbzeit", "break_label": "Halbzeitpause", "hint": ""},
    "en": {"name": "Blind football", "period_label": "Half", "break_label": "Half-time", "hint": ""},
    "cs": {"name": "Fotbal nevidomých", "period_label": "Poločas", "break_label": "Poločasová přestávka", "hint": ""}
  },
  "counters": [
    {
      "id": "team_fouls",
      "label": "Fouls",
      "scope": "participant",
      "reset_each_period": true,
      "warning_at": 4,
      "critical_at": 5,
      "warning_label": "Nächstes Foul → Double Penalty",
      "critical_label": "Double Penalty",
      "translations": {
        "de": {"label": "Fouls", "warning_label": "Nächstes Foul → Double Penalty", "critical_label": "Double Penalty"},
        "en": {"label": "Fouls", "warning_label": "Next foul → Double Penalty", "critical_label": "Double Penalty"},
        "cs": {"label": "Fauly", "warning_label": "Další faul → Double Penalty", "critical_label": "Double Penalty"}
      }
    }
  ]
}
```

`sport` und `ruleset` bleiben für Bestandsdateien als beschreibende Metadaten erhalten.
Sie wählen keine Programmfunktion und werden im Editor nicht benötigt. Neue Profile
verwenden zunächst `sport: "generic"`; der sichtbare Name steht in `translations`. `periods` ist positiv,
`period_label` frei wählbar, Counter-IDs sind eindeutig. Unterstützt wird
`scope: "participant"`. Warnschwellen sind Anzeigehilfen, keine Obergrenzen
und keine automatische Sportregel. Wenn beide Schwellen gesetzt sind, muss
`warning_at` kleiner als `critical_at` sein.

### Punkte und Satzstand

`score_mode` ist `total`, `period` oder `none`; fehlend bedeutet `total`.
`score_steps` enthält eindeutige positive Ganzzahlen (Default `[1]`),
`sets_enabled` aktiviert den manuellen Satzstand (Default `false`).
`show_details` und `show_officials` sind standardmäßig `true`.

`match.scores[participant_id]` ist bei `total` der Gesamtstand, bei `period` nur der
aktuelle Abschnitt. `none` führt intern vorbereitete Nullwerte für die Paarung;
die öffentliche API liefert ausdrücklich `score: null`, keinen erfundenen Spielstand.
Bei `period` liegen alle erfassten Abschnitte unter
`period_scores[period_als_string][participant_id]`. Aktuelle Abschnittspunkte müssen
exakt mit `scores` übereinstimmen. Abschnittswechsel speichert frühere Werte und legt
für den neuen Abschnitt echte Nullwerte an. Es wird kein Gesamtstand summiert.

`sets_won[participant_id]` speichert manuelle Satzgewinne, unabhängig von Punkten
und ohne automatische Gewinnerermittlung. Fehlende `period_scores` und `sets_won`
werden als `{}` geladen. Bei deaktivierter Satzerfassung sind keine Satzwerte erlaubt;
bei aktivierter Satzerfassung ohne importierte Werte liefert die API `null`.
Vorbereitung initialisiert Nullwerte. Alle erfassten Zahlen sind nichtnegativ und
teilnehmerbezogen; vor Spielbeginn müssen sie null sein.

Punkteereignisse können konfigurierte Schritte mit positivem oder negativem
Vorzeichen enthalten. Bei `period` tragen sie die betroffene `period`.
Manuelle Satzereignisse haben `type: "sets"` und `delta: 1` oder `-1`.
Undo korrigiert den ursprünglichen Abschnitt oder Satzstand; eine Änderung an einem
früheren Abschnitt ersetzt niemals die aktuellen Abschnittspunkte.

`roles` ordnet `participant_1` und `participant_2` je `{id, labels: {de, en, cs}}` zu.
Die Rollen-IDs sind innerhalb des Profils eindeutig, unabhängig von den Beschriftungen.
Im Boxprofil lauten sie `red` und `blue`; das Programm behandelt sie wie alle anderen
Rollen-IDs. Zuordnung über die Paarung, niemals über `side_l` / `side_r`.

`enabled` an einer Counterdefinition ist standardmäßig `true`. Ausblenden erhält
historische Werte, verhindert aber neue Bedienaktionen und entfernt den Counter aus
der öffentlichen Werteanzeige. Die Definition bleibt im Profil verfügbar.

Standardprofile und die gemeinsame Pflege aller drei Sprachen sind in
[SPORT_PROFILES.md](SPORT_PROFILES.md) beschrieben.

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
Die Struktur (`periods`, `score_mode`, `sets_enabled`, Counter-IDs und `reset_each_period`) ist ab Vorbereitung
festgelegt; nach Zurücknehmen der Vorbereitung ist sie wieder bearbeitbar, sofern
alle Spiele wieder geplant sind. Das gilt auch nach ausdrücklichem Zurücksetzen
aller Spiele; alte Ereignisse beschreiben dann keine aktuellen Ergebnisse mehr.
Texte, Punkteschritte, Rollenbezeichnungen, Sichtbarkeit, Schwellen und Zählerreihenfolge bleiben bearbeitbar.
Vor dem ersten Spiel werden bei Strukturänderungen nur leere Counterhistorien
neu initialisiert. Erfasste Werte werden niemals durch Profilpflege gelöscht.

Ohne Profil gelten ein Abschnitt und keine Zähler. Fehlende optionale Felder
werden kompatibel ergänzt: `referees`/`officials` als leere Listen,
`period` als `1`, `counters` als `{}`, `intermission` als `false` und zusätzliche
Phasen-/Rundenlabels als `""`. Die Schema-Version bleibt 1;
unbekannte Versionen werden abgewiesen.

### Mehrsprachigkeit und Bibliothek

Ein Profil enthält alle Sprachen unter `translations.de`, `.en` und `.cs`:
`name`, `period_label`, `break_label`, `score_label`, `sets_label` und `hint`. Counter verwenden dort
`label`, `warning_label` und `critical_label`. Keine separaten Sprachdateien.
Abschnittsnummern gehören weiterhin zum Match (`period`), nicht zur Vorlage.

Die bisherigen skalaren Texte bleiben als Fallback erhalten. Fehlende Übersetzungen
werden beim Anzeigen ergänzt: bekannte Begriffe werden übersetzt, eigene Texte bleiben
unverändert; leere Warntexte erhalten einen neutralen Hinweis. Lesen schreibt keine
Dateien um. Speichern im Editor hält alle drei Sprachen gemeinsam im Profil fest.

`data/sport-profiles.json` enthält `schema_version: 1`, eine eigene `revision` und
`profiles: [{"id": "…", "profile": {…}}]`. Fehlt die Datei, wird sie mit den sieben Standardprofilen angelegt.
`bundled_profiles` merkt sich bereits bereitgestellte Standard-IDs, auch nach einer
bewussten Löschung. Wiederholte Bereitstellung überschreibt keine Profile. Eingebettete Profile werden als Vorlagen
angeboten, ohne automatische Migration oder Kopplung. Neue Bibliotheks-IDs und Counter-IDs
werden in der GUI erzeugt; beim Bearbeiten bleiben sie stabil. Eine zentrale Datei ist
für diese kleine Bibliothek einfacher atomar zu speichern und zu sichern als mehrere Dateien.

Prag-JSON-Dateien bleiben unverändert ladbar. Teilnehmer, Paarungen, Play Areas und
Officials sind sportartenneutral; eine noch nicht gestartete Veranstaltung kann beispielsweise
auf drei Runden und eigene Counter umgestellt werden. Beschreibungen wie `Field 1` oder
`Gruppenphase` werden dabei nicht automatisch in Boxbegriffe umgeschrieben.
Eine bereits gespielte Veranstaltung dient als Archiv, nicht als Vorlage für eine
andere Wettkampfstruktur; dafür eine neue Veranstaltung samt Spielplan anlegen.

## Dateien und Migration

```text
data/
  events/<event-id>.json
  imports/<event-id>.json
  sport-profiles.json        # unabhängig gespeicherte Vorlagen und bereitgestellte Standard-IDs
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

Die Ereignisliste speichert relevante Zustandswechsel und Punkte-/Satz-/Zähleraktionen
mit Spiel-/Teilnehmerbezug, Zeitstempel, Revision und Request-ID. Score-Undo markiert
das ursprüngliche Ereignis als zurückgenommen und verweist darauf.
`match_reset` bildet die Grenze zwischen zwei Spielversuchen derselben Match-ID.
Zurücksetzen erhält Planfelder und Ereignisse; es leert Scores, Abschnittspunkte, Satzstand, Seiten und Counter,
setzt `period: 1`, `intermission: false` und `status: scheduled`. Die Kontrollrevision
steigt weiter und bleibt auch bei anschließender Spielplanbearbeitung erhalten.
Validierung und Undo prüfen die aktuellen Scores ausschließlich gegen Punkte-/Satzereignisse
nach der letzten Reset-Grenze. Ältere Score-Ereignisse müssen weiterhin auf bekannte
Spiele und Teilnehmer verweisen und ein gültiges Delta besitzen; sie dürfen zur
früheren, inzwischen korrigierten Paarung gehören. Ihre Undo-Markierungen bleiben
unverändert. Andere Spiele erhalten keine neue Undo-Grenze.

Die Liste bleibt für die Veranstaltung erhalten und ermöglicht auch nach Neustart
die Erkennung wiederholter Spiel-/Konfigurationsrequests. Counter werden mit
Gegenbuchungen korrigiert; Undo betrifft Punkte und manuell erfasste Satzgewinne.

Atomare Speicherung ersetzt kein Backup. [Sicherung und Wiederherstellung](INSTALLATION.md#backup)
beschreibt die benötigten Dateien.
