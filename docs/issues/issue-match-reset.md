# Bedienung: Spiel zurücksetzen und Paarung nach Spielbeginn korrigieren

> **Art:** Störungsbericht und Anforderung · **Status:** offen · **Priorität:** hoch
>
> Geprüfter Stand: LiveScore 0.1.2 (Produktivsystem `mediamtx18`, Prag 2026, 4. Oktober 2026).

## Anforderung

Mit Fehlbedienungen ist immer zu rechnen. Korrekturen müssen deshalb in der Bedienoberfläche einfach möglich sein, ohne Admin-Rechte, Dateien, SSH oder Neustart.

Insbesondere muss ein Spiel neu gestartet werden können. Auch nach Spielbeginn oder Spielende muss eine falsch eingetragene Paarung korrigierbar sein.

## Vorfall

Im Spiel um die Goldmedaille (`match-014`) wurde **ASAMEA Keravnos Athens gegen Kairat Almaty** eingetragen und gestartet. Laut den gespeicherten Halbfinals waren aber Kairat Almaty (1:0 gegen ASAMEA) und SF B/G BLISTA Marburg (1:0 gegen BSC Praha) die Finalisten.

Das Ereignisprotokoll zeigt die Versuche, das Spiel in der Oberfläche zu korrigieren:

```text
match_selected → prepare → match_started → counter (Teamfoul ASK) → side_switch
→ match_finished → match_selected → match_reopened → match_finished
→ match_reopened → match_finished
```

Mit „Spiel Ende“ und „Wiederöffnen“ war die Paarung nicht zu korrigieren. Vermutlich wurde danach die Veranstaltung als neue Veranstaltung `prague-2026-2` importiert und ausgewählt. Auch dort stand das Goldmedaillenspiel wieder mit der falschen Paarung auf `paused`.

## Ursachen in LiveScore 0.1.2

1. **Kein Rückweg nach Spielbeginn.** Erlaubt sind nur `scheduled → ready → live ⇄ paused → finished` und `finished → paused`. `unprepare` funktioniert nur aus `ready` (`livescore/service.py`). Nach dem Start kann die Paarung nicht mehr geändert werden.
2. **„Wiederöffnen“ übernimmt den alten Stand.** Score, Paarung, Seiten und Teamfouls bleiben erhalten. Das Spiel kommt nur zurück nach `paused`.
3. **Zurücksetzen gibt es nur für die ganze Veranstaltung.** Der Admin-Button setzt **alle** Spiele auf die Importdatei zurück. Am letzten Turniertag hätte das sämtliche Ergebnisse gelöscht. Außerdem ist er gesperrt, solange ein Spiel `ready`, `live` oder `paused` ist.
4. **„Bestehende Veranstaltung ersetzen“ ist am Wettkampftag nicht praktikabel.** Man muss exportieren, die JSON von Hand bearbeiten (auch die Score-Ereignisse des Spiels entfernen, sonst lehnt die Validierung die Datei ab) und die Datei vom Bedienrechner hochladen. Am Bedienrechner gab es dafür weder die Datei noch die Möglichkeit, sie zu bearbeiten.
5. **Mehrere gleichnamige Veranstaltungen.** Nach einem Import als neue Veranstaltung gab es `prague-2026` und `prague-2026-2`. Welche aktiv ist, steht nur in `active-event.json`. Die Korrektur wurde zunächst an der falschen Datei vorgenommen.

## Durchgeführte Notkorrektur

Die Korrektur lief per SSH auf dem Server, mit zwei Dienstneustarts:

1. Event-Datei aus `/var/lib/livescore/data/events/` kopiert.
2. In der Kopie bei `match-014` gesetzt: `status: scheduled`, Paarung, Seiten, Scores und Teamfouls geleert, `period: 1`. Alle Ereignisse zu `match-014` entfernt, Revision über den Live-Stand angehoben und gegen `State` validiert.
3. Dienst gestoppt, Datei als `events/prague-2026.json` eingesetzt, `active-event.json` auf `prague-2026` gestellt und den Dienst gestartet.
4. Kontrolle über `GET /api/v1/live`: `match-014`, `scheduled`, ohne Teilnehmer, Revision 300.

Fehlerquellen dabei: ein Tippfehler im Dienstnamen (Dienst lief weiter), umbrochene Befehlszeilen beim Einfügen und ein `!` vor dem Befehl in der Shell. Die Sicherung liegt in `events/prague-2026.json.bak-gold`. `prague-2026-2` enthält weiterhin den fehlerhaften Stand und sollte nicht mehr ausgewählt werden.

## Lösungsvorschlag (noch nicht umgesetzt)

Eine Aktion **„Spiel zurücksetzen“** für das ausgewählte Spiel, für Operator und Admin:

- erlaubt aus `ready`, `live`, `paused` und `finished`;
- setzt das Spiel auf `scheduled` zurück: Seiten und Scores leer, Teamfouls leer, Abschnitt 1, keine Halbzeitpause;
- behält die Planfelder (Paarung oder Platzhalter, Officials, Zeit, Play Area), sodass der Bediener danach wie gewohnt die Paarung bestätigt oder korrigiert und L/R festlegt;
- markiert die bisherigen Score-Ereignisse des Spiels so, dass Undo sie nicht mehr erreicht, und protokolliert ein Ereignis `match_reset`; das Protokoll bleibt nachvollziehbar;
- ist als kritische Aktion durch einen Bestätigungsdialog geschützt, mit Nennung von Spiel und aktuellem Score;
- lässt alle anderen Spiele unverändert.

Damit wären Ursachen 1 bis 4 für den Bediener gelöst. Für Ursache 5 genügt vorerst ein deutlicher Hinweis auf die aktive Veranstaltung in `/events`. Löschen von Veranstaltungen ist ein eigener Auftrag.

Vor der Umsetzung zu klären:

- Reicht diese eine Aktion, oder soll bei `ready`/`live` zusätzlich „Paarung ändern“ direkt angeboten werden? Empfehlung: nur „Spiel zurücksetzen“, denn danach folgt der normale Ablauf.
- Erhält die öffentliche API dabei einen sichtbaren Zwischenzustand? Nach dem Zurücksetzen liefert `GET /api/v1/live` `scheduled` ohne Teilnehmer, wie vor jedem Spiel.

Tests mindestens: Zurücksetzen aus jedem erlaubten Zustand, kein Einfluss auf andere Spiele, Undo nach dem Zurücksetzen erreicht keine alten Scores, erneutes `prepare` mit anderer Paarung, Wiederherstellung nach Neustart, `GET /api/v1/live` danach.
