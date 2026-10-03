# Bedienung: „Pause“ entfernen, Halbzeit nach oben, Wiederöffnen ohne PAUSE-Zustand

> **Art:** Vereinfachung der Bedienoberfläche · **Umfang:** nur Frontend (`static/`), Tests und Dokumentation · **Backend, Datenmodell und API unverändert**
>
> Geprüfter Stand: LiveScore 0.1.2 (Produktivsystem, Oktober 2026).

## Anlass

Beim Blindenfußballturnier in Prag hat der tschechische Bediener zur Halbzeit manchmal **„Pause“** gedrückt statt **„Halbzeitpause“**.

Folgen im Ist-Stand:

- Der Status wird `paused`, aber die Halbzeit ist nicht gekennzeichnet.
- `GET /api/v1/live` liefert weiter „1st half“ statt „Half-time“. Die Grafik zeigt keine Halbzeit.
- Halbzeitbezogene Teamfouls und die Kennzeichnung der Halbzeit hängen davon ab, dass der richtige Button gedrückt wird.

Ursachen:

1. „Pause“ und „Halbzeitpause“ bzw. „Half-time“ sind leicht zu verwechseln. In der englischen Oberfläche steht „Pause“ unübersetzt.
2. „Pause“ steht oben im Raster, die Halbzeit-Buttons stehen ganz unten unter „Spiel Ende“.
3. „Pause“ liefert keinen Wert, den Grafik oder Spielstand benötigen. Die gfx-engine behandelt `paused` wie `live`.

## Begründung nach den Produkt- und Bedienregeln

- **Keine allgemeine Pause (§7):** LiveScore führt keine Spielzeit und erfasst keine Unterbrechungen. Die Pause-Funktion wird aus der Bedienoberfläche entfernt. Der interne Status `paused` darf aus Kompatibilitätsgründen bestehen bleiben.
- **Halbzeit ist fachlich relevant (§6):** Teamfouls werden halbzeitbezogen geführt, und die Grafik zeigt die Halbzeit. Der Button für die Halbzeit muss deshalb leicht erreichbar sein.
- **Wiederöffnen (§10):** Ein versehentlich beendetes Spiel muss wieder geöffnet werden können. Daraus entsteht kein neuer sichtbarer Zustand.
- **Vereinfachen statt erweitern (§12):** Widersprechende Funktionen werden entfernt oder verborgen. Es kommt keine neue Logik und kein neuer Dialog hinzu.

## Soll-Bedienung

Score ±1, Teamfouls ±, UNDO, Officials-Anzeige und Spielauswahl bleiben unverändert.

**BEREIT**

```text
[ Seiten tauschen ]
[ 1. Halbzeit starten ]                       ← bisher „Spiel starten“
[ Paarung ändern / Vorbereitung zurücknehmen ]
```

**1. Halbzeit** (Statusschild LIVE)

```text
[ UNDO · letzter Score ]
[ Halbzeitpause ] [ Seitenwechsel ]           ← Halbzeitpause auf dem bisherigen Platz von „Pause“
[ Spiel Ende ]
```

**Halbzeitpause** (Statusschild HALBZEITPAUSE)

```text
[ UNDO · letzter Score ]
[ 2. Halbzeit starten ]                       ← nur hier sichtbar; Bestätigungsdialog wie bisher
[ Zurück zu 1. Halbzeit ] [ Seitenwechsel ]
[ Spiel Ende ]
```

**2. Halbzeit** (Statusschild LIVE)

```text
[ UNDO · letzter Score ]
[ Seitenwechsel ]                             ← bei Bedarf L/R entsprechend der Spielfeldsituation tauschen
[ Spiel Ende ]
```

**BEENDET**

```text
Ergebnis bestätigt …
[ Spiel wieder öffnen ]                       ← Bestätigungsdialog wie bisher
```

## Wiederöffnen eines versehentlich beendeten Spiels

„Spiel wieder öffnen“ bleibt erhalten. Die Funktion ist wichtig, wenn der Bediener versehentlich auf „Spiel Ende“ geklickt hat.

**Ist:**

```text
Spiel wieder öffnen → Dialog → Status PAUSE → „Fortsetzen“ → LIVE
```

**Soll:**

```text
Spiel wieder öffnen → Dialog → Spiel läuft weiter wie vor dem Spielende
```

- Das Backend bleibt unverändert. `reopen` setzt intern weiterhin `finished` → `paused`.
- Die Bedienoberfläche stellt den internen Status `paused` **wie LIVE** dar:
  - Statusschild LIVE, bzw. HALBZEITPAUSE bei gesetzter Halbzeitpause,
  - dieselben Buttons wie im laufenden Spiel,
  - kein Button „Fortsetzen“.
- Alle Spielaktionen (Score, Teamfouls, UNDO, Seitenwechsel, Halbzeitpause, 2. Halbzeit starten, Spiel Ende) sind im internen Status `paused` bereits heute erlaubt. Ein „Fortsetzen“ ist dafür nicht nötig.
- Score, Seiten, Halbzeit und Teamfouls bleiben erhalten.
- Eine gesetzte Halbzeitpause wurde durch das Spielende beendet. Beim Wiederöffnen während der Halbzeit muss sie erneut gesetzt werden. Dieses Verhalten ist unverändert.
- Der Dialogtext ändert sich von „… in PAUSE fortgesetzt. Mit ‚Fortsetzen‘ ist es wieder LIVE.“ in „Das Spiel wird mit unverändertem Score, Seiten und Halbzeit fortgesetzt.“

Nach dem Wiederöffnen liefert `GET /api/v1/live` weiterhin `status: "paused"`. Die gfx-engine behandelt das wie `live`. An der Grafik ändert sich nichts.

## Entscheidungsspiele

Es gibt keine eigene Phase oder Funktion für das Strafstoßschießen.

Ein Spiel, das einen Sieger benötigt, bleibt geöffnet, bis der Sieger feststeht, und wird erst dann mit „Spiel Ende“ beendet.

Dieses Issue ändert daran nichts. Es dokumentiert die Regel nur im README.

## Änderungen

### A. Pause aus der Bedienung entfernen

- `static/live.js`: Kein Button „Pause“ bzw. „Fortsetzen“ mehr.
- `static/live.js`, `static/config.js:40`: Status `paused` wird wie `live` angezeigt („LIVE“).
- `static/index.html` und `static/i18n.js`: Dialogtext „Spiel wieder öffnen“ anpassen (siehe oben).
- `static/i18n.js`: Die Texte „Pause“, „Fortsetzen“ und „PAUSE“ werden in der Oberfläche nicht mehr verwendet.

### B. Halbzeit-Bedienung nach oben

- „Halbzeitpause“ bzw. „Zurück zu 1. Halbzeit“ steht im Raster neben „Seitenwechsel“, auf dem bisherigen Platz von „Pause“.
- „2. Halbzeit starten“ wird **nur während der Halbzeitpause** angezeigt. Der Bestätigungsdialog bleibt, weil sich der Wechsel zur 2. Halbzeit nicht zurücknehmen lässt.
- Alle Halbzeit-Buttons stehen über „Spiel Ende“.
- Bei Profilen ohne Halbzeiten gilt dasselbe mit den vorhandenen neutralen Texten.

### C. Statusschild in der Halbzeitpause

- Während einer gesetzten Halbzeitpause zeigt das Statusschild „HALBZEITPAUSE“ statt „LIVE“.
- Die Texte: EN „HALF-TIME“, CS „POLOČASOVÁ PŘESTÁVKA“. Bei Profilen ohne Halbzeiten der vorhandene neutrale Text.
- Das ist nur eine Anzeige. API und `period_info` bleiben unverändert.

### D. Beschriftung

- „Spiel starten“ wird zu „1. Halbzeit starten“. EN und CS entsprechend der vorhandenen Vorlage für „2. Halbzeit starten“.
- Die tschechischen Texte bestätigt eine muttersprachliche Person.

### E. Dokumentation

- **README:**
  - Bedienablauf, Bedienung Punkt 8 (Pause) und Punkt 10 (Wiederöffnen), Abschnitt „Halbzeitpause“, Rollentabelle.
  - Unter „Bewusste Grenzen“ ergänzen: keine allgemeine Pause; Entscheidungsspiele bleiben geöffnet, bis der Sieger feststeht.
  - Klarstellen: Der Status `paused` und `POST /api/v1/live/pause` bleiben nur aus Kompatibilitätsgründen bestehen.
- **AGENTS.md:**
  - Bedienablauf ohne „Pause / Fortsetzen“.
  - Die Vorgabe „LIVE beziehungsweise PAUSE deutlich anzeigen“ wird zu „LIVE beziehungsweise HALBZEITPAUSE deutlich anzeigen“.
  - Die verbindlichen Produkt- und Bedienregeln aufnehmen, insbesondere Entscheidungsregel und Arbeitsregel für Entwickler und KI-Agenten.

### F. Tests

- `tests/browser_smoke.py`:
  - Klicks auf „Pause“ und „Fortsetzen“ entfernen.
  - Wiederöffnen prüfen: Nach dem Bestätigen zeigt die Oberfläche LIVE mit unverändertem Stand. Score-Buttons funktionieren ohne weiteren Schritt.
  - Halbzeitablauf prüfen: Halbzeitpause → 2. Halbzeit starten → Spiel Ende.
  - „2. Halbzeit starten“ ist in der 1. Halbzeit ohne Halbzeitpause nicht sichtbar.
  - Die Halbzeit-Buttons stehen vor „Spiel Ende“.
- `tests/test_i18n.py`: alle verwendeten Texte in EN, DE und CS.
- Backend-Tests bleiben unverändert und müssen bestehen. Sie prüfen den internen Status `paused` weiterhin.

## Unverändert

- Backend, Datenmodell, gespeicherte JSON-Dateien
- `GET /api/v1/live` und die gfx-engine
- interner Status `paused`, Endpunkte `pause` und `resume`
- „Spiel wieder öffnen“ mit Bestätigungsdialog
- Seitenwechsel als einfache eigene Aktion, ohne Dialog und ohne Kopplung an die Halbzeit

## Nicht Bestandteil

- Spielzeit oder Uhr (siehe #2)
- Strafstoßschießen oder Verlängerung als eigene Phase
- Unterbrechungen oder Time-outs
- Entfernen des internen Status `paused`

## Akzeptanzkriterien

- [ ] In der Bedienoberfläche gibt es keine Buttons „Pause“ oder „Fortsetzen“ mehr.
- [ ] In der 1. Halbzeit steht „Halbzeitpause“ neben „Seitenwechsel“ über „Spiel Ende“.
- [ ] „2. Halbzeit starten“ erscheint nur während der Halbzeitpause und behält den Bestätigungsdialog.
- [ ] Während der Halbzeitpause zeigt das Statusschild „HALBZEITPAUSE“. Die API liefert „Half-time“.
- [ ] „Zurück zu 1. Halbzeit“ korrigiert eine versehentlich gesetzte Halbzeitpause.
- [ ] Nach „Spiel wieder öffnen“ zeigt die Oberfläche das Spiel wie vor dem Spielende als LIVE. Score, Teamfouls, Seitenwechsel, Halbzeit und Spiel Ende sind sofort bedienbar.
- [ ] Nirgends in der Oberfläche erscheint „PAUSE“.
- [ ] EN, DE und CS sind vollständig. Keine unübersetzten deutschen Wörter in EN.
- [ ] API-Ausgabe und gespeicherte Dateien sind unverändert. Die Backend-Tests bestehen.
- [ ] README und AGENTS.md beschreiben den neuen Ablauf und die Produktregeln.

## Bis zum Rollout

Bedienhinweis an das Team:

> Zur Halbzeit **„Half-time“** drücken; der Button steht unten unter „Finish match“. „Pause“ nicht verwenden. Ein Spiel, das einen Sieger braucht, erst nach dem Strafstoßschießen beenden.
