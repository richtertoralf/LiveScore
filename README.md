# LiveScore

Lokale Webanwendung zur einfachen Erfassung und Bereitstellung von Live-Spielständen bei Turnieren.

LiveScore ist für Veranstaltungen gedacht, bei denen sich in einem Spiel oder Wettkampf **zwei Parteien direkt gegenüberstehen**. Das können Mannschaften oder Einzelpersonen sein. Beispiele sind Fußball, Blindenfußball, Showdown, Boxen, Tennis, Tischtennis, Hockey oder andere Sportarten mit zwei Seiten.

Die Anwendung ersetzt **keine Turnierverwaltung**. Spielplan, Teilnehmer und Veranstaltungsdaten werden vor der Veranstaltung übernommen oder manuell eingetragen. Während der Produktion konzentriert sich LiveScore auf genau das, was am Spielfeld benötigt wird:

**Paarung bestätigen → Links/Rechts festlegen → Spiel starten → Tore/Punkte erfassen → Pause/Seitenwechsel → Spiel beenden**

Die aktuellen Daten werden über eine einfache HTTP-API bereitgestellt und können beispielsweise von einer GFX-Engine für Livestream-Grafiken verwendet werden.

---

## Ziel

LiveScore soll am Wettkampftag auch von Helferinnen und Helfern bedient werden können, die das System vorher kaum oder gar nicht kennen.

Die wichtigsten Ziele sind:

- **extrem einfache Bedienung**
- klare, geführte Schritte statt komplexer Turnierverwaltung
- mobile Bedienung auf Smartphone oder Tablet
- Betrieb im lokalen Veranstaltungsnetz ohne Internet
- sportartenneutrales Modell für zwei gegeneinander antretende Parteien
- eindeutige Zuordnung zu **linker (`L`) und rechter (`R`) Seite**
- manuelle Live-Erfassung von Toren oder Punkten
- einfache Schnittstelle für GFX-, Overlay- und Produktionssysteme
- keine Datenbank
- nachvollziehbare, portable Speicherung in einer JSON-Datei

LiveScore soll bewusst klein bleiben. Es soll eine robuste Hilfe für die Liveproduktion sein und kein zweites Tournify, Sportdata oder vollständiges Wettkampfmanagement werden.

---

## Grundprinzip

```text
Spielplan / Konfiguration
          │
          ▼
    Paarung prüfen
          │
          ▼
  Links / Rechts festlegen
          │
          ▼
      Spiel starten
          │
          ▼
  Tore / Punkte erfassen
          │
    ┌─────┴─────┐
    ▼           ▼
  Pause     Seitenwechsel
    │           │
    └─────┬─────┘
          ▼
      Spielende
          │
          ▼
      nächstes Spiel
```

Für eine Livestream-Produktion ergibt sich beispielsweise:

```text
LiveScore ──HTTP API──> GFX-Engine ──> Overlay / Programmbild
```

Die GFX-Engine muss weder den Turniermodus noch die Bedienlogik kennen. Sie fragt nur den aktuellen Live-Zustand ab.

---

## Zwei Bereiche der Weboberfläche

### 1. Konfiguration

Vor der Veranstaltung werden die benötigten Daten eingetragen oder importiert.

#### Veranstaltung

- Name
- Startdatum
- Enddatum
- optional Veranstaltungsort
- optional Logo

Beispiel:

```text
13th Cup of Central Europe Cities 2026
03.10.2026 – 04.10.2026
Prag
```

#### Spielflächen

Die Anwendung verwendet intern den neutralen Begriff **Play Area**.

Die sichtbare Bezeichnung ist frei wählbar:

- `Field 1`
- `Table 1`
- `Court 1`
- `Mat 1`
- `Ring A`
- `Bahn 2`

Dadurch muss die Anwendung nicht wissen, welche Sportart gespielt wird.

#### Teilnehmer

Ein Teilnehmer kann eine Mannschaft oder eine Einzelperson sein.

Pro Teilnehmer werden mindestens gespeichert:

- ID
- Name
- optional Kurzname
- optional Logo

#### Spielplan

Für jedes geplante Spiel werden mindestens gespeichert:

- Spiel-ID
- Datum
- Uhrzeit
- Play Area
- Runde oder Bezeichnung
- Teilnehmer bzw. noch offene Platzhalter

Beispiel:

```text
03.10.2026
09:30
Field 1
Gruppe A
BSC Praha – FC Ingolstadt 04
```

Bei Final- oder Platzierungsspielen können die Teilnehmer zunächst noch unbekannt sein:

```text
08:30
Field 1
Semi final #1
1st Group A – 4th Group A
```

Die tatsächliche Paarung wird vor Spielbeginn vom Bediener bestätigt oder korrigiert.

---

### 2. Live-Betrieb

Im Live-Betrieb soll der Bediener möglichst keine Konfigurationsoberfläche mehr sehen.

Der Ablauf besteht aus wenigen klaren Schritten.

#### Schritt 1: nächstes Spiel

```text
NÄCHSTES SPIEL

09:30 · Field 1

BSC Praha
gegen
FC Ingolstadt 04

[ PAARUNG BESTÄTIGEN ]
[ PAARUNG ÄNDERN ]
```

#### Schritt 2: Links und Rechts festlegen

`L` und `R` beschreiben die tatsächliche Position im Spielfeld beziehungsweise im späteren Overlay.

```text
LINKS                         RECHTS

BSC Praha                     FC Ingolstadt 04

            [ ↔ TAUSCHEN ]

          [ SPIEL STARTEN ]
```

Für eine Produktion gilt:

- `L` = links im Programmbild / Overlay
- `R` = rechts im Programmbild / Overlay

Es gibt bewusst keine feste Annahme von `Home` und `Away`.

#### Schritt 3: Live-Spiel

```text
                LIVE

BSC PRAHA                    INGOLSTADT
   LINKS                        RECHTS

       2             :             1

     [ +1 ]                       [ +1 ]
     [ -1 ]                       [ -1 ]

               [ UNDO ]

       [ PAUSE ]   [ SEITENWECHSEL ]

              [ SPIEL ENDE ]
```

Die Buttons müssen groß genug für Smartphone und Tablet sein.

Für schnelle Aktionen soll möglichst kein zusätzlicher Dialog notwendig sein. Kritische Aktionen wie **Spiel beenden** dürfen eine Bestätigung verlangen.

#### Schritt 4: Pause

`Pause` setzt den Zustand des Spiels auf `paused`.

Der Button wechselt anschließend zu:

```text
[ FORTSETZEN ]
```

#### Schritt 5: Seitenwechsel

Ein Seitenwechsel verändert **nur die Zuordnung der Teilnehmer zu L und R**.

Beispiel vor dem Seitenwechsel:

```text
L: BSC Praha        2
R: FC Ingolstadt    1
```

Nach dem Seitenwechsel:

```text
L: FC Ingolstadt    1
R: BSC Praha        2
```

Der Spielstand gehört immer zum Teilnehmer und darf beim Seitenwechsel nicht vertauscht werden.

#### Schritt 6: Spielende

```text
SPIEL BEENDEN?

BSC Praha          2 : 1          FC Ingolstadt 04

[ ZURÜCK ]
[ ERGEBNIS BESTÄTIGEN ]
```

Danach schlägt LiveScore das nächste Spiel vor.

---

## Sportartenneutralität

LiveScore modelliert nicht Fußball, Showdown oder Tennis, sondern einen Wettkampf zwischen zwei Parteien.

Der gemeinsame Kern ist:

```text
Participant 1
      vs.
Participant 2
```

Im Live-Betrieb werden diese Teilnehmer den beiden Seiten zugeordnet:

```text
side_l
side_r
```

Der Zähler ist neutral. Je nach Veranstaltung kann die Oberfläche ihn beispielsweise als **Tore**, **Punkte** oder einfach als **Score** bezeichnen.

Für den ersten MVP gilt:

- `+1`
- `-1`
- Undo
- keine automatische sportartspezifische Regelberechnung

Sätze, Karten, Strafen, Torschützen, Tabellenberechnung oder andere Spezialregeln gehören nur dann in das Projekt, wenn dafür ein konkreter Produktionsbedarf besteht.

---

## Datenspeicherung

LiveScore verwendet **keine Datenbank**.

Alle Veranstaltungs-, Spielplan- und Live-Daten werden in einer JSON-Datei gespeichert, beispielsweise:

```text
data/tournament.json
```

Beispielstruktur:

```json
{
  "event": {
    "name": "13th Cup of Central Europe Cities 2026",
    "date_from": "2026-10-03",
    "date_to": "2026-10-04",
    "location": "Prague"
  },
  "play_areas": [
    {
      "id": "field-1",
      "label": "Field 1"
    }
  ],
  "participants": [
    {
      "id": "bsc-praha",
      "name": "BSC Praha",
      "short_name": "BSC"
    },
    {
      "id": "fc-ingolstadt-04",
      "name": "FC Ingolstadt 04",
      "short_name": "FCI"
    }
  ],
  "matches": [
    {
      "id": "match-001",
      "date": "2026-10-03",
      "time": "09:30",
      "play_area_id": "field-1",
      "round": "Gruppe A",
      "participant_1": "bsc-praha",
      "participant_2": "fc-ingolstadt-04",
      "status": "scheduled"
    }
  ],
  "live": {
    "match_id": null,
    "status": "idle",
    "side_l": null,
    "side_r": null
  },
  "events": []
}
```

Schreibvorgänge sollen robust erfolgen. Eine unvollständig geschriebene Datei darf die Veranstaltung nicht unbrauchbar machen. Die Implementierung soll deshalb zuerst in eine temporäre Datei schreiben und diese anschließend atomar ersetzen.

---

## Live-Zustand

Ein laufendes Spiel besitzt mindestens folgende Informationen:

```json
{
  "match_id": "match-001",
  "status": "live",
  "play_area_id": "field-1",
  "side_l": {
    "participant_id": "bsc-praha",
    "score": 2
  },
  "side_r": {
    "participant_id": "fc-ingolstadt-04",
    "score": 1
  }
}
```

Wichtig:

Der Score gehört fachlich zum Teilnehmer. `side_l` und `side_r` beschreiben nur seine aktuelle Position.

Beim Seitenwechsel werden die Positionen vertauscht, nicht die Ergebnisse.

---

## Zustände eines Spiels

Für den MVP reichen wenige eindeutige Zustände:

```text
scheduled
   │
   ▼
 ready
   │
   ▼
 live ◄────► paused
   │
   ▼
finished
```

Bedeutung:

- `scheduled` – im Spielplan vorhanden
- `ready` – Paarung wurde bestätigt und L/R festgelegt
- `live` – Spiel läuft
- `paused` – Spiel ist unterbrochen
- `finished` – Endstand wurde bestätigt

---

## Ereignisse und Undo

Bedienaktionen sollen nachvollziehbar bleiben.

Ein Treffer oder Punkt wird als Ereignis behandelt:

```json
{
  "type": "score",
  "participant_id": "bsc-praha",
  "delta": 1,
  "timestamp": "2026-10-03T09:38:14+02:00"
}
```

Weitere mögliche Ereignisse:

```text
match_started
score
pause
resume
side_switch
match_finished
```

`UNDO` nimmt die letzte dafür geeignete Bedienaktion zurück.

Die Ereignisse werden innerhalb derselben `tournament.json` gespeichert. Eine zusätzliche Datenbank ist dafür nicht nötig.

---

## HTTP-API

Die API ist die Schnittstelle zu GFX-Engines und anderen Produktionssystemen.

### Aktuelles Live-Spiel

```http
GET /api/v1/live
```

Beispiel:

```json
{
  "status": "live",
  "match_id": "match-001",
  "play_area": {
    "id": "field-1",
    "label": "Field 1"
  },
  "left": {
    "id": "bsc-praha",
    "name": "BSC Praha",
    "short_name": "BSC",
    "score": 2
  },
  "right": {
    "id": "fc-ingolstadt-04",
    "name": "FC Ingolstadt 04",
    "short_name": "FCI",
    "score": 1
  }
}
```

Die Ausgabe ist absichtlich bereits nach **links** und **rechts** aufbereitet. Eine GFX-Engine muss dadurch keine Seitenwechsel- oder Turnierlogik implementieren.

Für den MVP kann die GFX-Engine diesen Endpunkt beispielsweise einmal pro Sekunde abfragen.

### Vorgesehene Bedien-Endpunkte

```text
GET  /api/v1/tournament
GET  /api/v1/matches
GET  /api/v1/live

POST /api/v1/live/select
POST /api/v1/live/start
POST /api/v1/live/score
POST /api/v1/live/pause
POST /api/v1/live/resume
POST /api/v1/live/switch-sides
POST /api/v1/live/undo
POST /api/v1/live/finish
```

Beispiel für einen Score-Klick:

```json
{
  "side": "L",
  "delta": 1
}
```

Der wichtigste externe Vertrag ist `GET /api/v1/live`.

---

## Import von Spielplänen

LiveScore soll nicht von einem bestimmten Turniersystem abhängig sein.

Mögliche Quellen sind:

- manuelle Eingabe
- CSV
- JSON
- später gegebenenfalls ein Adapter für eine externe Turniersoftware

Ein Import ist nur eine Hilfe zur Erstellung der lokalen Konfiguration.

Die Liveproduktion muss auch dann funktionieren, wenn kein Internet vorhanden ist oder die externe Plattform verspätet aktualisiert wird.

---

## Was LiveScore ausdrücklich nicht sein soll

Der MVP soll **nicht**:

- Tabellen automatisch berechnen
- Turnierregeln vollständig abbilden
- Gewinner automatisch in Halbfinals oder Finals einsetzen
- einen Cloud-Dienst voraussetzen
- eine Benutzerverwaltung benötigen
- eine Datenbank benötigen
- sportartspezifische Speziallogik erzwingen
- GFX selbst rendern
- von Tournify oder einem anderen Anbieter abhängig sein

Offene Paarungen werden vor dem jeweiligen Spiel durch den Bediener bestätigt oder korrigiert.

---

## Technische Zielrichtung

Für die erste Implementierung bietet sich ein bewusst kleiner Stack an:

- Python
- FastAPI
- Uvicorn
- HTML/CSS/JavaScript
- responsive, mobile-first Weboberfläche
- JSON-Datei als persistenter Zustand
- REST-API
- lokaler Betrieb unter Linux oder Windows

Ein großes Frontend-Framework ist für den MVP nicht erforderlich. Die kleinste robuste Lösung ist zu bevorzugen.

---

## MVP

Version 0.1 soll mindestens ermöglichen:

1. Veranstaltung anlegen
2. Play Areas anlegen
3. Teilnehmer anlegen
4. Spielplan anlegen oder einlesen
5. nächstes Spiel auswählen
6. Paarung bestätigen oder korrigieren
7. Teilnehmer L und R zuordnen
8. Spiel starten
9. Score auf L oder R mit `+1` und `-1` ändern
10. letzte Aktion rückgängig machen
11. Spiel pausieren und fortsetzen
12. Seiten wechseln
13. Spiel beenden und Ergebnis bestätigen
14. aktuellen Zustand über `GET /api/v1/live` ausgeben
15. Zustand nach Neustart aus `tournament.json` wiederherstellen

---

## Bedienphilosophie

Die Live-Oberfläche wird für den Wettkampftag gebaut, nicht für Administratoren.

Deshalb gelten folgende Grundsätze:

- wenige große Schaltflächen
- eindeutige Beschriftungen
- klare visuelle Anzeige von `LIVE` und `PAUSE`
- keine verschachtelten Menüs während eines Spiels
- kein unnötiger Dialog nach jedem Score
- `UNDO` jederzeit gut erreichbar
- kritische Aktionen klar von häufigen Aktionen trennen
- Smartphone und Tablet als primäre Bediengeräte behandeln

Ein neuer Bediener soll nach einer sehr kurzen Einweisung verstehen:

> Paarung prüfen, links und rechts festlegen, Start drücken und während des Spiels nur noch Punkte sowie den Spielzustand bedienen.

---

## Projektstatus

Das Projekt befindet sich in der Konzept- und MVP-Phase.

Installations- und Betriebsanweisungen werden ergänzt, sobald eine erste lauffähige Version vorhanden ist. Bis dahin beschreibt dieses README den beabsichtigten Produktumfang und die wichtigsten fachlichen Regeln.
