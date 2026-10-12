# Bedienung: sportartenneutrale Abschnittspausen und direktes Wiederöffnen

> GitHub: [Issue #5](https://github.com/richtertoralf/LiveScore/issues/5)
> Status: umgesetzt und unter Linux/Chromium geprüft.
> Umfang: Bedienoberfläche, Live-Projektion, Wiederöffnen, Übersetzungen, Tests und Dokumentation.

## Anlass und Produktentscheidung

Beim ersten Live-Einsatz wurden „Pause“ und „Halbzeitpause“ verwechselt.
Eine eindeutige Abschnittspause ersetzt die beiden konkurrierenden Bedienwege.
Der Ablauf verwendet Sportprofile und eine gemeinsame Live-Projektion.

LiveScore erfasst Wettkampfdaten manuell und stellt sie anderen Anwendungen bereit.
Es ist keine Wettkampfregel-Engine. In der Bedienoberfläche gibt es nur Pausen
zwischen zwei Wettkampfabschnitten. Anzahl und Bezeichnung kommen aus dem Profil,
nicht aus der Sportart oder einem fest hinterlegten Fußballablauf.

Für die begriffliche Abgrenzung beim Boxen dienen die
[DBV-Wettkampfbestimmungen, Stand 01.09.2026](https://www.boxverband.de/wp-content/uploads/2026/09/DBV-WKB-Wettkampfbestimmungen.pdf):
§§ 58 und 60 unterscheiden Rundenwechsel und Unterbrechungen; § 99 und Anhang 4
beschreiben Rundenpausen getrennt von Unterbrechungen innerhalb einer Runde.
LiveScore übernimmt daraus keine Zeitnahme oder automatische Regelverarbeitung.

## Bedienlogik

1. Paarung und L/R prüfen, dann den ersten Abschnitt starten.
2. Während des Abschnitts stehen Score, konfigurierte Zähler, Undo und Seitenwechsel bereit.
3. Solange ein weiterer Abschnitt folgt, steht die passende Abschnittspause neben
   Seitenwechsel und vor Spiel Ende.
4. Während der Pause zeigt das Statusschild die Pause; der nächste Abschnitt kann
   mit dem bestehenden Bestätigungsdialog gestartet werden. Ein versehentliches
   Setzen lässt sich mit „Zurück zu Abschnitt n“ aufheben, ohne die Nummer zu ändern.
5. Der Abschnittswechsel beendet die Pause. Scores, Seiten und Officials bleiben;
   Zähler werden gemäß Profil zurückgesetzt oder übernommen. Bisherige Werte bleiben gespeichert.
6. Beim letzten Abschnitt und ohne weitere Abschnitte entfällt die Pausensteuerung.
   Der Bediener bestätigt das Wettkampfende; ein früheres Ende ist ebenfalls möglich.

Die Abfolge `Abschnitt n → Pause → Abschnitt n+1` funktioniert für jede konfigurierte
Anzahl. Bekannte Begriffe werden in EN/DE/CS übersetzt: Halbzeit/Half/Poločas,
Runde/Round/Kolo und Satz/Set. Eigene Bezeichnungen bleiben erhalten und verwenden
den neutralen Pausenbegriff. Diese Zuordnung ist Anzeigevokabular, keine Sportregel.

Seitenwechsel ist eine unabhängige Aktion. Es gibt keinen allgemeinen Pause-/
Fortsetzen-Button. Verletzungen, Time-outs oder andere kurzfristige Unterbrechungen
innerhalb eines Abschnitts werden nicht erfasst. Keine Uhr, automatische Pausendauer,
automatische Abschnittswechsel, Verlängerungs-, Strafstoß- oder Wertungslogik.

## Wiederöffnen

„Spiel wieder öffnen“ behält den bestehenden Bestätigungsdialog und führt direkt
von `finished` zu `live`. Score, Seiten, Abschnitt, Counter und Officials bleiben
unverändert. Alle Aktionen sind sofort verfügbar; kein weiterer Fortsetzen-Schritt.
Eine beim Spielende aufgehobene Abschnittspause wird nicht automatisch rekonstruiert.

## Daten und API-Kompatibilität

- Vorhandene Felder `periods`, `period_label`, `period` und `intermission` genügen.
  Keine neuen Datenfelder, keine Migration; Schema-Version bleibt 1.
- Feldnamen und Typen von `GET /api/v1/live` bleiben erhalten. Die bisherigen
  Halbzeit-Codes und englischen API-Labels bleiben als Darstellungskompatibilität
  bestehen; die GUI verwendet sie nicht zur Steuerung ihres Ablaufs.
- Bewusste Verhaltensänderung: Wiederöffnen liefert `live` statt `paused`.
- Alte `paused`-Stände bleiben unverändert ladbar und sofort bedienbar.
  Die gemeinsame Live-Projektion von GET, Tournament-Snapshot und WebSocket liefert
  dafür `status: "live"`. Die tatsächliche Abschnittspause steht unabhängig davon
  in `period_info.intermission`.
- Rohe Match-Daten und Exporte behalten gegebenenfalls `paused`. Die alten
  `pause`-/`resume`-Endpunkte bleiben mit ihren Validierungen erhalten, sind aber
  in OpenAPI veraltet und in der GUI nicht vorhanden.
- Externe Anwendungen dürfen nach Wiederöffnen nicht mehr zwingend `resume`
  senden. Pausenanzeigen müssen `period_info.intermission` statt `status == paused`
  auswerten. [Details im API-Vertrag](../API.md#kompatibilität-abschnittspausen-und-wiederöffnen-issue-5).
- Der direkte API-Abschnittswechsel bleibt erlaubt. Die GUI führt ihn über die Pause;
  es wird keine zusätzliche Regelpflicht im Backend eingeführt.

## Verifikation und Akzeptanz

- [x] Keine allgemeine Pause-/Fortsetzen-Schaltfläche; Abschnittspause vor Spiel Ende.
- [x] Passende Bezeichnungen aus dem Profil in EN/DE/CS, eigene Begriffe bleiben erhalten.
- [x] Mehr als zwei Abschnitte, ein Abschnitt und fehlendes Profil geprüft.
- [x] Nächsten Abschnitt nur während der Pause anbieten; Korrektur ändert keine Nummer.
- [x] Dialogabbruch und konkurrierende Änderungen sicher; zwei Browser sind synchron.
- [x] Score und Counter bleiben an Teilnehmer gebunden, auch bei Seitenwechsel mit 2:1.
- [x] Wiederöffnen ist direkt LIVE; Undo, Counter und Score funktionieren ohne Resume.
- [x] Alte `paused`-Daten, API-Kompatibilität, Export und Neustart geprüft.
- [x] Unit-Tests und Browser-Smokes erfolgreich; Dokumentation und Arbeitsregeln aktualisiert.

Die Prüfung verwendet eigene Datenverzeichnisse und lokale Testserver. Ein Rollout
auf laufende Veranstaltungsinstanzen ist nicht Bestandteil dieses Auftrags.

Ergebnis: **144 Unit-Tests bestanden**, dazu die Browser-Smokes für Bedienung und
Auth sowie **neun Profilvarianten in EN/DE/CS mit zwei Browsern**. Ein zusätzlicher
CS-Lauf prüft unveränderte eigene Abschnittsnamen und Counter nach Wiederöffnen.
Mobile Screenshots wurden visuell geprüft; Dokumentationslinks, JSON-/YAML-Beispiele,
Shell-Syntax und Git-Diff sind geprüft. Native Windows-Prüfungen wurden nicht ausgeführt.
