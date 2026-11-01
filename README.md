# LiveScore

[![Version 0.2.4](https://img.shields.io/badge/version-0.2.4-blue)](VERSION)

LiveScore erfasst Live-Spielstände bei Turnieren und stellt sie für Anzeigetafeln,
Dashboards und Grafikoverlays in TV- und Livestreamproduktionen bereit.
Es unterstützt Begegnungen zwischen zwei Mannschaften oder Einzelpersonen.
Die Bedienung erfolgt im Browser auf Smartphone, Tablet oder Rechner.

**Status:** In Entwicklung – installierbar und mit den unten beschriebenen
Funktionen nutzbar.

Die Anwendung läuft auf einem lokalen Server und funktioniert nach der Installation
auch ohne Internet. Veranstaltungsdaten werden als JSON-Dateien gespeichert;
eine Datenbank ist nicht erforderlich. LiveScore ergänzt die Turnierverwaltung um
die Live-Erfassung, übernimmt aber keine Tabellenberechnung oder automatische
Ermittlung von Finalpaarungen.

## Funktionen

- Veranstaltungen, Wettkampfflächen (Play Areas), Teilnehmer, Referees und Spielpläne
  im Browser anlegen und bearbeiten; native LiveScore-JSON-Dateien importieren und exportieren.
- Je nach Profil Gesamtstände oder Satzpunkte erfassen, gewonnene Sätze manuell
  führen und Eingaben mit **UNDO** korrigieren.
- Paarungen korrigieren, auch nach Spielbeginn durch Zurücksetzen des einzelnen Spiels;
  Links/Rechts zuordnen, Seiten wechseln
  und Ergebnisse bestätigen.
- Sieben fertige Sportprofile – Blindenfußball, Showdown, Boxen, Fußball,
  Handball, Tischtennis und Volleyball – auswählen und im Browser anpassen;
  alle Profiltexte gemeinsam für DE/EN/CS pflegen. Wettkampfdaten werden manuell
  erfasst; Wettkampfregeln wertet LiveScore nicht automatisch aus.
- Mehrere Bediener sehen und bearbeiten gemeinsam denselben aktuellen Spielstand.
- Oberfläche auf Englisch, Deutsch und Tschechisch; getrennte Zugänge für
  Administration und Bedienung.

Pro Instanz sind **eine Veranstaltung und ein Spiel gleichzeitig aktiv**.
Scores bleiben beim Seitenwechsel immer ihrem Teilnehmer zugeordnet.

## Installation und Start

Voraussetzungen: **Python 3.12 oder neuer**, `venv`, `pip` und Git.
Für die Installation werden GitHub und PyPI benötigt.

### Linux als Dienst

Auf Linux mit systemd:

```sh
git clone https://github.com/richtertoralf/LiveScore.git
cd LiveScore
sudo ./install.sh
systemctl status livescore
```

Der Dienst startet nach der Installation und beim Booten automatisch.
Unter **http://localhost:8730/** ist die Oberfläche erreichbar. Von anderen
Geräten im lokalen Netz die Adresse des LiveScore-Servers statt `localhost` verwenden.
Host und Port sind konfigurierbar.

### Manuell starten

Unter Linux im geklonten Repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m livescore
```

Der Server läuft im Vordergrund. Für Windows, Konfiguration, Updates und Backups
siehe [Installation und Betrieb](docs/INSTALLATION.md).

### Erste Anmeldung und sichere Einrichtung

Jede neue Installation startet mit den allgemein bekannten Zugängen
**admin / admin** (Administration) und **operator / operator** (Bedienung).
Beim ersten Admin-Login führt LiveScore direkt zur Benutzerverwaltung:

1. Zuerst das eigene Admin-Passwort ändern.
2. Danach das Operator-Passwort setzen. Neue Passwörter haben 12 bis 1024 Zeichen.
3. Erst danach weitere Geräte im Netz anmelden. Für einen Zugang aus dem
   Internet zusätzlich HTTPS einrichten.

Passwörter liegen als Hashwerte in `/etc/livescore/auth.yml`; Wiederherstellung
und HTTPS beschreibt [Installation und Betrieb](docs/INSTALLATION.md#benutzer-und-passwörter).

## Verwendung

1. Unter **Veranstaltungen** eine Veranstaltung anlegen oder eine LiveScore-JSON-Datei
   importieren und anschließend **Auswählen**.
2. Als Admin unter **Konfiguration → Sportprofile** eines der sieben Standardprofile
   auswählen und **Für Veranstaltung übernehmen**; bei Bedarf anpassen. Play Areas,
   Teilnehmer, Referees und Spielplan erfassen.
3. In der **Bedienung** ein Spiel auswählen, die Paarung bestätigen oder korrigieren
   und Links/Rechts im Programmbild festlegen.
4. Wettkampf starten und die vorgesehenen Punkte, Satzgewinne oder Zähler erfassen;
   bei Bedarf **UNDO** oder **Seitenwechsel**
   nutzen. Zwischen Abschnitten eine Abschnittspause setzen und den nächsten Abschnitt starten.
5. Mit **Spiel Ende** den Endstand prüfen und **Ergebnis bestätigen**.
   Danach das nächste Spiel auswählen.

Zum Ausprobieren liegt der Spielplan des Blindenfußballturniers Prag 2026 als
[Beispieldatei](examples/prague-2026.json) bei. Eine frische Linux-Dienstinstallation
wählt diese Veranstaltung bereits aus; beim manuellen Start wird sie über
**Veranstaltungen → JSON importieren** geladen. Sie enthält vorbereitete Spiele,
keine tatsächlichen Turnierergebnisse.

Details zu Abschnitten, Zählern, Ergebniskorrekturen und Importen stehen in der
[Bedienungsanleitung](docs/OPERATOR.md).

## Live-Daten für andere Anwendungen

Der öffentliche Endpunkt **`GET /api/v1/live`** liefert den aktuellen Spielzustand
als JSON mit Teilnehmern, Scores und den bereits zugeordneten Seiten `left` und
`right`. Das Profil kennzeichnet, welche Daten vorgesehen sind; Abschnittspunkte, Satzgewinne,
Pausen und feste Teilnehmerrollen sind eindeutig unterscheidbar.

```sh
curl --fail http://localhost:8730/api/v1/live
```

Andere Anwendungen können die URL beispielsweise einmal pro Sekunde abfragen;
eine Anmeldung ist für diesen Endpunkt nicht nötig. LiveScore stellt die Daten
bereit, die Darstellung übernimmt die jeweilige Anwendung.
[API-Dokumentation und Beispielantwort](docs/API.md).

Installationen vor Version 0.2.2 erhalten mit dem Upgrade diese Live-API;
angeschlossene Anwendungen müssen dann gegebenenfalls angepasst werden.

## Verwaltung unter Linux

| Befehl | Zweck |
|---|---|
| `livescore --version` | installierte Version mit Commit |
| `livescore --status` | Version, Dienst, Erreichbarkeit der Weboberfläche, LAN-Adressen, Pfade von Konfiguration und Daten; ohne root |
| `sudo livescore --upgrade` | auf den aktuellen Stand von GitHub aktualisieren |
| `sudo livescore --upgrade --source PFAD` | aus einem lokalen Checkout aktualisieren |
| `sudo /opt/livescore/current/uninstall.sh` | Programm entfernen; Konfiguration, Zugänge, Veranstaltungsdaten und Backups bleiben |

Details: [Installation und Betrieb](docs/INSTALLATION.md).

## Weiterführende Informationen

- [Installation und Betrieb](docs/INSTALLATION.md): Windows-Start, Serverkonfiguration,
  Passwörter, HTTPS, Upgrade, Backup und Deinstallation.
- [Bedienungsanleitung](docs/OPERATOR.md): Vorbereitung und Einsatz am Wettkampftag.
- [Sportprofile](docs/SPORT_PROFILES.md): Standardprofile, Erfassungsmodi und fachliche Grundlagen.
- [API](docs/API.md): Datenfelder, Endpunkte und Zugriffsschutz.
- [Datenmodell](docs/DATA_MODEL.md): JSON-Format, Sportprofile und Persistenz.
- [Entwicklung](docs/DEVELOPMENT.md): Codeaufbau, Tests und offene Produktentscheidungen.

LiveScore steht unter der [Apache-2.0-Lizenz](LICENSE).

## Mitmachen

Fehler, Wünsche und Erfahrungen vom Turnier bitte als
[Issue auf GitHub](https://github.com/richtertoralf/LiveScore/issues) melden. Neue
Sportprofile und Übersetzungen sind ebenso willkommen wie Code; den Einstieg
beschreibt [Entwicklung](docs/DEVELOPMENT.md).

## RICHTER.PROJECTS

**Möglichkeiten schaffen.** LiveScore gehört zu RICHTER.PROJECTS. Turniere können
damit ihre Spielstände ohne eigene Datenbank und ohne Internet live erfassen und an
Anzeigetafeln, Grafikoverlays und Livestreams weitergeben – bedient im Browser,
von einem oder mehreren Geräten gleichzeitig.
