# Sportprofile

Ein Sportprofil legt Erfassung und Darstellung fest. Es wertet keine Wettkampfregeln
aus: Punkte, Satzgewinne, Zähler, Abschnittswechsel und Spielende werden manuell bedient.
Es gibt weder Zeitmessung noch automatische Gewinnerermittlung.

## Auswahl und Pflege

Nach Installation oder `sudo livescore --upgrade` erscheinen sieben Standardprofile
unter **Konfiguration → Sportprofile → Profil auswählen**. Ein Profil auswählen und
mit **Für Veranstaltung übernehmen** als eigenständige Kopie speichern. Bestehende
Veranstaltungen erhalten beim Upgrade kein anderes Profil.

Nur der Admin verwaltet Profile. Die Bibliothek ist auch ohne ausgewählte Veranstaltung
verfügbar. **Neues Profil**, **In Bibliothek speichern**, **Als neues Profil bearbeiten**
und **Aus Bibliothek löschen** dienen der Pflege unabhängig von Veranstaltungen.
DE, EN und CS stehen für alle Bezeichnungen gemeinsam im Editor. Die Oberflächensprache
ändert nur die Anzeige, niemals die bearbeitbaren Übersetzungen.

## Erfassungsoptionen

| Einstellung | Bedeutung |
|---|---|
| Punkteerfassung | Kein Punktestand, fortlaufender Gesamtstand oder getrennte Punkte je Abschnitt |
| Gewonnene Sätze | Separater, manuell korrigierbarer Satzstand; keine automatische Übernahme aus Punkten |
| Punkteschritte | Positive Schrittwerte, beispielsweise `1, 2`; die Bedienung bietet dazu Plus und Minus |
| Abschnitte | Maximale Anzahl, Abschnitts- und Pausenbezeichnung |
| Feste Rollen | Rollen für Teilnehmer 1 und 2 der Paarung, mit je drei Sprachtexten |
| Spielplanangaben / Officials | In der Wettkampfbedienung und der aufbereiteten Live-API anzeigen oder ausblenden |
| Zähler | Ein-/ausblenden, Beschriftungen, optionale Anzeigegrenzen und Rücksetzen beim Abschnittswechsel |

Rollen gehören zur Paarung: Im Boxprofil ist Teilnehmer 1 die rote, Teilnehmer 2 die
blaue Ecke. Beim Bestätigen oder Korrigieren der Paarung werden diese Bezeichnungen
angezeigt. Ein Bildschirm-Seitenwechsel vertauscht die Ecke nicht.

Bei abschnittsbezogenen Punkten beginnt die Anzeige beim nächsten Abschnitt bei null;
vorherige Punkte bleiben in der Abschnittstabelle gespeichert. Gewonnene Sätze bleiben
stehen und werden separat mit +1 / −1 erfasst. **UNDO** nimmt die letzte geeignete
Punkte- oder Satzaktion zurück, gegebenenfalls im vorherigen Abschnitt. Zähler werden
weiterhin mit Gegenbuchungen korrigiert. Wiederöffnen erhält alle Ergebnisse;
Zurücksetzen des einzelnen Spiels leert auch Abschnittspunkte und Satzstand.

Die Erfassungsstruktur bleibt nach Vorbereitung des ersten Spiels festgelegt:
Abschnittsanzahl, Punktemodus, aktivierte Satzerfassung, Zähler-IDs und deren
Rücksetzverhalten. Texte, Punkteschritte, Rollenbezeichnungen, Anzeigegrenzen und
Sichtbarkeit bleiben bearbeitbar. Zum Ändern der Struktur müssen alle Spiele wieder
geplant sein; verwendete Veranstaltungen können als Archiv erhalten bleiben.

## Ausgelieferte Ausgangsprofile

| Profil | Abschnitte / Pause | Punkte | Weitere Angaben |
|---|---|---|---|
| Blindenfußball | 2 Halbzeiten / Halbzeitpause | Tore fortlaufend, ±1 | Teamfouls je Halbzeit; Anzeigehinweise ab 4 und 5 |
| Showdown | maximal 3 Sätze / Satzpause | Satzpunkte, ±1 und ±2 | Manuell gewonnene Sätze; Best-of-Three als Ausgangspunkt |
| Boxen | 3 Runden / Rundenpause | Keine | Rote und blaue Ecke; keine Zähler, Spielplanangaben oder Officials in der Live-Ansicht |
| Fußball | 2 Halbzeiten / Halbzeitpause | Tore fortlaufend, ±1 | Keine zusätzlichen Zähler |
| Handball | 2 Halbzeiten / Halbzeitpause | Tore fortlaufend, ±1 | Keine zusätzlichen Zähler |
| Tischtennis | maximal 5 Sätze / Satzpause | Satzpunkte, ±1 | Manuell gewonnene Sätze; Best-of-Five als Ausgangspunkt |
| Volleyball | maximal 5 Sätze / Satzpause | Satzpunkte, ±1 | Manuell gewonnene Sätze; Best-of-Five als Ausgangspunkt |

Die Abschnittszahl ist eine konfigurierbare Obergrenze, keine vorgeschriebene Spieldauer.
Ein Spiel darf früher beendet werden. Auch bei erreichtem Punkt- oder Satzstand startet
oder beendet LiveScore keinen Abschnitt. Verlängerungen, andere Wettbewerbsformate und
zusätzliche Zähler vor Spielbeginn passend konfigurieren.

## Fachliche Grundlage

Prüfstand: 12. Oktober 2026. Übernommen werden nur Begriffe und sinnvolle
Ausgangskonfigurationen; sämtliche Regelentscheidungen bleiben bei der Spielleitung.

- [IBSA Blindenfußball, Regeln und Downloads](https://ibsasport.org/sports/football/about/rules-and-downloads/):
  Das dort verlinkte [Regelwerk 2026–2029](https://fileservice.aifdigitalsolutions.com/ibsa/2026%20IBSA%20Football%20-%20Laws%20of%20The%20Game_20260108111642669.pdf)
  beschreibt zwei Halbzeiten und kumulierte Teamfouls pro Halbzeit. Die vierte wird
  gekennzeichnet, ab der fünften bestehen besondere Freistoßregelungen. LiveScore
  zeigt ausschließlich den Zähler und neutrale Hinweise; keine Foulbewertung.
- [IBSA Showdown, Regeln und Downloads](https://ibsasport.org/sports/showdown/rules-and-downloads/):
  Die verlinkten [Regeln 2026–2028](https://fileservice.aifdigitalsolutions.com/ibsa/IBSA%20Showdown%20Rules%202026-2028_20260627105158866.pdf)
  erlauben Einzelspiele über ein, drei oder fünf Sätze und unterscheiden Ein- und
  Zweipunktwertungen. Drei ist hier eine veränderbare Ausgangswahl, keine Vorgabe für
  alle Turnierphasen oder Mannschaftswettbewerbe.
- [DBV-Wettkampfbestimmungen, September 2026](https://www.boxverband.de/wp-content/uploads/2026/09/DBV-WKB-Wettkampfbestimmungen.pdf):
  § 47 nennt drei Runden mit zwei Rundenpausen; Unterbrechungen innerhalb einer Runde
  sind davon getrennt. Altersabhängige Zeiten und Punktrichterwertung werden nicht erfasst.
- [IFAB, Regel 7](https://www.theifab.com/laws/latest/the-duration-of-the-match/):
  Zwei Halbzeiten und Halbzeitpause bilden den Ausgangspunkt für Fußball;
  Wettbewerbsvarianten und Verlängerungen sind nicht automatisch enthalten.
- [IHF, Hallenhandball-Regeln vom 1. Juli 2025](https://www.ihf.info/sites/default/files/2025-07/09A%20-%20Rules%20of%20the%20Game_Indoor%20Handball_E.pdf):
  Regel 2 beschreibt zwei Halbzeiten. Zeit-, Alters- und Verlängerungsregeln bleiben außerhalb des Profils.
- [ITTF Statutes 2026](https://db.ittf.com/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf):
  Regel 2.12 erlaubt eine ungerade Anzahl von Sätzen; fünf ist die hier gewählte,
  veränderbare Ausgangskonfiguration. Die englischen Begriffe sind „Game“ und „Games won“.
- [FIVB-Regeln 2025–2028](https://www.fivb.com/volleyball/the-game/official-volleyball-rules/):
  Drei gewonnene Sätze ergeben maximal fünf Sätze. 25 Punkte in regulären Sätzen und
  15 im Entscheidungssatz dienen nur der Orientierung; LiveScore hinterlegt keine
  Zielpunktzahlen und entscheidet keinen Satzgewinn.

## Bereitstellung und Datenerhalt

Alle Vorlagen liegen gemeinsam mit den Administratorprofilen in
`data_dir/sport-profiles.json`. Stabile IDs verhindern Duplikate. Der Installer ergänzt
fehlende Standardprofile vor dem Dienststart; reguläre Upgrades tun dies nach dem
Stoppen des Dienstes und vor dem Wechsel zur neuen Laufzeit. Auch ein manueller Start
ergänzt die Bibliothek automatisch. Beim ersten Upgrade über einen bisherigen
Installer übernimmt der automatisch neu gestartete Server diese Bereitstellung.

Bereits angepasste Profile, eigene Profile und Veranstaltungskopien bleiben erhalten.
Eine bewusst gelöschte Standardvorlage wird nicht wieder angelegt. Die Bibliothek
merkt sich bereitgestellte IDs gemeinsam in derselben Datei. Ungültige Dateien führen
zum Abbruch; Schreibfehler lassen die vorhandene Bibliothek unverändert. Scheitert das
Upgrade nach Bereitstellung, wird die vorherige Bibliothek vor dem Neustart der alten
Laufzeit wiederhergestellt.

Prag-Dateien bleiben ohne manuelle Migration importierbar. Ihre bisherigen Profile
verwenden weiterhin fortlaufende Scores. Teilnehmer, Paarungen, Wettkampfflächen und
Officials lassen sich auch für eine neue Boxveranstaltung verwenden; vorhandene
Bezeichnungen und Ergebnisse werden nicht automatisch umgeschrieben.

Die öffentliche Darstellung ist in [API.md](API.md) dokumentiert, die Speicherung der
Abschnittspunkte und Satzstände in [DATA_MODEL.md](DATA_MODEL.md).
