# HTTP- und WebSocket-API

## Öffentliche Live-Daten

`GET /api/v1/live` ist ohne Anmeldung verfügbar und liefert eine konsistente,
für Grafiken aufbereitete Momentaufnahme. Polling, etwa einmal pro Sekunde,
genügt; Antworten tragen `Cache-Control: no-store`.

```sh
curl --fail http://localhost:8730/api/v1/live
```

Die API entscheidet anhand der Veranstaltungskonfiguration, welche Daten vorgesehen
sind. Sie berechnet weder Gewinner noch Sportregeln und steuert kein SHOW/HIDE im
Grafiksystem. Kein Verbraucher muss einen Sportnamen auswerten, Seitenwechsel
nachbauen oder frühere Satzpunkte zum Gesamtstand addieren.

## Antwortformat

| Feld | Bedeutung |
|---|---|
| `source` | Verfügbarkeit und Kontext der konsistenten Serverantwort |
| `source.available` | `true` bei einer erfolgreich gelieferten Momentaufnahme; keine Aussage über einen externen Dienst |
| `source.instance_id` | Kennung des Serverstarts; ändert sich beim Neustart |
| `source.revision` | Monotoner Änderungszähler innerhalb dieses Serverstarts, auch bei Veranstaltungswechseln |
| `source.event_id` | Aktive Veranstaltungs-ID, sonst `null` |
| `source.selection_token` | Auswahlkennung; ändert sich auch bei Wechsel A → B → A und Ersetzen/Zurücksetzen der Veranstaltung |
| `revision` | Persistente Revision der aktiven Veranstaltung; kann beim Wechsel sinken |
| `status` | `idle`, `scheduled`, `ready`, `live` oder `finished` |
| `pairing_confirmed` | Ob eine Paarung und ihre Bildschirmseiten bestätigt sind |
| `match_id`, `play_area` | Ausgewähltes Spiel und aufgelöste Wettkampffläche; ohne Auswahl `null` |
| `sport_profile` | Effektive Profilkonfiguration mit sämtlichen DE/EN/CS-Texten und Counterdefinitionen |
| `display` | Welche Informationen zur Darstellung vorgesehen sind |
| `left`, `right` | Bestätigte Teilnehmer, bereits den Bildschirmseiten zugeordnet; sonst `null` |
| `period`, `period_info` | Aktueller Abschnitt und fertig beschrifteter Abschnitts-/Pausenzustand |
| `stage`, `round` | Turnierphase und Spielplangruppe/-runde als `{code, name, label_en}`, sonst `null` |
| `officials` | Aufgelöste Officials in Spielplanreihenfolge, bei aktivierter Funktion; sonst `null` |

Ein Serverstart mit aktiver Veranstaltung ohne explizites Profil verwendet das
Standardmodell: fortlaufender Score mit ±1, ein Abschnitt, keine Zähler oder festen
Rollen, kein Satzstand. Das effektive `sport_profile` beschreibt diesen generischen
Fall ebenfalls. Ohne aktive Veranstaltung sind `sport_profile` und `display` `null`,
der Status ist `idle`.

### Funktionen und Beschriftungen

| Profil-/Anzeigefeld | Bedeutung |
|---|---|
| `display.score` | Score vorgesehen; `false` bedeutet ausdrücklich keine Score-Anzeige |
| `display.score_mode` | `none`, `total` (fortlaufend) oder `period` (aktuelle Abschnittspunkte) |
| `display.sets` | Gewonnene Sätze zusätzlich vorgesehen |
| `display.counters` | IDs der aktivierten und relevanten Counter |
| `display.details`, `display.officials` | Spielplanmetadaten beziehungsweise Officials zur Anzeige vorgesehen |
| `sport_profile.score_steps` | Manuelle Plus-/Minus-Schritte, beispielsweise `[1, 2]` |
| `sport_profile.periods` | Konfigurierte maximale Abschnittszahl, kein automatisch auszuspielendes Format |
| `sport_profile.translations` | Für `de`, `en`, `cs`: `name`, `period_label`, `break_label`, `score_label`, `sets_label`, `hint` |
| `sport_profile.roles` | Feste Rollen für `participant_1` / `participant_2`, mit stabiler `id` und `labels` in DE/EN/CS |
| `sport_profile.counters` | Definitionen mit stabiler `id`, `enabled`, `reset_each_period`, optionalen Schwellen und dreisprachigen Texten |

Alle konfigurierten Counterdefinitionen werden geliefert, auch deaktivierte. Nur
aktivierte Counter stehen in `display.counters` und in den aktuellen Teilnehmerwerten.
`warning_at`/`critical_at` sind Anzeigegrenzen, keine Wertbegrenzungen. Die Countertexte
stehen unter `translations.<sprache>.label`, `.warning_label`, `.critical_label`.
Leere Bestandsübersetzungen erhalten beim Lesen einen Fallback, ohne die Datei umzuschreiben.
`sport` und `ruleset` sind beschreibende Metadaten und wählen keine Programmfunktion.

### Teilnehmerwerte

Jede Seite enthält `id`, `name`, `short_name`, `country_code`, `score`, `sets_won`,
`period_scores`, `counters`, `counter_states` und `role`.

- `score`: Nichtnegative Zahl, wenn Punkteerfassung vorgesehen und die Paarung
  bestätigt ist. Bei `total` der Gesamtstand, bei `period` ausschließlich die Punkte
  des aktuellen Abschnitts. Bei `none` ausdrücklich `null`.
- `sets_won`: Separater, manuell erfasster Satzstand. Bei deaktivierter Funktion
  `null`; bei aktiviertem Profil und noch fehlendem importierten Wert ebenfalls
  `null`. Vorbereitung eines neuen Spiels legt echte Nullwerte an.
- `period_scores`: Nur bei `period` eine Historie wie `{"1": 11, "2": 3}`;
  nummerierte Abschnitte einschließlich des aktuellen. In anderen Modi `null`.
- `counters`: Aktuelle Werte der aktivierten Counter, etwa `{"team_fouls": 0}`.
  Nicht konfigurierte oder ausgeblendete Counter fehlen. Ohne aktivierte Counter `{}`.
- `counter_states`: Je aktivierter Counter `normal`, `warning` oder `critical`;
  `critical` hat Vorrang. Die zugehörigen Hinweise liefert das Profil.
- `role`: `{id, labels}` für die feste Teilnehmerrolle oder `null`. Die ID kann
  beispielsweise `red` oder `blue` sein; sie wählt keine Backend-Logik.

Teilnehmernamen werden nicht übersetzt. Fehlende Kurznamen und Länder sind `""`;
Länder sind zweistellige Codes wie `CZ` oder `DE`. Logos und grafische Farben sind
keine Vorgaben der Live-API.

Ein Seitenwechsel vertauscht ausschließlich `left` und `right`. Punkte, Satzgewinne,
Historien, Länder und feste Rollen bleiben beim jeweiligen Teilnehmer. Die Rolle
wird über die Paarung vergeben, nicht über die Bildschirmposition. Im Standardboxprofil
gehört Teilnehmer 1 zur roten und Teilnehmer 2 zur blauen Ecke; die Oberfläche zeigt
bei Paarungsauswahl diese Rollenbezeichnungen.

### Abschnitte und Zustände

`period_info` enthält `number`, `total`, `intermission`, `code`, `labels`,
`period_labels` und `label_en`. `number` entspricht `period`; `total` ist die
konfigurierte Abschnittszahl. `period_labels` beschriftet stets den aktuellen
Abschnitt, etwa `{"de":"2. Runde","en":"Round 2","cs":"2. Kolo"}`.
`labels` enthält während der Pause stattdessen die Pausenbezeichnung; `label_en`
ist identisch mit `labels.en`. Der Renderer wählt seine Sprache selbst.

| Zustand | Abschnittscode / Bedeutung |
|---|---|
| `idle` | Kein ausgewähltes Spiel; `period_info`, `period`, `left`, `right` sind `null` |
| `scheduled` | Paarung unbestätigt, `pairing_confirmed: false`, Seiten `null`, Code `not_started` |
| `ready` | Paarung bestätigt, echte Anfangswerte vorhanden, Code `not_started` |
| `live` | Laufender Abschnitt: `period_n` |
| `live` mit `intermission: true` | Pause nach Abschnitt n: `intermission_after_n` |
| `finished` | Bestätigte Daten bleiben sichtbar; Code `finished` |

Abschnittspausen sind ausschließlich Pausen zwischen zwei Abschnitten. Der nächste
Abschnitt beendet die Pause. Wiederöffnen liefert sofort `live` und erhält Daten;
Zurücksetzen liefert `scheduled`, unbestätigte Paarung und keine Seitenwerte.
Alte gespeicherte `paused`-Zustände werden beim Lesen als laufender Wettkampf
aufbereitet; eine Abschnittspause wird nur durch `intermission` gekennzeichnet.

### Verfügbarkeit und Änderungserkennung

| Situation | Erkennung |
|---|---|
| Funktion deaktiviert | `display`-Flag ist `false` bzw. ID fehlt; entsprechende optionale Werte sind `null` oder Counterwerte fehlen |
| Funktion aktiviert, noch ohne Daten | Flag ist aktiv, Wert `null`; beispielsweise importierter, noch nicht erfasster Satzstand |
| Gültiger Nullwert | Zahl `0`, beispielsweise echter Torstand von 0:0 |
| Noch keine bestätigte Paarung | `pairing_confirmed: false`, `left/right: null`, auch bei bereits bekannten geplanten Teilnehmern |
| Keine Veranstaltungs-/Spielauswahl | `source.event_id: null` beziehungsweise `match_id: null`, `status: idle` |
| Verbindung/Datenquelle nicht erreichbar | Transportfehler oder nicht erfolgreiche HTTP-Antwort; keine gültige neue Momentaufnahme |

Bei einem Transportfehler niemals aus einer alten oder leeren Antwort 0:0 ableiten.
Ein Verbraucher kann den letzten bestätigten Stand behalten und selbst einen
Verbindungsstatus anzeigen. LiveScore kann bei Nichterreichbarkeit keine HTTP-Antwort
mit `available: false` senden.

Für Änderungen und das Verwerfen verspäteter Antworten `source.instance_id` und
`source.revision` gemeinsam auswerten. Eine neue Instanz ist ein neuer Stream;
innerhalb derselben Instanz ältere Revisionen verwerfen. `source.event_id` und
`source.selection_token` unterscheiden Veranstaltungswechsel und neu geladene Daten.
Profilpflege, Paarung, Punkte, Rollen, Abschnitte, Zurücksetzen und Wiederöffnen
ändern die Revision. Weder Spielstart noch Abschnittswechsel löst eine externe
Grafikaktion aus.

Bei deaktivierten Spielplanangaben sind `stage` und `round` `null`; bei deaktivierten
Officials ist `officials` `null`. Bei aktivierten Officials ohne Zuordnung ist die
Liste `[]`. Officials enthalten `id`, `name`, `country_code`, `position`, `role` und
`role_label_en`; da das Modell nur Referees verwaltet, lautet die Funktion `referee`.
`position` bezeichnet die Listenreihenfolge, keine abgeleitete Funktion.

Für Phasen und Runden bleiben bekannte Spielplanbegriffe mit Code/Englisch aufbereitet:
„Gruppenphase“ → `group_stage`, „Gruppe A“ → `group_a`, „Play-Offs“ → `play_offs`,
„semi final #1“ → `semi_final_1`, „bronze medal match“ → `bronze_medal_match` usw.
Bei eigenen Bezeichnungen ist `name` vorhanden, aber `code`/`label_en` können `null`
sein. Explizite `stage_label` und `round_label` ersetzen den englischen Fallback.

## Vollständige Beispielantworten

Die folgenden eigenständigen Beispielantworten werden gegen die Implementierung
geprüft; es sind keine realen Wettkampfergebnisse. Die UUIDs unter
`source` sind Beispielwerte und werden vom laufenden Server erzeugt. Das erste Beispiel
entspricht Auswahl, Vorbereitung, Start und drei Score-Aktionen mit der Prag-Datei.

<details>
<summary>Blindenfußball mit Teamfouls</summary>

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
    },
    "sets_won": null,
    "period_scores": null,
    "role": null
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
    },
    "sets_won": null,
    "period_scores": null,
    "role": null
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
    "total": 2,
    "intermission": false,
    "code": "period_1",
    "period_labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
      "cs": "1. Poločas"
    },
    "label_en": "Half 1",
    "labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
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
        "enabled": true,
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
        "hint": "",
        "score_label": "Tore",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "blind_football",
        "period_label": "Half",
        "break_label": "Half-time",
        "hint": "",
        "score_label": "Tore",
        "sets_label": "Sets won"
      },
      "cs": {
        "name": "blind_football",
        "period_label": "Poločas",
        "break_label": "Poločasová přestávka",
        "hint": "",
        "score_label": "Tore",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "total",
    "score_steps": [
      1
    ],
    "sets_enabled": false,
    "roles": {},
    "show_details": true,
    "show_officials": true
  },
  "pairing_confirmed": true,
  "display": {
    "score": true,
    "score_mode": "total",
    "sets": false,
    "counters": [
      "team_fouls"
    ],
    "details": true,
    "officials": true
  },
  "source": {
    "available": true,
    "instance_id": "df46207c-b113-4efb-b4d9-2103c98e3f28",
    "revision": 6,
    "event_id": "prague-2026",
    "selection_token": "91ba2d69-83a5-4ef8-acec-5c94b92de77d"
  }
}
```

</details>

<details>
<summary>Boxen ohne Score, Runde 2</summary>

```json
{
  "status": "live",
  "revision": 6,
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Ring A"
  },
  "left": {
    "id": "alex-novak",
    "name": "Alex Novák",
    "short_name": "NOV",
    "country_code": "CZ",
    "score": null,
    "counters": {},
    "counter_states": {},
    "sets_won": null,
    "period_scores": null,
    "role": {
      "id": "red",
      "labels": {
        "de": "Rote Ecke",
        "en": "Red corner",
        "cs": "Červený roh"
      }
    }
  },
  "right": {
    "id": "jan-svoboda",
    "name": "Jan Svoboda",
    "short_name": "SVO",
    "country_code": "CZ",
    "score": null,
    "counters": {},
    "counter_states": {},
    "sets_won": null,
    "period_scores": null,
    "role": {
      "id": "blue",
      "labels": {
        "de": "Blaue Ecke",
        "en": "Blue corner",
        "cs": "Modrý roh"
      }
    }
  },
  "officials": null,
  "period": 2,
  "period_info": {
    "number": 2,
    "total": 3,
    "intermission": false,
    "code": "period_2",
    "period_labels": {
      "de": "2. Runde",
      "en": "Round 2",
      "cs": "2. Kolo"
    },
    "label_en": "Round 2",
    "labels": {
      "de": "2. Runde",
      "en": "Round 2",
      "cs": "2. Kolo"
    }
  },
  "stage": null,
  "round": null,
  "sport_profile": {
    "sport": "boxing",
    "ruleset": "",
    "periods": 3,
    "period_label": "Runde",
    "counters": [],
    "translations": {
      "de": {
        "name": "Boxen",
        "period_label": "Runde",
        "break_label": "Rundenpause",
        "hint": "",
        "score_label": "",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "Boxing",
        "period_label": "Round",
        "break_label": "Round break",
        "hint": "",
        "score_label": "",
        "sets_label": "Sets won"
      },
      "cs": {
        "name": "Box",
        "period_label": "Kolo",
        "break_label": "Přestávka mezi koly",
        "hint": "",
        "score_label": "",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "none",
    "score_steps": [
      1
    ],
    "sets_enabled": false,
    "roles": {
      "participant_1": {
        "id": "red",
        "labels": {
          "de": "Rote Ecke",
          "en": "Red corner",
          "cs": "Červený roh"
        }
      },
      "participant_2": {
        "id": "blue",
        "labels": {
          "de": "Blaue Ecke",
          "en": "Blue corner",
          "cs": "Modrý roh"
        }
      }
    },
    "show_details": false,
    "show_officials": false
  },
  "pairing_confirmed": true,
  "display": {
    "score": false,
    "score_mode": "none",
    "sets": false,
    "counters": [],
    "details": false,
    "officials": false
  },
  "source": {
    "available": true,
    "instance_id": "9ade0c95-a7ba-59b6-85b2-462bd2eb8b0b",
    "revision": 6,
    "event_id": "boxing-demo",
    "selection_token": "11ab1bb9-dd89-59fc-89f3-5e66e9cda8d1"
  }
}
```

</details>

<details>
<summary>Fußball mit Torstand</summary>

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
    "counters": {},
    "counter_states": {},
    "sets_won": null,
    "period_scores": null,
    "role": null
  },
  "right": {
    "id": "fc-ingolstadt-04",
    "name": "FC Ingolstadt 04",
    "short_name": "FCI",
    "country_code": "DE",
    "score": 1,
    "counters": {},
    "counter_states": {},
    "sets_won": null,
    "period_scores": null,
    "role": null
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
    "total": 2,
    "intermission": false,
    "code": "period_1",
    "period_labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
      "cs": "1. Poločas"
    },
    "label_en": "Half 1",
    "labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
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
    "sport": "football",
    "ruleset": "",
    "periods": 2,
    "period_label": "Halbzeit",
    "counters": [],
    "translations": {
      "de": {
        "name": "Fußball",
        "period_label": "Halbzeit",
        "break_label": "Halbzeitpause",
        "hint": "",
        "score_label": "Tore",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "Football",
        "period_label": "Half",
        "break_label": "Half-time",
        "hint": "",
        "score_label": "Goals",
        "sets_label": "Sets won"
      },
      "cs": {
        "name": "Fotbal",
        "period_label": "Poločas",
        "break_label": "Poločasová přestávka",
        "hint": "",
        "score_label": "Góly",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "total",
    "score_steps": [
      1
    ],
    "sets_enabled": false,
    "roles": {},
    "show_details": true,
    "show_officials": true
  },
  "pairing_confirmed": true,
  "display": {
    "score": true,
    "score_mode": "total",
    "sets": false,
    "counters": [],
    "details": true,
    "officials": true
  },
  "source": {
    "available": true,
    "instance_id": "68dacc2e-fd14-5c47-a2fa-f94de70e0893",
    "revision": 6,
    "event_id": "football-demo",
    "selection_token": "16780a85-2451-52de-a922-1b86e65f745f"
  }
}
```

</details>

<details>
<summary>Tischtennis mit Satzpunkten und gewonnenen Sätzen</summary>

```json
{
  "status": "live",
  "revision": 6,
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Table 1"
  },
  "left": {
    "id": "alex-novak",
    "name": "Alex Novák",
    "short_name": "NOV",
    "country_code": "CZ",
    "score": 3,
    "counters": {},
    "counter_states": {},
    "sets_won": 1,
    "period_scores": {
      "1": 11,
      "2": 3
    },
    "role": null
  },
  "right": {
    "id": "jan-svoboda",
    "name": "Jan Svoboda",
    "short_name": "SVO",
    "country_code": "CZ",
    "score": 4,
    "counters": {},
    "counter_states": {},
    "sets_won": 0,
    "period_scores": {
      "1": 8,
      "2": 4
    },
    "role": null
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
  "period": 2,
  "period_info": {
    "number": 2,
    "total": 5,
    "intermission": false,
    "code": "period_2",
    "period_labels": {
      "de": "2. Satz",
      "en": "Game 2",
      "cs": "2. Set"
    },
    "label_en": "Game 2",
    "labels": {
      "de": "2. Satz",
      "en": "Game 2",
      "cs": "2. Set"
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
    "sport": "table-tennis",
    "ruleset": "",
    "periods": 5,
    "period_label": "Satz",
    "counters": [],
    "translations": {
      "de": {
        "name": "Tischtennis",
        "period_label": "Satz",
        "break_label": "Satzpause",
        "hint": "Best-of-Five als Ausgangspunkt; andere Formate vor Spielbeginn einstellen.",
        "score_label": "Satzpunkte",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "Table tennis",
        "period_label": "Game",
        "break_label": "Game interval",
        "hint": "Best of five by default; configure other formats before play.",
        "score_label": "Game points",
        "sets_label": "Games won"
      },
      "cs": {
        "name": "Stolní tenis",
        "period_label": "Set",
        "break_label": "Přestávka mezi sety",
        "hint": "Výchozí formát na tři vítězné sety; jiný formát nastavte před zápasem.",
        "score_label": "Body v setu",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "period",
    "score_steps": [
      1
    ],
    "sets_enabled": true,
    "roles": {},
    "show_details": true,
    "show_officials": true
  },
  "pairing_confirmed": true,
  "display": {
    "score": true,
    "score_mode": "period",
    "sets": true,
    "counters": [],
    "details": true,
    "officials": true
  },
  "source": {
    "available": true,
    "instance_id": "cc05619b-722f-57f0-8791-dfb5170d7db7",
    "revision": 6,
    "event_id": "table-tennis-demo",
    "selection_token": "a4678969-670e-52a2-a6a4-80ff277b62e2"
  }
}
```

</details>

<details>
<summary>Volleyball in der Satzpause</summary>

```json
{
  "status": "live",
  "revision": 6,
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Court 1"
  },
  "left": {
    "id": "vc-praha",
    "name": "VC Praha",
    "short_name": "PRA",
    "country_code": "CZ",
    "score": 22,
    "counters": {},
    "counter_states": {},
    "sets_won": 1,
    "period_scores": {
      "1": 25,
      "2": 22
    },
    "role": null
  },
  "right": {
    "id": "berlin-volley",
    "name": "Berlin Volley",
    "short_name": "BER",
    "country_code": "DE",
    "score": 25,
    "counters": {},
    "counter_states": {},
    "sets_won": 1,
    "period_scores": {
      "1": 20,
      "2": 25
    },
    "role": null
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
  "period": 2,
  "period_info": {
    "number": 2,
    "total": 5,
    "intermission": true,
    "code": "intermission_after_2",
    "period_labels": {
      "de": "2. Satz",
      "en": "Set 2",
      "cs": "2. Set"
    },
    "label_en": "Set break",
    "labels": {
      "de": "Satzpause",
      "en": "Set break",
      "cs": "Přestávka mezi sety"
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
    "sport": "volleyball",
    "ruleset": "",
    "periods": 5,
    "period_label": "Satz",
    "counters": [],
    "translations": {
      "de": {
        "name": "Volleyball",
        "period_label": "Satz",
        "break_label": "Satzpause",
        "hint": "",
        "score_label": "Satzpunkte",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "Volleyball",
        "period_label": "Set",
        "break_label": "Set break",
        "hint": "",
        "score_label": "Set points",
        "sets_label": "Sets won"
      },
      "cs": {
        "name": "Volejbal",
        "period_label": "Set",
        "break_label": "Přestávka mezi sety",
        "hint": "",
        "score_label": "Body v setu",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "period",
    "score_steps": [
      1
    ],
    "sets_enabled": true,
    "roles": {},
    "show_details": true,
    "show_officials": true
  },
  "pairing_confirmed": true,
  "display": {
    "score": true,
    "score_mode": "period",
    "sets": true,
    "counters": [],
    "details": true,
    "officials": true
  },
  "source": {
    "available": true,
    "instance_id": "a879d8ba-d6a7-5703-948d-d9bcabb1f633",
    "revision": 6,
    "event_id": "volleyball-demo",
    "selection_token": "7408b6d0-dd9b-5ae5-b1e4-e9d5e21b36d3"
  }
}
```

</details>

<details>
<summary>Keine vorbereitete Paarung</summary>

```json
{
  "status": "scheduled",
  "revision": 6,
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Field 1"
  },
  "left": null,
  "right": null,
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
    "total": 2,
    "intermission": false,
    "code": "not_started",
    "period_labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
      "cs": "1. Poločas"
    },
    "label_en": "Half 1",
    "labels": {
      "de": "1. Halbzeit",
      "en": "Half 1",
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
    "sport": "football",
    "ruleset": "",
    "periods": 2,
    "period_label": "Halbzeit",
    "counters": [],
    "translations": {
      "de": {
        "name": "Fußball",
        "period_label": "Halbzeit",
        "break_label": "Halbzeitpause",
        "hint": "",
        "score_label": "Tore",
        "sets_label": "Gewonnene Sätze"
      },
      "en": {
        "name": "Football",
        "period_label": "Half",
        "break_label": "Half-time",
        "hint": "",
        "score_label": "Goals",
        "sets_label": "Sets won"
      },
      "cs": {
        "name": "Fotbal",
        "period_label": "Poločas",
        "break_label": "Poločasová přestávka",
        "hint": "",
        "score_label": "Góly",
        "sets_label": "Vyhrané sety"
      }
    },
    "score_mode": "total",
    "score_steps": [
      1
    ],
    "sets_enabled": false,
    "roles": {},
    "show_details": true,
    "show_officials": true
  },
  "pairing_confirmed": false,
  "display": {
    "score": true,
    "score_mode": "total",
    "sets": false,
    "counters": [],
    "details": true,
    "officials": true
  },
  "source": {
    "available": true,
    "instance_id": "68dacc2e-fd14-5c47-a2fa-f94de70e0893",
    "revision": 6,
    "event_id": "football-demo",
    "selection_token": "16780a85-2451-52de-a922-1b86e65f745f"
  }
}
```

</details>

## Upgrade und API-Umstellung

Version 0.2.2 liefert die hier beschriebene Live-Ausgabe am bestehenden Endpunkt;
es gibt keine parallele alte API. Die allgemeinen `pause`-/`resume`-Endpunkte
sind entfallen; Abschnittspausen werden ausschließlich über `intermission` erfasst. Angeschlossene Anwendungen müssen insbesondere
`display`, nullable Punkt-/Satzwerte, Abschnittshistorien, Rollen und den neuen
Quellenkontext berücksichtigen. Ein deaktivierter Score wird nicht als 0:0 geliefert.
Englische Abschnittstexte verwenden die Form „Round 2“.

`sudo livescore --upgrade` erhält Veranstaltungen, eingebettete Profilkopien,
Administratorvorlagen und Passwörter. Fehlende Profil- und Match-Felder alter Dateien
werden beim Laden sinnvoll ergänzt. Die JSON-Schema-Version bleibt 1; die Prag-Dateien
bleiben importierbar. Neue Standardprofile werden nur der Bibliothek hinzugefügt.
Archive mit Abschnittspunkten oder Satzständen benötigen diese oder eine neuere
LiveScore-Version. Ältere Programme mit strikter Feldvalidierung können sie ablehnen.

## Bedien-API

Bei aktiviertem Auth sind diese Endpunkte und der WebSocket geschützt.
`matches` und `tournament` enthalten rohe Verwaltungsdaten; für externe Grafiken
die aufbereitete öffentliche Live-Antwort einschließlich `display` verwenden.
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
| `POST /api/v1/live/score` | konfigurierter positiver oder negativer Punkteschritt für die aktuelle Seite |
| `POST /api/v1/live/sets` | manuell +1 oder −1 gewonnener Satz für die aktuelle Seite |
| `POST /api/v1/live/counter` | +1 oder −1 für einen Teilnehmer-Counter im aktuellen Abschnitt |
| `POST /api/v1/live/period` | bestätigter Wechsel zum nächsten Abschnitt, nur live/paused |
| `POST /api/v1/live/intermission` | Pause zwischen Abschnitten setzen/zurücknehmen (`intermission`: true/false), nur live/paused |
| `POST /api/v1/live/switch-sides` | nur L/R tauschen (ready/live/paused) |
| `POST /api/v1/live/undo` | letzte geeignete Punkte- oder Satzaktion zurücknehmen |
| `POST /api/v1/live/finish` | Ergebnis bestätigen (live/paused → finished) |
| `POST /api/v1/live/reopen` | ausgewähltes beendetes Spiel wieder öffnen (finished → live) |
| `POST /api/v1/live/reset` | ausgewähltes Spiel zurücksetzen (ready/live/paused/finished → scheduled), Operator und Admin |
| `WS /api/v1/ws` | initialer UI-Snapshot, weitere Snapshots, Heartbeat alle 5 Sekunden bei Leerlauf |

Mutationen geben den aktuellen UI-Snapshot zurück. Spielaktionen benötigen `request_id`, `event_id`, `selection_token` und `match_id`.
Für Steueraktionen gilt `expected_revision`; Score, Satzstand und Counter verwenden stattdessen
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
abweichen; Scores, Abschnittspunkte, Satzstand und Counter starten bei null. Andere Spiele bleiben unverändert.
`can_undo` und Undo berücksichtigen nur den aktuellen Spielversuch.

`match_reset` ist eine Undo-Grenze für den aktuellen Spielversuch. Archivierte
Ereignisse bleiben erhalten. Zur Weiterbearbeitung eines Endstands ohne Löschen der
Wettkampfdaten dient `reopen`.

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

Punkte-, Satz- und Counter-Buchungen mit derselben gültigen `control_revision` können
parallel addiert werden. Steueraktionen wie Seitenwechsel, Abschnittspause, Undo oder
Abschnittswechsel erhöhen diese Kontrollrevision und machen ältere Buchungen
ungültig. Die Event-Revision erhöht sich dagegen bei jeder Änderung.

`POST /api/v1/live/sets` verwendet dieselben Felder wie der Score-Request, mit
`delta: 1` oder `-1`. Die Satzerfassung muss im Profil aktiviert sein.
Score-Requests erlauben nur die konfigurierten `score_steps` mit positivem oder
negativem Vorzeichen; `0` und deaktivierte Punkteerfassung ergeben 422.

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
Veranstaltungsdatei ; die Live-API liefert den entsprechenden Kontext unter `source`.

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
Text-, Anzeige- und Schwellenpflege auch während des Wettkampfs; verwendete Strukturänderungen
werden mit `409` abgewiesen. [Änderungsregeln](OPERATOR.md#sportprofile-verwalten-admin).
