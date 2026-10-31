# Installation und Betrieb

Die Linux-Installation trennt Programm, Konfiguration und Veranstaltungsdaten.
Unterstützt wird Linux mit systemd und Python >= 3.12, insbesondere Ubuntu 24.04+
und vergleichbare Distributionen. Die Anwendung selbst bleibt manuell unter
Linux und Windows startbar. Die Installer benötigen Bash, Git, Python mit
`venv`/`pip`, systemd und die üblichen Werkzeuge zur Dienstkontoanlage.

Auf Ubuntu bei fehlenden Voraussetzungen einmal selbst installieren:

```sh
sudo apt-get install git python3 python3-venv
```

Der Installer verändert keine Paketquellen, Firewall, Proxy-Konfiguration oder
fremden Dienste. PyPI-Zugriff ist für die Dependency-Installation erforderlich,
GitHub-Zugriff für Download-Installation und Remote-Upgrades; der laufende
Veranstaltungsbetrieb ist offline möglich. Paketdownload-Fehler vor dem Umschalten
lassen die alte Laufzeit bestehen.

## GitHub-Zugang (öffentliches Repository)

`richtertoralf/LiveScore` ist öffentlich. Download-Installation und Remote-Upgrades
benötigen weder GitHub-Konto noch Token. `livescore --install` und
`livescore --upgrade` ohne `--source` klonen `main` per HTTPS ohne interaktive
Anmeldung. Credential-Helper und Passwortabfragen sind für diesen Download deaktiviert.
Das temporäre Download-Verzeichnis unter `/opt/livescore/.download-*` wird in jedem
Fall entfernt. Bei Git-Fehlern wird der Exitcode gemeldet.

Ältere installierte Stände können noch nach Zugangsdaten fragen. Für das erste
Upgrade dieser Stände einen aktuellen öffentlichen Checkout klonen und darin
`sudo ./upgrade.sh` ausführen. Danach verwendet auch `sudo livescore --upgrade`
den Download ohne Anmeldung.

## Erstinstallation

Aus einem öffentlichen Checkout ohne GitHub-Anmeldung:

```sh
git clone https://github.com/richtertoralf/LiveScore.git
cd LiveScore
sudo ./install.sh
livescore --version
livescore --status
```

`livescore --status` ist rein lesend und braucht kein root. Er zeigt Version,
Commit, Branch und Herkunft, den Zustand von `livescore.service` mit Autostart,
ob die Weboberfläche lokal antwortet, die URLs für alle LAN-Adressen (bei
Loopback-Bindung nur die lokale) und die Pfade von Konfiguration und Daten.
Ohne Leserecht auf `/etc/livescore` gelten Standardport 8730 und `0.0.0.0`; der
vollständige Status kommt dann mit `sudo livescore --status`. Exitcode 0: kein
technischer Fehler, auch bei bewusst gestopptem Dienst; 1: Dienst
fehlgeschlagen, aktiver Dienst antwortet nicht oder keine Installation; 2:
ungültige Konfiguration.

`install.sh` installiert den lokalen Checkout ohne weitere Abfrage. Alternativ lädt
`sudo ./bin/livescore --install` den aktuellen Stand von GitHub/main ohne Anmeldung.

| Pfad | Inhalt |
|---|---|
| `/opt/livescore/releases/<Laufzeit>/` | Programmcode, VERSION, mitgelieferte Prag-Dateien, eigene `.venv` |
| `/opt/livescore/current` | atomar wechselnder Link auf die aktuelle Laufzeit |
| `/usr/local/bin/livescore` | Link zum CLI-Wrapper der aktuellen Laufzeit |
| `/etc/livescore/livescore.yml` | lokale Serverkonfiguration |
| `/etc/livescore/auth.yml` | lokale scrypt-Passworthashes; entsteht beim ersten Serverstart |
| `/var/lib/livescore/data/events/*.json` | einzelne Veranstaltungen |
| `/var/lib/livescore/data/imports/*.json` | gespeicherte Importdateien als Grundlage für „Zurücksetzen“ |
| `/var/lib/livescore/data/active-event.json` | aktive Veranstaltung und Auswahlkennung |
| `/var/lib/livescore/backups/` | Sicherung von Config/Auth und Daten vor jedem tatsächlich ausgeführten Upgrade |
| `/etc/systemd/system/livescore.service` | Systemdienst mit eigenem Konto `livescore` |

Die Betriebsverzeichnisse erhalten `.livescore-managed` als Herkunftsmarkierung.
Unbekannte belegte Installationspfade, fremde CLI-/Unit-Dateien und Symlinks in
Config-/Datenverzeichnissen werden abgewiesen. Das Dienstkonto hat keine Login-Shell.
Der Programmcode gehört root; nur Config/Auth und Laufdaten sind für den Dienst
schreibbar. Die Unit begrenzt Schreibzugriff auf diese Verzeichnisse.

Die Installation liest `imports/prague-2026.json`, validiert das State-Modell
und erzeugt bei fehlenden Veranstaltungsdaten `events/prague-2026.json` sowie
den Auswahlzeiger auf `prague-2026`. Mitgeliefert sind 6 Participants samt Ländern,
6 Referees, 14 Matches mit je 3 Officials, zwei Halbzeiten und der generische
Teamfoul-Counter (Warnung bei 4, Critical/Double Penalty ab 5).
Keine automatische Sportregel-, Tabellen- oder Play-off-Logik.

Vorhandene Eventdateien, Legacy-Dateien, ein leerer gespeicherter Auswahlzeiger
oder unbekannte Dateien verhindern den Seed. Allein liegengebliebene `.lock`-Dateien
sind keine Veranstaltungsdaten. Normale Serverstarts führen keinen Seed aus;
Upgrades ebenfalls nicht. `examples/prague-2026.json` ist dieselbe portable
Veranstaltung für Import/Export und Tests. Der Installer verwendet ausschließlich
die Datei unter `imports/` als Seed-Quelle.

Die Abschlussmeldung nennt Version, URL und Pfade. Standardzugriff:

- Web: `http://HOST:8730/`
- öffentliche Live-API: `http://HOST:8730/api/v1/live`
- öffentliche Version: `http://HOST:8730/api/version`

Die [erste Anmeldung und Passwortverwaltung](#benutzer-und-passwörter) erfolgt
im Browser. EN ist Default, DE und CS sind im Header wählbar.
Die Version erscheint im Footer.

## Manueller Start unter Linux und Windows

Voraussetzung ist Python 3.12 oder neuer mit `venv` und `pip`. Zuerst das
Repository klonen und in dessen Verzeichnis wechseln:

```sh
git clone https://github.com/richtertoralf/LiveScore.git
cd LiveScore
```

Unter Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m livescore
```

Unter Windows in PowerShell (`py -3 --version` muss mindestens 3.12 anzeigen):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m livescore
```

Der Server läuft im Vordergrund, ohne einen Dienst zu installieren.
Die Oberfläche liegt unter `http://localhost:8730/`; von anderen Geräten aus
den Servernamen oder seine IP-Adresse verwenden. Ohne vorhandene Daten beginnt
der manuelle Start mit einem leeren Veranstaltungskatalog. Die Prag-Datei kann
über `/events` importiert und anschließend ausgewählt werden.

## Serverkonfiguration

Im Checkout verwendet LiveScore `config/livescore.yml`, der Linux-Dienst
`/etc/livescore/livescore.yml`. Beispiel für den Checkout:

```yaml
bind_host: 0.0.0.0
port: 8730
data_dir: ../data
auth:
  enabled: true
  file: auth.yml
  session_hours: 12
  secure_cookie: false
```

| Einstellung | Bedeutung |
|---|---|
| `bind_host` | `0.0.0.0` für Zugriff über Netzwerkschnittstellen, `127.0.0.1` nur lokal |
| `port` | freier TCP-Port von 1 bis 65535; Standard `8730` für Oberfläche und API |
| `data_dir` | Veranstaltungsdateien und aktive Auswahl; installiert: `/var/lib/livescore/data` |
| `auth.enabled` | Login für Bedienung und Verwaltung; Standard `true` |
| `auth.file` | Passwortdatei; installiert: `/etc/livescore/auth.yml` |
| `auth.session_hours` | Session-Laufzeit ab Login; Standard 12 Stunden |
| `auth.secure_cookie` | `true` bei HTTPS; für lokalen HTTP-Zugriff `false` |

Relative Daten- und Auth-Pfade beziehen sich auf das Verzeichnis der Config-Datei,
nicht auf das Arbeitsverzeichnis. Als Legacy-Option ist `data_file` statt `data_dir`
möglich; genau eine der beiden Optionen angeben. Das Elternverzeichnis der
Legacy-Datei wird das Datenverzeichnis. [Migration und Dateiformat](DATA_MODEL.md#dateien-und-migration).

Eine eigene Config kann beim manuellen Start angegeben werden:

```sh
.venv/bin/python -m livescore --config config/local.yml
```

Genau einen Serverprozess pro Datenverzeichnis starten. Separate Instanzen
benötigen getrennte Daten- und Auth-Dateien sowie Ports. JSON-Dateien nur bei
beendetem Server manuell bearbeiten. Ungültige Konfiguration oder beschädigte
vorhandene Daten führen zum Startabbruch und werden nicht durch Standarddaten ersetzt.

Für die Installation `/etc/livescore/livescore.yml` bearbeiten, danach:

```sh
sudo systemctl restart livescore
sudo journalctl -u livescore -n 100 --no-pager
```

Dieser Restart übernimmt Änderungen an der Serverkonfiguration.
Für [Passwort-Recovery](#admin-passwort-vergessen) ist kein Neustart nötig.

Host und Port sind frei konfigurierbar. Der Installer unterstützt Datenpfade
innerhalb `/var/lib/livescore/data` und Auth-Pfade innerhalb `/etc/livescore`.
Andere Pfade sind beim manuellen Checkout-Betrieb möglich, werden vom automatischen
Deployment aber abgewiesen, damit Backup, Rechtevergabe und Uninstall keine
beliebigen fremden Verzeichnisse betreffen.

Ein vorhandener Checkout mit lokalen Daten wird nicht automatisch verschoben.
Für eine Übernahme den bisherigen Prozess kontrolliert beenden, die neue
Installation stoppen, vorhandene Config passend übertragen und Event-Verzeichnis
samt Auswahlzeiger sowie Auth-Datei gesichert übernehmen. Pfade anpassen und
Dateien dem Dienstkonto `livescore` zuordnen. Erst nach Prüfung starten; die alten
Originale als Backup behalten. Diese Übernahme wird nicht durch einen Reinstall
erzwungen. Niemals zwei Prozesse auf dasselbe Datenverzeichnis starten.

`livescore` ohne Option startet den Server im Vordergrund; bei laufendem Dienst
verhindert die Prozesssperre eine zweite Instanz. Für normale Bedienung den
Systemdienst verwenden. `livescore --config PFAD` ermöglicht einen ausdrücklich
separaten manuellen Betrieb. `python -m livescore --version` funktioniert in der
venv ebenfalls; beide CLI-Varianten und die Web-API lesen `VERSION`.

### HTTPS

Vor Internetfreigabe beide Startpasswörter ändern, HTTPS über einen Reverse Proxy
einrichten und `auth.secure_cookie: true` setzen. Nur den HTTPS-Zugang öffentlich
erreichbar machen; den LiveScore-Port nicht direkt freigeben.
Bei einem Proxy auf demselben Rechner kann LiveScore an `127.0.0.1` gebunden werden.

Der Proxy muss den öffentlichen `Host` erhalten und WebSocket-Upgrades weiterleiten,
damit Browser-Origin und Host übereinstimmen. Uvicorn vertraut keinen
Forwarded-Headers; die Cookie-Sicherheit wird ausdrücklich konfiguriert.
Bei getrennten Maschinen auch die Verbindung zum Backend absichern.
TLS, Zertifikate und Firewall richtet der Betreiber ein.

## Benutzer und Passwörter

| Benutzer | Startpasswort | Berechtigung |
|---|---|---|
| `operator` | `operator` | Bestehende Veranstaltungsdetails bearbeiten, auswählen, exportieren und Spiele bedienen |
| `admin` | `admin` | zusätzlich Passwörter verwalten und Veranstaltungen zurücksetzen/ersetzen |

Beim ersten Admin-Login führt LiveScore zu `/users`. Zuerst das eigene Passwort
ändern, danach das Operator-Passwort setzen. Neue Passwörter müssen 12–1024 Zeichen
lang sein und werden zweimal eingegeben. Das alte Passwort ist nicht erforderlich.
Operatoren ändern ihr Passwort über den Admin. Weitere Benutzer oder Rollen
können nicht angelegt werden.

Passwortänderungen melden alle Sessions des betroffenen Accounts ab.
Ein Serverneustart beendet alle Sessions, erhält aber Passwörter und Veranstaltungsdaten.
Die Passwortdatei enthält scrypt-Hashes und wird beim ersten Start angelegt;
sie nicht von Hand bearbeiten. Im Checkout liegt sie unter `config/auth.yml`.
Fehlende oder ungültige Accounts in einer vorhandenen Datei führen zum Startabbruch,
nicht zum Zurücksetzen auf Startpasswörter.

Die Live-Daten unter `GET /api/v1/live` bleiben öffentlich lesbar.
Die übrigen fachlichen APIs und der WebSocket verlangen bei aktiviertem Auth
eine Anmeldung. `/docs`, `/redoc` und `/openapi.json` sind Admin-only.
Details zur Anmeldung eigener Clients stehen in der [API](API.md#anmeldung-eigener-clients).
Bei ausdrücklich deaktiviertem Auth sind Fachfunktionen ohne Login verfügbar,
die Passwortverwaltung ist deaktiviert.

Sportprofile sowie Anlegen und Importieren von Veranstaltungen sind Admin-Aufgaben.
Die Profilbibliothek liegt in `data_dir/sport-profiles.json` und ist in den vorhandenen
Daten-Backups und Upgrade-Sicherungen enthalten. **Version 0.2.2** kann über
`sudo livescore --upgrade` von GitHub/main installiert werden. Die sieben
Standardprofile erscheinen automatisch in **Konfiguration → Sportprofile**;
bestehende Veranstaltungsprofile und Administratoränderungen bleiben erhalten.
Es ist kein zusätzlicher Importbefehl nötig. Vorhandene Veranstaltungsdateien benötigen
keine manuelle Migration. Externe Anwendungen müssen die [aktuelle Live-API](API.md)
mit Anzeigevorgaben und nullable Werten berücksichtigen.

### Admin-Passwort vergessen

Auf dem Linux-Dienstrechner:

```sh
sudo livescore --reset-admin-password
```

Das neue Passwort wird zweimal verdeckt abgefragt. Die CLI speichert es atomar
in der vorhandenen gültigen Auth-Datei und fordert beim passenden laufenden
systemd-Dienst einen Auth-Reload an. Der Reload lädt nur Passwörter neu;
Operator-Sessions, WebSockets und Live-Daten bleiben erhalten.
Das Dienstlog bestätigt den asynchronen Reload:

```sh
sudo journalctl -u livescore -n 100 --no-pager
```

Ohne laufenden systemd-Dienst wird das Passwort ebenfalls gespeichert.
Ein laufender Standalone-Prozess unter Linux/Unix benötigt anschließend
`kill -HUP <geprüfte-LiveScore-PID>`; sonst gilt die Änderung beim nächsten Start.
Im Checkout die passende Config verwenden:

```sh
.venv/bin/python -m livescore --config config/local.yml --reset-admin-password
```

Ungültige neue Auth-Daten werden beim Reload abgewiesen; bisherige Credentials
bleiben im Speicher aktiv. Bei älteren Prozessen ohne SIGHUP-Unterstützung oder
einem fehlgeschlagenen Reload kann das Passwort bereits gespeichert sein,
obwohl die CLI einen Fehler meldet. Erst Dienstlog und Prozessstand prüfen;
nicht blind erneut zurücksetzen. Beide Passwörter vergessen: zuerst Admin per CLI,
anschließend Operator unter `/users` neu setzen.

## Upgrade

```sh
sudo livescore --upgrade
# Alternativ eine zuvor geprüfte lokale Quelle:
sudo livescore --upgrade --source /pfad/zum/LiveScore-Checkout
```

Das Upgrade lädt `main` aus dem festen öffentlichen GitHub-Repository ohne
Anmeldung in ein temporäres Verzeichnis innerhalb der Installation
(siehe [GitHub-Zugang](#github-zugang-öffentliches-repository)).
Mit `--source` wird stattdessen ein lokaler Checkout verwendet. Es führt keinen Git-Pull in lokalen
Betreiberdaten aus und benötigt keinen Git-Checkout in der installierten Laufzeit.
Version und Commit werden verglichen: Bei gleicher Version und gleichem
sauberem Commit meldet es „bereits aktuell“ und ändert nichts, ohne Neubau,
Sicherung oder Neustart. Ein neuer Commit derselben Versionsnummer wird
installiert; Versionsrückschritte werden abgewiesen. Commit, Branch und Quelle
stehen in `installation.json` der Laufzeit; `livescore --version` zeigt sie.
Von 0.2.2 und älter läuft das Upgrade noch mit dem alten Installer ohne
Commit; das nächste Upgrade ergänzt ihn einmalig.

Ablauf:

1. Installierte Version und Zielversion nennen; Installation exklusiv sperren.
2. Neue Programmdateien und neue venv neben der bisherigen Laufzeit anlegen.
3. Requirements installieren, `pip check`, Python-Kompilation und Seedvalidierung.
4. Vorhandene Config/Auth/Eventdateien lesend validieren. Fehlende Auth-Datei bei
   aktiviertem Auth führt zum Abbruch, statt neue Startpasswörter zu erzeugen.
5. Eigenen Dienst stoppen und Config/Auth sowie alle Veranstaltungsdaten sichern.
6. `current` atomar umschalten, Unit aktualisieren, einen zuvor laufenden Dienst neu
   starten und öffentliche Versionsantwort sowie systemd-Status prüfen. Ein gestoppter
   Dienst bleibt gestoppt.
7. Bei Fehlern nach dem Umschalten zur bisherigen Laufzeit/Unit zurückkehren und
   einen zuvor laufenden Dienst wieder starten. Config/Auth/Eventdaten werden nicht
   durch alte Sicherungen überschrieben.

Der letzte vorherige Programmstand bleibt zusätzlich unter `releases/` erhalten;
ältere Programmlaufzeiten werden nach erfolgreichem Upgrade entfernt. Backups unter
`/var/lib/livescore/backups` bleiben erhalten; sie enthalten vertrauliche
Passworthashes und sollten regelmäßig extern gesichert und kontrolliert bereinigt
werden. Ein manueller Code-Rollback erfordert einen gestoppten Dienst und das
Zurücksetzen des `current`-Links auf den vorherigen Laufzeitpfad.

Lokale Config wird nicht ersetzt. Auth-Hashes, Passwörter, Eventdateien, aktive
Auswahl, Scores, Fouls und Officials bleiben erhalten. Es gibt keine zusätzliche
Datenmigration. Ein Neustart beendet wie bisher alle Browser-Sessions; danach
neu anmelden. Upgrades in einer geplanten Betriebspause durchführen.

Bei Stromverlust während eines Deployments bleiben die Programmlaufzeiten und
persistenten Daten separat erhalten; die atomare Umschaltung ist kein Ersatz für
Backups. Nach einem unterbrochenen Vorgang `current`, Config und Dienststatus
prüfen und gegebenenfalls den letzten Programmstand aktivieren.

## Backup

Für eine vollständige Sicherung den Server kontrolliert beenden und das gesamte
Datenverzeichnis mit `events/`, `imports/` und `active-event.json` kopieren.
Serverkonfiguration und Auth-Datei ebenfalls sichern. Bei der Dienstinstallation
sind dies `/var/lib/livescore/data` und `/etc/livescore`. Lock-Dateien sind keine
Nutzdaten. Die Auth-Datei und Upgrade-Backups enthalten vertrauliche Passworthashes.

Ein JSON-Export im Browser ist ein konsistenter Snapshot einer einzelnen Veranstaltung
und kann auf einer anderen Instanz importiert werden. Er enthält keine Passwörter,
keine gespeicherte Reset-Grundlage und keinen Auswahlzeiger. Separate Exporte
sind kein zeitgleicher Gesamtsnapshot des Datenverzeichnisses.

Für eine Wiederherstellung den Server stoppen, die gesicherten Dateien an ihre
konfigurierten Pfade zurückkopieren und bei einer Dienstinstallation den Zugriff
des Kontos `livescore` auf Config/Auth und Daten sicherstellen. Danach starten und
aktive Veranstaltung sowie Live-Zustand prüfen.

## Deinstallation

```sh
sudo /opt/livescore/current/uninstall.sh
# Alternativ aus dem Checkout:
sudo ./uninstall.sh
```

Entfernt ausschließlich LiveScore-Unit, CLI und Programmlaufzeiten inklusive venv.
**Config, Auth, Veranstaltungsdaten, Backups und das Dienstkonto bleiben erhalten.**
Eine spätere Installation übernimmt diese Daten, ohne Veranstaltungen oder
Passwörter zurückzusetzen. Ein normaler Reinstall bei noch installiertem Programm
bricht kontrolliert mit Verweis auf `livescore --upgrade` ab.

Nur wenn auch alle lokalen Daten und Passwörter ausdrücklich gelöscht werden sollen:

```sh
sudo ./uninstall.sh --purge
```

`--purge` ist die ausdrückliche Löschbestätigung; es entfernt auch `/etc/livescore`
und `/var/lib/livescore` samt Backups. Nach normalem Uninstall diesen Befehl aus
dem Checkout ausführen, da die installierte Programmdatei dann fehlt. Das gesperrte
Dienstkonto bleibt auch bei Purge bestehen; keine fremden Konten werden verändert.

## Isolierte Verifikation

```sh
./install.sh --staging-root "$PWD/.test-artifacts/manual-install"
.test-artifacts/manual-install/usr/local/bin/livescore --version
.test-artifacts/manual-install/usr/local/bin/livescore --upgrade --source "$PWD"
./uninstall.sh --staging-root "$PWD/.test-artifacts/manual-install"
.venv/bin/python tests/deployment_smoke.py
.venv/bin/python tests/auth_recovery_smoke.py
```

Staging bildet alle Installationspfade unter dem angegebenen Root ab. Es erstellt
keine Systemkonten, ruft kein systemctl auf und startet keinen Dienst. CLI und
venv sind echt; ein manueller Teststart benötigt einen freien, ausdrücklich in
der Staging-Config gewählten Port. Der Staging-Pfad wird in der installierten
CLI hinterlegt, damit Upgrade/Uninstall ebenfalls isoliert bleiben.

Der Deployment-Smoke erstellt echte venvs und installiert die Requirements,
startet ausschließlich eigene Loopback-Prozesse und prüft Fresh-Seed, geändertes
Admin-Passwort, Live-Score/Fouls, Upgrade, Restart, Reinstall-Abweisung,
Uninstall-Datenerhalt und Purge. Unit-Tests ergänzen Schreibfehler, Rollback,
Deployment-Lock, Fremdpfadschutz und Seed-Grenzfälle sowie mit einem Fake-`git`
den öffentlichen Download ohne Passwortabfrage, Fehlerbehandlung und das Löschen
des Download-Verzeichnisses. `tests/deployment_smoke.py --remote-upgrade` prüft den
Download von GitHub/main ohne Anmeldung. Browser-Smokes prüfen die
Version auf allen fünf Seiten und EN/DE/CS sowie die bisherigen Bedienabläufe.

Auf codex-dev werden diese Tests nur unter `.test-artifacts/` ausgeführt.
Der Recovery-Smoke hält ein echtes Live-Spiel mit Score, Fouls und zweiter Periode
aktiv, verwendet echte verdeckte PTY-Eingabe und sendet echtes SIGHUP an denselben
Server-PID. Ein isolierter `systemctl`-Stub führt den mitgelieferten ExecReload-Befehl
aus; er kontaktiert niemals Host-systemd. Währenddessen werden Live-GETs fortlaufend
geprüft sowie bestehende Operator-Session und WebSocket beibehalten. Die Auth-Tests
prüfen zusätzlich parallele Web-/CLI-Transaktionen, veraltete Admin-Requests,
Dateifehler und ungültigen Reload ohne Verlust der funktionierenden Credentials.
Ein echter systemweiter Installations-/systemd-Test wurde dort nicht ausgeführt;
die bestehende Instanz und andere Dienste bleiben unberührt.
