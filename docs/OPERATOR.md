# Bedienung am Wettkampftag

## Zugang und Sprache

Die Bedienung liegt unter `/`, die Veranstaltungsverwaltung unter `/events`,
die Konfiguration der aktiven Veranstaltung unter `/config`.
Mit **EN / DE / CS** im Header lässt sich die Sprache wechseln; Englisch ist
die Voreinstellung. Der Wechsel lädt die Seite neu, deshalb Formulare vorher
speichern. Namen und frei eingegebene Texte werden nicht übersetzt.

`operator` und `admin` können alle fachlichen Daten bearbeiten und Spiele bedienen.
Nur `admin` darf Passwörter verwalten sowie Veranstaltungen zurücksetzen oder
durch einen Import ersetzen. [Zugang einrichten und Passwörter zurücksetzen](INSTALLATION.md#benutzer-und-passwörter).

## Veranstaltung vorbereiten

1. Unter **Veranstaltungen** eine Veranstaltung mit Name und Zeitraum anlegen
   oder eine native LiveScore-JSON-Datei importieren. Danach **Auswählen** klicken;
   Anlegen und Importieren aktivieren die Veranstaltung nicht automatisch.
2. Unter **Konfiguration** Ort, Score-Bezeichnung und Play Areas festlegen.
   Eine Play Area kann etwa „Field 1“, „Table 1“ oder „Ring A“ heißen.
3. Teilnehmer mit Namen, optional Kurznamen und Ländercodes erfassen.
   Ländercodes sind zweistellig, etwa `CZ` oder `DE`.
4. Referees erfassen und den Spielen als Officials zuweisen. Der Spiel-Editor
   bietet drei optionale Plätze; bei importierten Spielen mit mehr Officials
   bleiben alle Zuweisungen bearbeitbar.
5. Spiele mit Datum, Uhrzeit, Play Area, optional Turnierphase und Runde anlegen.
   Spiele müssen im Veranstaltungszeitraum liegen. Offene Paarungen dürfen
   Platzhalter tragen; sie werden vor Spielbeginn manuell festgelegt.

Vorhandene Einträge zum Bearbeiten auswählen. IDs bleiben dabei erhalten.
Logo-Pfade sind Metadaten; ein Bild-Upload ist nicht enthalten.
Sportprofile für Abschnitte und Zähler werden per JSON oder API hinterlegt;
einen Profil-Editor gibt es nicht. Das Format steht im [Datenmodell](DATA_MODEL.md#sportprofil).

Es gibt eine aktive Veranstaltung und ein gemeinsam ausgewähltes Spiel,
auch bei mehreren Play Areas. Ein vorbereitetes oder laufendes Spiel sperrt
Veranstaltungswechsel und Konfiguration. Das gilt auch während einer Abschnittspause.
Vor dem Start kann die Vorbereitung
zurückgenommen werden; nach dem Start muss das Ergebnis bestätigt werden.

## Spiel bedienen

1. In der **Bedienung** ein Spiel auswählen. Die Liste ist nach Datum und Uhrzeit sortiert.
2. **Paarung bestätigen** oder **Paarung ändern**. Zwei verschiedene bekannte
   Teilnehmer sind erforderlich. L/R prüfen und bei Bedarf **Seiten tauschen**.
3. Den Wettkampf starten: je nach Profil etwa **1. Halbzeit starten**, **1. Runde starten**
   oder **1. Satz starten**, ohne Profil **Spiel starten**. Score mit **+1 / −1** erfassen.
   Negative Scores sind nicht möglich.
4. **UNDO** nimmt die letzte noch nicht zurückgenommene Score-Aktion dieses Spiels
   zurück, auch die eines anderen Bedieners. Das funktioniert nach Seitenwechsel,
   Reload und Serverneustart. Zähleränderungen werden nicht mit Undo zurückgenommen.
5. Bei Bedarf eine **Abschnittspause** setzen oder **Seitenwechsel** nutzen.
   Beide wirken für alle Browser. Score-Korrekturen und Undo bleiben in der Pause möglich.
6. **Spiel Ende** öffnet die Endstandprüfung. Erst **Ergebnis bestätigen** beendet
   das Spiel. Bei zwischenzeitlichen Änderungen durch einen anderen Bediener
   muss der neue Stand erneut geprüft werden.
7. Nächstes Spiel auswählen. Ergebnisse bleiben im Spielplan erhalten.

**L/R bezeichnet links/rechts im Programmbild oder Overlay.** Ein Seitenwechsel
vertauscht die Darstellung; Namen, Scores, Länder und Zähler bleiben beim Teilnehmer.

Wurde ein Spiel versehentlich beendet, lässt es sich mit **Spiel wieder öffnen**
nach Bestätigung fortsetzen. Frühere Spiele sind über **Beendete Spiele anzeigen**
erneut auswählbar, sofern kein anderes Spiel vorbereitet oder aktiv ist.
Score, Seiten, Abschnitt und Zähler bleiben erhalten; der Wettkampf ist sofort
wieder **LIVE** und bedienbar. Eine zuvor gesetzte Abschnittspause wurde durch das
Spielende beendet und muss gegebenenfalls erneut gesetzt werden.

Die Paarung lässt sich nach Spielbeginn nicht mehr ändern. Wiederöffnen hebt diese
Sperre nicht auf. Ein Zurücksetzen einzelner Spiele ist noch nicht implementiert;
das Zurücksetzen einer ganzen Veranstaltung ist dafür kein geeigneter Ersatz.

## Wettkampfabschnitte, Pausen und Zähler

Bei konfiguriertem Sportprofil erscheinen Abschnittssteuerung und zusätzliche
Zähler, etwa Teamfouls. Zähler werden mit **+1 / −1** korrigiert und können nicht
negativ werden. Warnschwellen verändern nur die Anzeige und lösen keine Sportregel
oder Strafaktion aus.

Es gibt eine Art von Pause: **zwischen zwei Wettkampfabschnitten**. Anzahl und
Bezeichnung kommen aus dem Sportprofil; der Ablauf ist für jede Anzahl gleich:

```text
Abschnitt n → Abschnittspause → Abschnitt n+1
```

Der Pausenbutton steht neben **Seitenwechsel**, vor **Spiel Ende**. Bei bekannten
Abschnittsbegriffen heißt er **Halbzeitpause**, **Rundenpause** oder **Satzpause**;
Eigene Begriffe bleiben erhalten; ihr Pausenbutton heißt **Pause zwischen
Abschnitten**. Das Statusschild zeigt die jeweilige Pause deutlich an.

Erst während dieser Pause erscheint beispielsweise **2. Runde starten**.
Der bestehende Bestätigungsdialog schützt den Abschnittswechsel. Eine versehentlich
gesetzte Pause lässt sich mit **Zurück zu 1. Runde** aufheben; das ändert keinen
Abschnitt. Beim letzten Abschnitt und ohne weitere konfigurierte Abschnitte gibt es
keine Pausensteuerung. Abschnitte können weder übersprungen noch zurückgeschaltet werden.

Beim Abschnittswechsel bleiben Score, Seiten und Officials erhalten. Zähler beginnen
je nach Profil bei null oder übernehmen den bisherigen Wert; frühere Abschnittswerte
bleiben gespeichert. Auch während einer Abschnittspause sind Score, Zähler, Undo
und Seitenwechsel bedienbar. Es gibt keine allgemeine Pause-/Fortsetzen-Schaltfläche.
Unterbrechungen innerhalb eines Abschnitts, etwa Verletzungen oder Time-outs, werden
nicht erfasst. Keine Spieluhr, automatische Pausendauer oder automatischer Wechsel;
der Bediener entscheidet über Abschnittswechsel und Wettkampfende.

## Import, Export und Zurücksetzen

Unter **Veranstaltungen → JSON importieren** eine native LiveScore-Datei auswählen
(maximal 10 MiB). Die Vorschau prüft die Datei und zeigt deren Inhalt an;
erst **Importieren** speichert sie. Ein importierter Live- oder Pausenstand bleibt
erhalten. Ältere gespeicherte `paused`-Stände sind sofort bedienbar und werden als
laufend angezeigt; nur `intermission` kennzeichnet eine Abschnittspause.
Bei gleicher Veranstaltungs-ID kann der Import abgebrochen oder als
neue Veranstaltung gespeichert werden. Ein normaler Import überschreibt nichts.

**JSON exportieren** lädt den vollständigen Stand einer Veranstaltung mit Scores,
Zählerhistorie und Ereignisprotokoll herunter. Auch inaktive Veranstaltungen sind
exportierbar. CSV und Fremdformate sowie eine automatische Tournify-Anbindung sind
nicht implementiert.

Für den Admin stehen zwei weitere Aktionen zur Verfügung:

- **Zurücksetzen** lädt eine Veranstaltung aus ihrer gespeicherten Importdatei neu.
  Verfügbar ist dies nach einem JSON-Import und für die vom Installer angelegte Prag-Veranstaltung.
- **Bestehende Veranstaltung ersetzen** übernimmt bei einer ID-Kollision eine
  andere Importdatei und macht sie zur neuen Grundlage für das Zurücksetzen.

Beide Aktionen verlangen eine Bestätigung. Sie ersetzen **alle Spiele, Ergebnisse,
Paarungen, Konfiguration und das Ereignisprotokoll** der betroffenen Veranstaltung.
Bei Bedarf vorher exportieren. Für die aktive Veranstaltung sind sie gesperrt,
solange ein Spiel vorbereitet oder laufend ist. Manuell angelegte oder ältere
importierte Veranstaltungen ohne gespeicherte Importdatei können erst nach einem
ausdrücklichen Ersetzen zurückgesetzt werden.

## Mehrere Bediener und Verbindungsverlust

Alle Browser bedienen dasselbe ausgewählte Spiel. Zwei getrennte Score-Klicks
verschiedener Bediener zählen als zwei Aktionen; doppelte Erfassung mit Undo korrigieren.

Bei Verbindungsverlust zeigt die Oberfläche **Offline · Bedienung gesperrt**.
Aktionen werden offline nicht gesammelt. Nach Wiederverbindung wird der aktuelle
Serverstand geladen. Bei unklarer HTTP-Antwort zuerst die Anzeige prüfen, bevor
erneut gebucht wird. Ein Reload löst keine Aktion erneut aus.
