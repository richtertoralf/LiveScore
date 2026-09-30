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

## GitHub-Zugang (privates Repository)

`richtertoralf/LiveScore` ist privat. Benötigt werden ein GitHub-Username und ein
Token mit **Leserecht auf das Repository** (Fine-grained Token mit
„Contents: Read-only“ oder klassischer Token mit `repo`). Da auf wechselnden Rechnern
installiert wird, **speichert LiveScore keine Zugangsdaten**.

`livescore --install` und `livescore --upgrade` ohne `--source` fragen bei jedem
Aufruf interaktiv `GitHub-Username` und `GitHub-Token` ab (Token unsichtbar per
`getpass`). Der Klon läuft per HTTPS mit `git -c credential.helper= clone`, damit
kein Credential-Helper den Token ablegt. Die Werte gelangen nur als
Umgebungsvariablen an den git-Prozess und werden über ein temporäres
`GIT_ASKPASS`-Hilfsskript abgefragt, das danach gelöscht wird; der Token steht nie
in der URL, in Kommandozeilenargumenten oder Fehlermeldungen. `GIT_TERMINAL_PROMPT=0`
bleibt gesetzt, Git fragt also nicht selbst nach. Das temporäre Download-Verzeichnis
unter `/opt/livescore/.download-*` wird in jedem Fall entfernt.

Bei abgelehntem Zugriff (git-Exitcode 128) erscheint:
„Anmeldung fehlgeschlagen – Username/Token prüfen, Token braucht Leserecht auf
richtertoralf/LiveScore“. Andere Git-Fehler melden nur ihren Exitcode; Gits eigene
Ausgabe darüber (z. B. Netzwerkfehler) enthält keine Zugangsdaten. Ob Installation
bzw. Upgrade überhaupt möglich ist, wird vor der Abfrage geprüft.

## Erstinstallation

Aus einem Checkout: Beim ersten Klonen fragt Git selbst nach Username und Token
(Token als Passwort eingeben). `-c credential.helper=` verhindert auch hier, dass
ein eventuell konfigurierter Helper den Token speichert.

```sh
git -c credential.helper= clone https://github.com/richtertoralf/LiveScore.git
cd LiveScore
sudo ./install.sh
livescore --version
systemctl status livescore
```

`install.sh` installiert den lokalen Checkout ohne weitere Abfrage. Alternativ lädt
`sudo ./bin/livescore --install` den aktuellen Stand von GitHub/main mit der oben
beschriebenen Username-/Token-Abfrage.

| Pfad | Inhalt |
|---|---|
| `/opt/livescore/releases/<Laufzeit>/` | Programmcode, VERSION, mitgelieferte Prag-Dateien, eigene `.venv` |
| `/opt/livescore/current` | atomar wechselnder Link auf die aktuelle Laufzeit |
| `/usr/local/bin/livescore` | Link zum CLI-Wrapper der aktuellen Laufzeit |
| `/etc/livescore/livescore.yml` | lokale Serverkonfiguration |
| `/etc/livescore/auth.yml` | lokale scrypt-Passworthashes; entsteht beim ersten Serverstart |
| `/var/lib/livescore/data/events/*.json` | einzelne Veranstaltungen |
| `/var/lib/livescore/data/active-event.json` | aktive Veranstaltung und Auswahlkennung |
| `/var/lib/livescore/backups/` | Sicherung von Config/Auth und Daten vor jedem Upgrade |
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

Initial credentials: **admin / admin**, **operator / operator**.
**Diese Passwörter vor Internetfreigabe ändern. HTTPS ist zwingend erforderlich.**
Operator verwaltet alle fachlichen Veranstaltungs- und Live-Daten; Admin zusätzlich
Benutzer/Passwörter. Der erste Admin-Login erzwingt dessen Passwortänderung.
EN ist Default, DE und CS sind im Header wählbar. Die Version erscheint im Footer.

## Konfiguration und manueller Betrieb

Für die Installation `/etc/livescore/livescore.yml` bearbeiten, danach:

```sh
sudo systemctl restart livescore
sudo journalctl -u livescore -n 100 --no-pager
```

Dieser Restart gilt für Änderungen an Server-Host/Port, nicht für Passwort-Recovery.
Für ein vergessenes Admin-Passwort während einer Veranstaltung:

```sh
sudo livescore --reset-admin-password
# Auth-Datei auch unabhängig von Recovery erneut einlesen:
sudo systemctl reload livescore
```

`ExecReload=/bin/kill -HUP $MAINPID` lädt ausschließlich Auth neu, ohne Prozesswechsel.
Admin-Recovery erhält Operator-Sessions/WebSockets und sämtliche Live-Daten.
Ungültige Credentials werden abgewiesen, der bisherige RAM-Stand bleibt aktiv.
Die CLI speichert atomar unter demselben kurzen Lock wie die Web-Passwortverwaltung
und übernimmt den bisherigen Dateieigentümer. Kein Stop/Start/Restart im Recovery-Pfad.
Der automatisch angeforderte Reload wird im Dienstlog bestätigt; die CLI wartet
nicht auf eine fachliche Bestätigung des asynchronen Signalhandlers.
Ohne passenden laufenden systemd-Dienst meldet sie den erforderlichen manuellen
Auth-Reload beziehungsweise das Laden beim nächsten normalen Start.
Details und Verhalten älterer Prozesse: [README – Recovery](../README.md#admin-passwort-vergessen-recovery-ohne-downtime).

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

## Upgrade

```sh
sudo livescore --upgrade
# Alternativ eine zuvor geprüfte lokale Quelle:
sudo livescore --upgrade --source /pfad/zum/LiveScore-Checkout
```

Das Upgrade fragt GitHub-Username und Token ab (siehe
[GitHub-Zugang](#github-zugang-privates-repository)) und lädt `main` aus dem festen
GitHub-Repository in ein temporäres Verzeichnis innerhalb der Installation.
Mit `--source` entfällt die Abfrage. Es führt keinen Git-Pull in lokalen
Betreiberdaten aus und benötigt keinen Git-Checkout in der installierten Laufzeit.
Es kann auch einen ergänzten Stand derselben Versionsnummer installieren;
Versionsrückschritte werden abgewiesen.

Ablauf:

1. Installierte Version und Zielversion nennen; Installation exklusiv sperren.
2. Neue Programmdateien und neue venv neben der bisherigen Laufzeit anlegen.
3. Requirements installieren, `pip check`, Python-Kompilation und Seedvalidierung.
4. Vorhandene Config/Auth/Eventdateien lesend validieren. Fehlende Auth-Datei bei
   aktiviertem Auth führt zum Abbruch, statt neue Startpasswörter zu erzeugen.
5. Eigenen Dienst stoppen und Config/Auth sowie alle Veranstaltungsdaten sichern.
6. `current` atomar umschalten, Unit aktualisieren, Dienst neu starten und öffentliche
   Versionsantwort sowie systemd-Status prüfen.
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
die Zugangsdatenübergabe per `GIT_ASKPASS`, das Löschen von Hilfsskript und
Download-Verzeichnis und tokenfreie Fehlermeldungen. `tests/deployment_smoke.py
--remote-upgrade` fragt entsprechend interaktiv nach Username und Token. Browser-Smokes prüfen die
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
