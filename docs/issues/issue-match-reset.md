# Bedienung: Spiel zurücksetzen und Paarung nach Spielbeginn korrigieren

> **Art:** Störungsbericht und Anforderung · **Status:** umgesetzt in 0.2.1 · **Priorität:** hoch
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

## Umgesetzte Lösung

**Spiel zurücksetzen / Paarung korrigieren** ist die einheitliche Korrekturaktion für
Operator und Admin aus `ready`, `live`, Legacy-`paused` und `finished`. Sie ersetzt
in der GUI auch das bisherige Zurücknehmen der Vorbereitung. Die vorhandene API
`unprepare` bleibt für vorbereitete Spiele verfügbar. Wiederöffnen dient weiterhin
der Fortführung mit erhaltenen Daten und führt seit Issue #5 direkt zu `live`.

Ein Bestätigungsdialog zeigt Spiel, Termin, Play Area, Paarung und Score sowie die
Folgen und die fehlende Undo-Möglichkeit. Das ausgewählte Spiel kehrt nach
`scheduled` zurück: Seiten, Scores und alle Counterhistorien leer, Abschnitt 1,
keine Abschnittspause. Planfelder einschließlich Paarung und Officials bleiben
stehen. Anschließend folgt die vorhandene Paarungsauswahl und Vorbereitung.
Andere Spiele, Ergebnisse und Veranstaltungsdaten bleiben unverändert.

`POST /api/v1/live/reset` nutzt vorhandene Kontext-, Revisions- und Request-ID-Prüfungen.
Konkurrierende Änderungen verlangen eine erneute Bestätigung; verspätete Score-/Counter-
Requests bleiben auch nach erneutem Start und Spielplanbearbeitung ungültig.
Die Kontrollrevision wird dabei niemals zurückgesetzt. Speicherung und Browserausgabe
erfolgen über die vorhandene atomare Persistenz und WebSocket-Verteilung.

Das Protokoll wird nicht gelöscht: `match_reset` grenzt den neuen Spielversuch ab.
Undo erreicht keine Score-Aktion vor dieser Grenze, auch nach Paarungsänderung,
Export/Import und Neustart. Frühere Ereignisse behalten ihre ursprünglichen
Undo-Markierungen. Keine neuen Modellfelder, Sportregeln oder Pausenfunktionen.

Bedienung: [Operator-Dokumentation](../OPERATOR.md#einzelnes-spiel-korrigieren).
Vertrag und Kompatibilität: [API](../API.md#einzelnes-spiel-zurücksetzen-issue-4).
Die aktive Veranstaltung ist bereits in der Navigation sichtbar. Das Löschen von
Veranstaltungen bleibt außerhalb dieses Auftrags. Die oben beschriebene Notkorrektur
ist ein historischer Einsatzbericht, keine aktuelle Betriebsanleitung.

## Verifikation

Automatisierte API-Tests prüfen alle erlaubten Zustände, Isolation anderer Ergebnisse
und Planfelder, Score-Undo über mehrere Spielversuche, neue Paarungen, Eventvalidierung,
Export/Import, Neustart, Request-Deduplizierung, veraltete Bestätigungen, konkurrierende
Operatoren, WebSocket-Ausgabe, Schreibfehler sowie Operator-, CSRF- und Login-Rechte.
Der Browsertest `tests/browser_reset_smoke.py` prüft zwei Operator-Logins in DE/EN/CS,
Box-/Showdown-Profile und kein Profil, mobile und Desktop-Ansichten, Dialogabbruch,
Konflikte, Abschnittspausen, Paarungskorrektur und Wiederherstellung.

Ergebnis für 0.2.1: **156 Unit-Tests bestanden**, neuer Korrektur-Browsertest sowie
bestehende Bedienungs- und Auth-Browsertests bestanden. JSON-Beispiele und API-Beispiele
wurden validiert. Das echte CLI-Upgrade von der veröffentlichten 0.2.0 auf 0.2.1
bestand mit unveränderten Veranstaltungsdaten, Profilbibliothek und Zugangsdaten.
