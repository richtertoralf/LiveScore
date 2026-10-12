# HTTP- und WebSocket-API

## Live-Daten abrufen

`GET /api/v1/live` liefert den aktuellen Zustand der aktiven Veranstaltung.
Der Endpunkt ist auch bei aktiviertem Login öffentlich lesbar; er benötigt keine
Cookies oder Zugangsdaten. Eine Anzeigetafel, ein Dashboard oder eine Grafiksoftware
kann ihn beispielsweise einmal pro Sekunde abfragen:

```sh
curl --fail http://localhost:8730/api/v1/live
```

Von einem anderen Rechner aus `localhost` durch die Adresse des LiveScore-Servers
ersetzen. Oberfläche und API verwenden denselben konfigurierbaren Port.
Die abfragende Anwendung übernimmt die Darstellung; eine bestimmte Grafiksoftware
ist nicht erforderlich.

### Vollständige Beispielantwort

```json
{
  "status": "live",
  "revision": 6,
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Field 1"
  },
  "left": {
    "id": "bsc-praha",
    "name": "BSC Praha",
    "short_name": "BSC",
    "country_code": "CZ",
    "score": 2,
    "counters": {
      "team_fouls": 0
    },
    "counter_states": {
      "team_fouls": "normal"
    }
  },
  "right": {
    "id": "fc-ingolstadt-04",
    "name": "FC Ingolstadt 04",
    "short_name": "FCI",
    "country_code": "DE",
    "score": 1,
    "counters": {
      "team_fouls": 0
    },
    "counter_states": {
      "team_fouls": "normal"
    }
  },
  "officials": [
    {
      "country_code": "ES",
      "id": "luis-ramon-perez-macias",
      "name": "Luis Ramon Pérez Macias",
      "position": 1,
      "role": "referee",
      "role_label_en": "Referee"
    },
    {
      "country_code": "DE",
      "id": "bennet-kruekemeier",
      "name": "Bennet Krükemeier",
      "position": 2,
      "role": "referee",
      "role_label_en": "Referee"
    },
    {
      "country_code": "ES",
      "id": "juan-carlos-paule",
      "name": "Juan Carlos Paule",
      "position": 3,
      "role": "referee",
      "role_label_en": "Referee"
    }
  ],
  "period": 1,
  "period_info": {
    "number": 1,
    "intermission": false,
    "code": "period_1",
    "label_en": "1. Half",
    "labels": {
      "de": "1. Halbzeit",
      "en": "1. Half",
      "cs": "1. Poločas"
    }
  },
  "stage": {
    "code": "group_stage",
    "name": "Gruppenphase",
    "label_en": "Group stage"
  },
  "round": {
    "code": "group_a",
    "name": "Gruppe A",
    "label_en": "Group A"
  },
  "sport_profile": {
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
        "critical_label": "Double Penalty",
        "translations": {
          "de": {
            "label": "Fouls",
            "warning_label": "Nächstes Foul → Double Penalty",
            "critical_label": "Double Penalty"
          },
          "en": {
            "label": "Fouls",
            "warning_label": "Next foul → Double Penalty",
            "critical_label": "Double Penalty"
          },
          "cs": {
            "label": "Fauly",
            "warning_label": "Další faul → Double Penalty",
            "critical_label": "Double Penalty"
          }
        }
      }
    ],
    "translations": {
      "de": {
        "name": "blind_football",
        "period_label": "Halbzeit",
        "break_label": "Halbzeitpause",
        "hint": ""
      },
      "en": {
        "name": "blind_football",
        "period_label": "Half",
        "break_label": "Half-time",
        "hint": ""
      },
      "cs": {
        "name": "blind_football",
        "period_label": "Poločas",
        "break_label": "Poločasová přestávka",
        "hint": ""
      }
    }
  }
}
```

Das Beispiel entspricht Auswahl, Vorbereitung, Start und drei Score-Aktionen auf
Basis der Beispieldatei und wird automatisiert gegen die API geprüft.
Nach Seitenwechsel enthält `left` Ingolstadt mit 1 und `right` Praha mit 2.
Ohne ausgewähltes Spiel: `status: "idle"`, `period`, `period_info`, `stage`, `round`,
`match_id`, `play_area`, `left` und `right` sind `null`. Beim ausgewählten, noch nicht vorbereiteten Spiel:
`status: "scheduled"`, Match/Play Area sind vorhanden, `left` und `right` sind
`null`. Ein bestätigtes Ergebnis bleibt als `finished` sichtbar, bis ein anderes
Spiel ausgewählt wird. Wird ein beendetes Spiel erneut ausgewählt, liefert die API
dieses Spiel mit `finished` und seinem Endstand; nach **Spiel wieder öffnen** meldet
sie `live`. Fehlende Kurznamen erscheinen als leere Zeichenfolge.
`officials` enthält die aufgelösten Referee-Objekte des aktuellen Matches, bereits
ab `scheduled`. Ohne Match oder ohne Officials ist es `[]`. `/tournament` enthält
zusätzlich die gesamte `referees`-Liste; dort und in `/matches` bleiben
`match.officials` geordnete Listen von Referee-IDs.
`period` nennt den aktuellen Abschnitt, bereits ab `scheduled`.
`left/right.counters` liefern nur die aktuellen Werte; `counter_states` enthält
je Counter `normal`, `warning` oder `critical` (Critical hat Vorrang).
Ohne konfigurierten Counter sind beide Objekte leer. Eine abfragende Anwendung muss keine Periodenhistorie
auswerten. Das Profil steht zusätzlich unter `sport_profile` in der Live-Ausgabe; die Historie
steht im Tournament-State beziehungsweise Export.

### Spielperiode, Turnierphase, Runde und Officials-Funktion

Die folgenden Metadaten stehen ab `scheduled` bereit; bei `idle` sind
`period_info`, `stage` und `round` jeweils `null`:

| Feld | Inhalt |
|---|---|
| `period_info.number` | identisch mit `period` |
| `period_info.intermission` | `true` während einer ausdrücklich gesetzten Pause zwischen zwei Wettkampfabschnitten |
| `period_info.code` | stabiler Code, siehe unten |
| `period_info.label_en` | englischer Abschnitts- oder Pausentext |
| `period_info.labels` | konfigurierte Anzeigetexte für `de`, `en`, `cs` |
| `sport_profile` | aufbereitetes Veranstaltungsprofil oder `null` |
| `stage` | Turnierphase: `code`, `name` (Originaltext), `label_en`; `null` ohne Angabe |
| `round` | Gruppe bzw. Spielrunde aus `match.round`, gleiche Struktur wie `stage` |
| `officials[].position` | Reihenfolge im Spiel ab 1, keine Funktion |
| `officials[].role` / `role_label_en` | `referee` / `Referee` |

`period_info.code` richtet sich nach bestehendem Spielstatus, `period` und
`intermission`:

| Situation | Code |
|---|---|
| `scheduled`, `ready` | `not_started` |
| laufender Abschnitt n | `period_n` |
| Pause nach Abschnitt n | `intermission_after_n` |
| `finished` | `finished` |

Für alle Profile gilt dieselbe Zuordnung. `period_info.labels` enthält DE/EN/CS:
zum Beispiel `{"de":"2. Runde","en":"2. Round","cs":"2. Kolo"}`. Während einer
Abschnittspause enthält es stattdessen die Pausenbezeichnung. `label_en` entspricht
`labels.en`; Status und Abschnittsnummer werden separat geliefert.

`sport_profile` enthält das vollständige Veranstaltungsprofil mit allen aufgelösten
Übersetzungen, der Gesamtzahl der Abschnitte und den Counterdefinitionen. Es steht
auch ohne ausgewähltes Spiel bereit; ohne Profil ist es `null`. Eine externe Anzeige
kann ihre Sprache selbst wählen. Schwellen erzeugen nur `counter_states`, keine Regeln.

### Kompatibilität: Abschnittspausen und Wiederöffnen (Issue #5)

Die Veranstaltung bleibt Schema-Version 1. Version **0.2.0** erweitert Profile um
`translations` und die Live-Ausgabe um `sport_profile` und `period_info.labels`.
Es gibt keine feste Halbzeit-Sonderbehandlung mehr: `first_half`, `second_half`,
`half_time` und `full_time` werden durch die oben dokumentierten generischen Codes
ersetzt. `label_en` enthält nun den konfigurierten Abschnitts- oder Pausentext.
Ältere Clients müssen bei Bedarf angepasst werden; ein Kompatibilitätsmodus ist nicht vorgesehen.
Die installierte Softwareversion steht unter `GET /api/version`.

- Wiederöffnen führt unmittelbar von `finished` nach `live`.
- Alte interne `paused`-Stände werden in der gemeinsamen Live-Projektion als `live`
  dargestellt. Eine Abschnittspause wird ausschließlich durch
  `period_info.intermission: true` angezeigt. Rohe Match-Daten und Exporte behalten
  den gespeicherten Wert; Lesen schreibt keine Datei um.
- Die bereits veralteten `pause`-/`resume`-Endpunkte existieren noch für gespeicherte
  Zustände, sind kein Bedienweg und setzen keine Abschnittspause.
- Die API erlaubt den direkten nächsten Abschnitt; die GUI führt ihn über die Pause.

Score, Seiten, Counterwerte und Officials bleiben erhalten. Bestehende Veranstaltungsdateien,
auch die Prag-Beispiele, bleiben ladbar und unabhängig von der neuen Profilbibliothek.

Für `stage` und `round` gilt diese feste Zuordnung (Vergleich ohne Groß-/Kleinschreibung,
Originaltext bleibt in `name` erhalten):

| Originalwert | `code` | `label_en` |
|---|---|---|
| Gruppenphase | `group_stage` | Group stage |
| Gruppe A … Gruppe Z | `group_a` … `group_z` | Group A … Group Z |
| Play-Offs | `play_offs` | Play-offs |
| semi final #1 / #2 | `semi_final_1` / `semi_final_2` | Semi-final 1 / Semi-final 2 |
| match for place 5th | `fifth_place_match` | 5th-place match |
| bronze medal match | `bronze_medal_match` | Bronze medal match |
| gold medal match | `gold_medal_match` | Gold medal match |

Unbekannte Werte werden nicht übersetzt: `code` und `label_en` sind dann `null`,
`name` enthält den Originaltext. Im Spiel-Editor kann optional ein englischer
Anzeigetext (`stage_label`, `round_label`) hinterlegt werden; er ersetzt dann nur
`label_en`. Teilnehmer- und Personennamen werden nie übersetzt.

Alle Officials eines Spiels sind im Modell Einträge der **Referee**-Liste und
werden deshalb als `referee`/„Referee“ ausgegeben. `position` gibt nur die
Reihenfolge wieder; Funktionen wie Assistant Referee oder Timekeeper werden daraus
nicht abgeleitet.

**Verfügbarkeit** – drei Fälle werden unterschieden:

- *Von der Quelle nicht unterstützt:* Das Feld fehlt ganz, z. B. bei älteren
  LiveScore-Versionen `period_info`/`stage`/`round`/`role`, bei Countern ein
  nicht konfigurierter Counter in `counters`. **Trikotfarben liefert LiveScore
  nicht**; es gibt kein Farbfeld.
- *Unterstützt, aber beim aktuellen Spiel keine Angabe:* `stage`/`round` sind
  `null`, `label_en`/`code` sind `null`, `country_code` ist gemäß bestehendem
  Vertrag `""`, `officials` ist `[]`.
- *Gültiger Wert:* auch `0` ist ein echter Wert, z. B. `counters.team_fouls: 0`.

`country_code` ist ein zweistelliger Ländercode oder `""` und bleibt beim
Seitenwechsel dem Teilnehmer zugeordnet. [Format und Erfassung](DATA_MODEL.md#veranstaltungsdatei).

Diese Felder stehen auch im `live`-Objekt des WebSocket-/Tournament-Snapshots.
Jede Änderung von Abschnittspause, Periode oder Spielplan erhöht `revision`, auch ohne
Scoreänderung; Pollende Clients sehen sie beim nächsten Abruf.

Alle vier GET-Endpunkte (`live`, `tournament`, `matches`, `events`)
beziehen sich immer auf die **aktive Veranstaltung**. Ohne Auswahl bleibt `live`
`idle`, die Match-/Actionlog-Listen sind leer. `/api/v1/events` bleibt das Actionlog,
kein Veranstaltungskatalog. Die externe Live-Revision ist eine
**Event-Revision**, kein globaler Änderungszähler; nach Wechsel kann sie sinken.
LiveScore liefert die Zuordnung zu `left` und `right` bereits aufbereitet;
die Anwendung muss einen Seitenwechsel nicht selbst aus dem Spielverlauf ableiten.
HTTP-Antworten werden mit `Cache-Control: no-store` geliefert.

## Bedien-API

Bei aktiviertem Auth sind diese Endpunkte und der WebSocket geschützt.
Interaktive OpenAPI-Dokumentation liegt unter `/docs`, das Schema unter
`/openapi.json`; beides ist dann nur für Admins zugänglich.

| Methode / Pfad | Bedeutung |
|---|---|
| `GET /api/v1/tournament` | vollständiger UI-Snapshot, ohne Ereignisliste, mit `live` und `can_undo` |
| `GET /api/v1/matches` | Spielplan inklusive Spielstatus und teilnehmerbezogenen Scores |
| `GET /api/v1/events` | Ereignisse ohne interne Request-Signatur |
| `POST /api/v1/config/event` | Veranstaltung setzen |
| `POST /api/v1/config/play-areas` | Play Area anlegen/über ID aktualisieren |
| `POST /api/v1/config/participants` | Teilnehmer anlegen/über ID aktualisieren |
| `POST /api/v1/config/referees` | Referee mit `id`, `name`, optional `country_code` anlegen/aktualisieren |
| `POST /api/v1/config/matches` | geplantes Spiel anlegen/über ID aktualisieren |
| `POST /api/v1/live/select` | geplantes oder beendetes Spiel auswählen |
| `POST /api/v1/live/prepare` | Paarung bestätigen/korrigieren und L/R festlegen |
| `POST /api/v1/live/unprepare` | Vorbereitung zurücknehmen |
| `POST /api/v1/live/start` | vorbereitetes Spiel starten |
| `POST /api/v1/live/score` | +1 oder −1 für Teilnehmer auf angegebener Seite |
| `POST /api/v1/live/counter` | +1 oder −1 für einen Teilnehmer-Counter im aktuellen Abschnitt |
| `POST /api/v1/live/period` | bestätigter Wechsel zum nächsten Abschnitt, nur live/paused |
| `POST /api/v1/live/intermission` | Pause zwischen Abschnitten setzen/zurücknehmen (`intermission`: true/false), nur live/paused |
| `POST /api/v1/live/pause` | veraltet: intern live → paused; Live-Ausgabe bleibt live |
| `POST /api/v1/live/resume` | veraltet: intern paused → live |
| `POST /api/v1/live/switch-sides` | nur L/R tauschen (ready/live/paused) |
| `POST /api/v1/live/undo` | letzte geeignete Score-Aktion zurücknehmen |
| `POST /api/v1/live/finish` | Ergebnis bestätigen (live/paused → finished) |
| `POST /api/v1/live/reopen` | ausgewähltes beendetes Spiel wieder öffnen (finished → live) |
| `POST /api/v1/live/reset` | ausgewähltes Spiel zurücksetzen (ready/live/paused/finished → scheduled), Operator und Admin |
| `WS /api/v1/ws` | initialer UI-Snapshot, weitere Snapshots, Heartbeat alle 5 Sekunden bei Leerlauf |

Mutationen geben den aktuellen UI-Snapshot zurück. Spielaktionen benötigen `request_id`, `event_id`, `selection_token` und `match_id`.
Für Steueraktionen gilt `expected_revision`; Score und Counter verwenden stattdessen
`control_revision`. Alle Kontextwerte stammen aus dem aktuellen UI-Snapshot. `prepare` benötigt
zusätzlich `participant_1`, `participant_2`, `side_l` und `side_r` als IDs.
Config-Aktionen benötigen `request_id`, `expected_revision`, `event_id`,
`selection_token` und `data` mit den
jeweiligen Planfeldern; Status und Scores dürfen dort nicht gesetzt werden.

### Einzelnes Spiel zurücksetzen (Issue #4)

`POST /api/v1/live/reset` verwendet denselben `MatchCommand` wie `finish`:
`request_id`, `event_id`, `selection_token`, `match_id` und `expected_revision`.
Nur das ausgewählte vorbereitete, laufende oder beendete Spiel ist zurücksetzbar.
Ein fremdes Spiel, veralteter Stand oder bereits `scheduled` ergibt **409**.
Wiederholung mit derselben Request-ID und demselben Inhalt ist sicher, auch nach Neustart.

Die Live-Antwort liefert danach `status: "scheduled"`, `left: null`, `right: null`,
`period: 1` und `period_info.code: "not_started"`. Die Paarung bleibt im Spielplan,
aber es gibt keine vorbereiteten Seiten. Nach erneutem `prepare` darf die Paarung
abweichen; Scores und Counter starten bei null. Andere Spiele bleiben unverändert.
`can_undo` und Undo berücksichtigen nur den aktuellen Spielversuch.

Version **0.2.1** ergänzt den Endpunkt und das Ereignis `match_reset`; bestehende
Live-Feldnamen und Veranstaltungsdateien bleiben erhalten, ohne Migration.
Clients, die selbst Scores aus Ereignissen rekonstruieren, müssen `match_reset`
als Reset-Grenze behandeln. Ältere Serverversionen können neue Exporte mit
Reset-Historien wegen ihrer früheren Score-Validierung ablehnen; solche Archive
mit 0.2.1 oder neuer öffnen. Das Zurücksetzen ist keine Ergebnisänderung mit
Datenübernahme: für eine reine Ergebniskorrektur dient weiterhin `reopen`.

Beispiel Score-Request (Werte immer aus aktuellem UI-Snapshot übernehmen):

```json
{
  "request_id": "66cf0c9b-2d91-4e8a-a67c-1cf0738d0be3",
  "event_id": "prague-2026",
  "selection_token": "91ba2d69-83a5-4ef8-acec-5c94b92de77d",
  "match_id": "match-001",
  "control_revision": 2,
  "participant_id": "bsc-praha",
  "side": "L",
  "delta": 1
}
```

Fehler: **422** bei ungültigen Feldern/Referenzen, **409** bei unzulässigem
Übergang oder veraltetem Zustand, **503** bei Speicherfehler. Nach 409 Zustand
neu laden und bewusst erneut bedienen; keine blinde Wiederholung mit neuer Revision.
Nach unklarer Transportantwort ist derselbe Request mit derselben ID wiederholbar.

Spiel- und Konfigurationsrequests werden auch nach Neustart anhand ihrer
`request_id` erkannt: Derselbe Inhalt wird nicht erneut gebucht; eine andere
Aktion mit derselben ID ergibt 409. Die Auswahlkennung schützt vor veralteten
Requests nach einem Veranstaltungswechsel, auch bei A → B → A.

Score- und Counter-Buchungen mit derselben gültigen `control_revision` können
parallel addiert werden. Steueraktionen wie Seitenwechsel, Pause, Undo oder
Abschnittswechsel erhöhen diese Kontrollrevision und machen ältere Buchungen
ungültig. Die Event-Revision erhöht sich dagegen bei jeder Änderung.

`POST /api/v1/live/counter` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `control_revision`, `participant_id`, `counter_id`, die aktuelle `period`
und `delta` (−1 oder +1). Es verwendet wie Score **keine** `expected_revision`.
`POST /api/v1/live/period` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `expected_revision` und die **Zielperiode** `period` (aktuell + 1).
Die Bestätigung erfolgt im Browser; der Server prüft Zustand, Revision und Profilgrenze.
`POST /api/v1/live/intermission` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `expected_revision` und `intermission` (boolean). Setzen ist nur vor dem
letzten Abschnitt möglich; derselbe Zielwert wie der aktuelle ergibt 409.
WebSocket-Heartbeat: `{"heartbeat": true}`. Normale Nachrichten entsprechen
`GET /api/v1/tournament`. Nach spätestens etwa 14 Sekunden ohne Nachricht sperrt
die UI die Bedienung; erkannter Browser-Offline-Status sperrt sofort.

## Veranstaltungskatalog-API

| Methode / Pfad | Bedeutung |
|---|---|
| `GET /api/v1/event-catalog` | `items` mit IDs, Veranstaltungsdaten, Anzahlen und `reset_available`; aktive ID und Auswahlkennung |
| `GET /api/v1/event-catalog/active` | `active_event_id` und `selection_token` |
| `POST /api/v1/event-catalog/create` | neue Veranstaltung; `event` mit Veranstaltungsdaten |
| `POST /api/v1/event-catalog/select` | auswählen; Ziel-`event_id` und bisheriger `selection_token` |
| `POST /api/v1/event-catalog/import/preview` | `json_text` und optionale `event_id`; vollständig validierte Vorschau, `collision`, `preview_token` |
| `POST /api/v1/event-catalog/import` | bestätigter Import mit `json_text`, Vorschau-`event_id`, `preview_token`, `as_new` (Default false) |
| `POST /api/v1/event-catalog/replace` | nur Admin: vorhandene Veranstaltung durch geprüfte Datei ersetzen; `json_text`, `event_id`, `preview_token` aus der Vorschau |
| `POST /api/v1/event-catalog/reset` | nur Admin: Veranstaltung `event_id` aus der gespeicherten Importdatei neu einlesen |
| `GET /api/v1/event-catalog/{event_id}/export` | Download einer einzelnen portablen State-JSON |

`create`, `select`, bestätigter `import`, `replace` und `reset` benötigen außerdem `request_id` und
`catalog_session`. Antworten sind aktuelle UI-Snapshots; Create/Import liefern
zusätzlich `created_event_id`. Anlage und Import aktivieren die Veranstaltung
nicht automatisch. Preview benötigt keine Request-ID und hat keine Seiteneffekte.
Fehlerhafte Syntax/States ergeben 422, ID-/Kontext-/Vorschaukonflikte 409,
Schreibfehler 503, Export einer unbekannten ID 404. Das aktuelle Event wird auch
bei fehlgeschlagenem Import oder Wechsel nicht verändert.

`catalog_session` stammt aus `stream_id`. Wiederholte Katalogrequests werden nur
innerhalb desselben Serverstarts erkannt; nach Neustart werden alte Requests
abgewiesen. Vor einem erneuten Import oder Anlegen die Liste prüfen.

Der UI-Snapshot enthält zusätzlich `active_event_id`, `selection_token`, `catalog`,
`stream_id` und `stream_revision`. Diese Felder gehören nicht zur exportierten
Veranstaltungsdatei und nicht zum stabilen `GET /api/v1/live`-Format.

`stream_id` kennzeichnet den Serverstart, `stream_revision` die Reihenfolge
aller Änderungen seit diesem Start. Browser verwenden beides, um veraltete
HTTP-/WebSocket-Antworten zu verwerfen. Der WebSocket liefert vollständige
Snapshots, keine Änderungsfragmente.

## Anmeldung eigener Clients

Für den öffentlichen Live-Abruf ist dieser Ablauf nicht erforderlich.
Bei aktiviertem Auth benötigen geschützte Endpunkte eine Cookie-Session:

1. `GET /api/auth/session` liefert vor dem Login `csrf_token` und setzt ein
   Login-Cookie. Cookie und Token gemeinsam behalten.
2. `POST /login` mit `username` und `password` als JSON sowie `X-CSRF-Token`
   senden und das neue Session-Cookie übernehmen.
3. `GET /api/auth/session` erneut abrufen. Das nun gelieferte CSRF-Token wird
   für alle Mutationen benötigt, einschließlich `POST /logout`.

Ein mitgesendeter `Origin` muss zum `Host` passen. WebSockets verlangen eine
gültige Session und einen passenden Origin. Fehlende Anmeldung ergibt 401,
fehlende Rechte oder ungültiges CSRF-Token 403; Login-Limits ergeben 429.
Ein Admin mit Startpasswort kann zunächst nur dessen Änderung durchführen.

`GET /api/auth/users` liefert dem Admin Namen, Rollen und Startpasswort-Flags.
`POST /api/auth/password` erwartet `username`, `password`, `repeat` und den
CSRF-Header. Bei eigener Änderung meldet `reauthenticate: true` den nötigen
erneuten Login. [Passwörter und Betrieb](INSTALLATION.md#benutzer-und-passwörter).

## Sportprofilverwaltung (Admin)

Die normale Einrichtung erfolgt über die Weboberfläche. Für Integrationen:

- `GET /api/v1/sport-profiles`: `revision`, `profiles` mit `id` und `profile`;
  zusätzlich `event_profiles` als unabhängige Vorlagen aus Veranstaltungen.
- `POST /api/v1/sport-profiles/save`: `id`, `profile`, `request_id`,
  `catalog_session` und `expected_revision` der **Bibliothek**. Neue ID legt ein Profil an,
  vorhandene ID bearbeitet es.
- `POST /api/v1/sport-profiles/delete`: dieselben Kontrollfelder, ohne `profile`.
- `POST /api/v1/config/sport-profile`: übliche Veranstaltungskontext- und
  Revisionsfelder, `data: {"sport_profile": {…}}` oder `null`. Speichert eine Kopie;
  kein dauerhafter Verweis auf ein Bibliotheksprofil.

Alle diese Endpunkte verlangen Admin-Rechte und bei Mutationen CSRF-Schutz.
Operatoren dürfen ein Profil auch nicht über `config/event`, Neuanlage oder Import
ändern. Anlegen/Importieren/Ersetzen/Zurücksetzen von Veranstaltungen ist Admin-only;
Auswahl, Export, normale Detailpflege und Live-Bedienung bleiben für Operatoren verfügbar.

Bibliothek und Veranstaltung haben getrennte Revisionen. Speichern ist atomar;
`409` verhindert das Überschreiben eines inzwischen geänderten Profils. Änderungen
an der Bibliothek ändern keine Veranstaltungsdaten. Eine Veranstaltungskopie erlaubt
Text- und Schwellenpflege auch während des Wettkampfs; verwendete Strukturänderungen
werden mit `409` abgewiesen. [Änderungsregeln](OPERATOR.md#sportprofile-verwalten-admin).
