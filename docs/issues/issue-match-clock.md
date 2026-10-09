> **Art:** Dokumentation einer Produktentscheidung · **Status:** zurückgestellt · **Priorität:** niedrig / Future

## Entscheidung

LiveScore führt **keine eigene Spielzeit**.

Insbesondere gibt es:

- keine Start-/Stop-Buttons für eine Uhr,
- keine Korrektur oder Anpassung einer Uhr durch den Bediener,
- keine Ableitung einer Spielzeit aus Spielstart, Halbzeit oder Spielende,
- keine Erfassung von Spielunterbrechungen, Team-Time-outs, Referee-Time-outs oder Verletzungsunterbrechungen.

Die Bedienoberfläche erhält dadurch keine zusätzlichen zeitkritischen Bedienelemente.

## Begründung

LiveScore erfasst nur die Informationen, die für Livegrafik, Spielstand, Teamfouls, Links/Rechts-Zuordnung, die Unterscheidung der Halbzeiten und das endgültige Spielende benötigt werden.

Eine von LiveScore selbst geführte Spielzeit liefert dafür keinen notwendigen Wert. Gleichzeitig würde sie Folgendes verursachen:

- Der Bediener müsste parallel zum offiziellen Zeitnehmer jede relevante Unterbrechung sekundengenau nachvollziehen. Im Blindenfußball hält der Zeitnehmer die offizielle Uhr bei zahlreichen Spielsituationen an.
- Es entstünde eine zweite Zeitnahme, die von der offiziellen Zeit abweichen kann.
- Die Bedienung würde unter Zeitdruck deutlich aufwendiger.

Dass das Sportregelwerk eine Spielzeit kennt, ist allein kein Grund, sie in LiveScore abzubilden.

## Ist-Stand

LiveScore 0.1.2 hat keine Uhr. `GET /api/v1/live` enthält keine Zeitinformation. Das README führt die Match-Uhr unter „Bewusste Grenzen“.

## Zukunftsthema

Eine spätere Übernahme einer externen offiziellen Zeitquelle ist ein eigenständiges Zukunftsthema. Sie wird erst betrachtet, wenn ein konkreter Integrationsfall vorliegt und das ausdrücklich beschlossen wird. An der heutigen Bedienlogik ändert sie nichts.

## Status / Priorität

- **Status:** zurückgestellt
- **Priorität:** niedrig / Future
- Keine Implementierung geplant.
