# Arbeitsregeln für Coding-Agenten

## Projekt und Navigation

LiveScore ist eine lokale Webanwendung zur einfachen Erfassung von Live-Spielständen bei Turnieren.

Das Projekt ist bewusst kein vollständiges Turniermanagement. Es verwaltet die für die Liveproduktion benötigten Veranstaltungsdaten, Teilnehmer, Spielplaninformationen und den aktuellen Spielzustand. Eine HTTP-API stellt den Live-Zustand für GFX- und andere Produktionssysteme bereit.

Diese Datei beschreibt, wie in diesem Repository gearbeitet wird. Die fachliche Zielstellung und der gewünschte MVP stehen in `README.md`. Vor Änderungen zuerst den vorhandenen Code, `README.md`, vorhandene Tests und gegebenenfalls weitere projektspezifische Dokumentation lesen.

Solange keine speziellere Dokumentation vorhanden ist, ist `README.md` die maßgebliche fachliche Referenz.

## Zentrale Projektregeln

Die folgenden Festlegungen sind Teil des Produktmodells.

### Kein Datenbanksystem

- LiveScore verwendet für den MVP keine SQL-, NoSQL- oder eingebettete Datenbank.
- Persistenter Veranstaltungs- und Live-Zustand wird in einer JSON-Datei gespeichert.
- Keine Datenbank nur aus Bequemlichkeit oder für hypothetische spätere Skalierung einführen.
- Schreibvorgänge müssen robust sein. Nach einem Prozessabbruch darf möglichst keine halb geschriebene JSON-Datei zurückbleiben.
- Bei Änderungen am Persistenzformat Abwärtskompatibilität oder eine klar definierte Migration berücksichtigen.

### Zwei Parteien, keine Home/Away-Annahme

Das Kernmodell besteht aus zwei gegeneinander antretenden Teilnehmern.

Ein Teilnehmer kann eine Mannschaft, Einzelperson oder ein anderes eindeutig bezeichnetes Wettkampfobjekt sein.

Intern keine Fußballannahmen wie `home_team` und `away_team` als allgemeines Domänenmodell einführen.

Im Live-Betrieb wird die tatsächliche räumliche Zuordnung mit `side_l` und `side_r` beschrieben.

### Bedeutung von L und R

`L` und `R` sind Positionsangaben:

- `L` = links im Programmbild beziehungsweise Overlay
- `R` = rechts im Programmbild beziehungsweise Overlay

Sie sind keine dauerhafte Identität eines Teilnehmers.

Der Score gehört immer zum Teilnehmer.

Ein Seitenwechsel vertauscht die Zuordnung der Teilnehmer zu `L` und `R`, niemals deren Score.

Diese Invariante muss durch Tests abgesichert sein.

### Play Area ist neutral

Der interne Begriff für die Wettkampffläche ist `play_area`.

Die sichtbare Bezeichnung ist konfigurierbar, zum Beispiel:

- Field 1
- Table 1
- Court 1
- Mat 1
- Ring A
- Bahn 2

Keine Sportart durch hart codierte Begriffe wie `field` oder `table` erzwingen.

### Score ist neutral

Der Kern verwaltet einen numerischen Score pro Teilnehmer.

Für den MVP genügen:

- `+1`
- `-1`
- Undo

Die Oberfläche darf je nach Konfiguration Begriffe wie Tor, Punkt oder Score anzeigen.

Sportartspezifische Regeln wie Sätze, Karten, Strafen, Torschützen, Tabellenberechnung oder automatische Turnierlogik nur auf ausdrücklichen Auftrag einführen.

### Externe Turniersysteme sind keine Laufzeitabhängigkeit

Spielpläne können später aus Tournify, CSV, JSON oder anderen Quellen übernommen werden.

Ein Import ist ein Adapter zur lokalen Konfiguration.

Die Live-Erfassung und `GET /api/v1/live` müssen ohne Internet und ohne Erreichbarkeit eines externen Dienstes funktionieren.

Keine zentrale Geschäftslogik an ein bestimmtes externes Turniersystem koppeln.

## Bedienablauf

Der Live-Betrieb soll dem Bediener einen klaren linearen Ablauf geben:

```text
nächstes Spiel
    ↓
Paarung bestätigen oder korrigieren
    ↓
L / R zuordnen
    ↓
Spiel starten
    ↓
Score erfassen
    ↓
Pause / Fortsetzen / Seitenwechsel
    ↓
Spiel beenden und Ergebnis bestätigen
    ↓
nächstes Spiel
```

Die GUI ist für den Einsatz am Wettkampftag gedacht.

Deshalb:

- mobile-first entwickeln
- große, eindeutig beschriftete Bedienelemente verwenden
- häufige Aktionen mit möglichst wenigen Klicks erreichbar machen
- kein unnötiges Menü während eines laufenden Spiels
- Score-Klicks nicht mit Bestätigungsdialogen bremsen
- `UNDO` deutlich sichtbar halten
- kritische Aktionen wie `Spiel Ende` gegen versehentliche Bedienung schützen
- den aktuellen Zustand `LIVE` beziehungsweise `PAUSE` deutlich anzeigen

Komplexität darf nicht vom Backend in die Bedienoberfläche verschoben werden.

## Zustandsmodell

Für den MVP die Zustände klein und eindeutig halten:

```text
scheduled
ready
live
paused
finished
```

Erlaubte Übergänge sollen explizit implementiert und getestet werden.

Insbesondere:

- ein nicht vorbereitetes Spiel nicht versehentlich starten
- ein beendetes Spiel nicht stillschweigend weiter verändern
- Pause und Fortsetzen müssen einen eindeutigen Zustand erzeugen
- Seitenwechsel darf keine Score-Zuordnung beschädigen
- nach Neustart muss der persistierte Zustand nachvollziehbar wiederhergestellt werden

Keine komplexe State-Machine-Bibliothek einführen, solange einfache explizite Logik ausreicht.

## API-Regeln

Die externe API ist Teil des Produktvertrags.

Der wichtigste Endpunkt ist:

```http
GET /api/v1/live
```

Er liefert den für die Darstellung bereits aufbereiteten aktuellen Zustand mit einer linken und rechten Seite.

Eine GFX-Engine soll keine Turnier-, Seitenwechsel- oder Sportlogik nachbauen müssen.

Bei Änderungen an diesem Endpunkt:

- bestehende Feldnamen nicht beiläufig umbenennen
- Änderungen bewusst versionieren
- JSON-Beispiele und Tests aktualisieren
- keine internen Implementierungsdetails unnötig nach außen geben

Bedienaktionen dürfen über weitere API-Endpunkte umgesetzt werden. Mutierende Endpunkte müssen Eingaben validieren und dürfen den gespeicherten Zustand nicht inkonsistent hinterlassen.

Für den MVP ist Polling durch die GFX-Engine ausreichend. WebSockets, SSE oder Message Broker nur einführen, wenn ein konkreter Bedarf nachgewiesen ist.

## Ereignisse und Undo

Bedienaktionen sollen nachvollziehbar sein.

Score-Änderungen und relevante Zustandswechsel dürfen als Ereignisse innerhalb der JSON-Struktur protokolliert werden.

Mindestens für Score-Aktionen muss Undo zuverlässig funktionieren.

Beim Entwurf beachten:

- Undo soll die letzte geeignete Bedienaktion zurücknehmen.
- Ein Seitenwechsel darf Scores nicht an die falsche Partei binden.
- Ein Reload der Bedienoberfläche darf keine Aktion erneut auslösen.
- Doppelklicks oder wiederholte HTTP-Anfragen dürfen nicht unbemerkt zu schwer nachvollziehbaren Zuständen führen.

Keine Event-Sourcing-Architektur bauen, wenn eine kleine Ereignisliste den konkreten Bedarf erfüllt.

## Arbeitsweise

- Die kleinste robuste Lösung bevorzugen, die den konkreten Bedarf erfüllt.
- Neue Komponenten, Dienste, Abstraktionsschichten oder Abhängigkeiten nur einführen, wenn ein konkreter Nutzen sie rechtfertigt.
- Betriebs-, Wartungs- und Fehlersuchaufwand gehören zu den technischen Kosten.
- Das Projekt muss für ein kleines beziehungsweise ein Einmann-Team nachvollziehbar und wartbar bleiben.
- Nicht vorsorglich für hypothetische Anforderungen oder Skalierung bauen.
- Vor einer Änderung den betroffenen Code, die zugehörige Dokumentation und vorhandene Tests lesen.
- Den bestehenden Stand prüfen, statt ihn aus Annahmen zu ersetzen.
- Eine dokumentierte Festlegung nicht umgehen. Wirkt sie falsch, das melden.
- Den Scope klein und zusammenhängend halten.
- Keine spekulativen Features und keine unbeauftragten Refactors.
- Einfachen, funktionierenden Code nicht ohne Bedarf abstrahieren.
- Klarer Code vor cleverem Code.
- Die Begriffe verwenden, die in `README.md` und der vorhandenen Dokumentation stehen.

## Technische Leitplanken

Solange das Repository nichts anderes festlegt, ist für den MVP eine kleine lokale Webanwendung vorgesehen:

- Python
- FastAPI
- Uvicorn
- HTML/CSS/JavaScript
- JSON-Datei als Persistenz
- HTTP/REST
- Betrieb im lokalen Netzwerk
- Linux und Windows als sinnvolle Zielplattformen

Ein großes Frontend-Framework, Redis, PostgreSQL, Docker, Kubernetes oder ein Message Broker sind keine Voraussetzung und sollen nicht ohne konkreten Auftrag eingeführt werden.

Eine zusätzliche Abhängigkeit muss einen nachvollziehbaren Vorteil gegenüber Standardbibliothek oder bereits verwendeten Komponenten bieten.

## Datenmodell und Persistenz

Das gespeicherte Modell soll lesbar und auch außerhalb der Anwendung nachvollziehbar bleiben.

Bevorzugen:

- stabile IDs
- klare Feldnamen
- ISO-Datums- und Zeitformate
- explizite Statuswerte
- lesbare JSON-Struktur

Vermeiden:

- implizite Bedeutung durch Arraypositionen
- versteckte Kopplung zwischen UI-Reihenfolge und Fachlogik
- Score ausschließlich an `L` oder `R` zu speichern
- nicht dokumentierte Magic Values
- unnötig verschachtelte Strukturen

Beim Speichern:

1. neuen Zustand vollständig validieren,
2. in eine temporäre Datei schreiben,
3. Datei vollständig schließen beziehungsweise flushen,
4. die produktive JSON-Datei atomar ersetzen, soweit die Plattform dies unterstützt.

## Auftragsgrenze

- Den beauftragten Scope vollständig umsetzen. Bleibt etwas offen, das sagen.
- Nur den beauftragten Fall umsetzen. Ein Dokument erklärt Hintergrund, es ist kein Auftrag zur Umsetzung aller erwähnten Möglichkeiten.
- Andere Repositories nur auf ausdrücklichen Auftrag ändern.
- Laufende oder externe Umgebungen nur auf ausdrücklichen Auftrag ändern.
- Bestehende Benutzeränderungen, lokale Veranstaltungsdaten und Secrets nicht überschreiben.
- Branchwechsel, Commit, Push, Merge, Release und Deployment nur ausführen, wenn der Auftrag sie umfasst.
- Größere Verbesserungen als Folgeauftrag vorschlagen statt sie nebenbei einzubauen.

## Dokumentationsregel

- README.md und weitere Projektdokumentation werden auf Deutsch geführt.
- Etablierte technische Fachbegriffe und API-Feldnamen bleiben unverändert.
- Verhaltensänderungen in der zuständigen Dokumentation nachführen.
- Neue Produktregeln nicht ausschließlich im Code verstecken.
- Beispiele müssen zum tatsächlich implementierten Verhalten passen.
- Noch nicht implementierte Funktionen klar als geplant oder optional kennzeichnen.

Wenn später eine umfangreichere Dokumentation entsteht, soll jedes Thema einen klaren primären Ort erhalten, beispielsweise:

```text
README.md              Produktziel und Einstieg
docs/API.md            HTTP-API und Datenformate
docs/DATA_MODEL.md     JSON-Modell und Invarianten
docs/DEVELOPMENT.md    Entwicklungsbetrieb und Tests
docs/OPERATOR.md       Bedienung am Wettkampftag
```

Keine Dokumentationsstruktur nur vorsorglich anlegen. Dateien erst erstellen, wenn der Inhalt tatsächlich benötigt wird.

## Verifikation

Änderungen mit den Prüfungen absichern, die zum betroffenen Bereich passen.

Für den MVP sind insbesondere Tests für folgende Fälle wichtig:

- JSON laden und speichern
- Wiederherstellung nach Neustart
- Paarung vor Spielbeginn ändern
- L/R-Zuordnung tauschen
- Score links erhöhen
- Score rechts erhöhen
- Score verringern
- Undo
- Pause und Fortsetzen
- Seitenwechsel bei vorhandenem Score
- Spiel beenden
- Wechsel zum nächsten Spiel
- `GET /api/v1/live`
- API-Ausgabe nach einem Seitenwechsel
- ungültige Zustandsübergänge

Eine zentrale Regression muss ausdrücklich getestet werden:

```text
Teilnehmer A hat 2 Punkte.
Teilnehmer B hat 1 Punkt.
Seitenwechsel.
```

Danach muss gelten:

```text
Teilnehmer A hat weiterhin 2 Punkte.
Teilnehmer B hat weiterhin 1 Punkt.
```

Nur ihre Darstellung auf `L` und `R` hat sich geändert.

## Abschluss eines Auftrags

Vor Abschluss:

- passende Tests ausführen
- relevante manuelle Prüfung durchführen, wenn die Änderung UI oder Bedienablauf betrifft
- JSON-Datei auf gültiges Format prüfen
- API-Beispiele gegen das tatsächliche Verhalten prüfen
- Diff prüfen
- Repository-Status prüfen

Im Abschlussbericht wahrheitsgemäß nennen:

- was geändert wurde
- welche Prüfungen tatsächlich ausgeführt wurden
- welche relevanten Schritte nicht ausgeführt wurden und warum
- bekannte offene Punkte innerhalb des beauftragten Scopes
