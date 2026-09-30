# LiveScore 0.1.0

Lokale Webanwendung zur einfachen Erfassung von Live-Spielständen bei Turnieren.
Zwei Parteien treten gegeneinander an: Mannschaften, Einzelpersonen oder andere
benannte Teilnehmer. Die Anwendung bleibt sportartenneutral und ist **keine
vollständige Turnierverwaltung**.

**Paarung bestätigen → Links/Rechts festlegen → Spiel starten → Score erfassen
→ Pause/Seitenwechsel → Ergebnis bestätigen → nächstes Spiel.**

Mehrere Veranstaltungen können lokal vorbereitet, importiert und gespeichert werden.
Genau eine davon ist für alle Bediener aktiv. Mit **LiveScore 0.1.0** sind Veranstaltungsdaten, Play Areas, Teilnehmer und Spielplan
manuell im Browser erfassbar und bearbeitbar. Zwei oder mehr Bediener
sehen denselben serverseitigen Zustand automatisch per WebSocket. Die externe
HTTP-API liefert den aktuellen Spielstand bereits für links und rechts aufbereitet.
Der Betrieb benötigt kein Internet, keine Datenbank und keinen externen Dienst.

Die zentrale Versionsnummer steht in `VERSION`. In der installierten Python-Umgebung
zeigt `python -m livescore --version` die Ausgabe `LiveScore 0.1.0`; der Befehl
startet keinen Server und verändert keine Konfiguration oder Veranstaltungsdaten.

## Installation und Start

### Linux-Dienst installieren

Auf Linux mit systemd, Python **3.12+**, `venv`, `pip` und Git:

Das Repository ist **privat**. Zum Klonen GitHub-Username und ein Token mit
Leserecht auf `richtertoralf/LiveScore` eingeben (Token als Passwort);
`-c credential.helper=` verhindert, dass der Token gespeichert wird:

```sh
git -c credential.helper= clone https://github.com/richtertoralf/LiveScore.git
cd LiveScore
sudo ./install.sh
livescore --version
systemctl status livescore
```

Der Installer erstellt `/opt/livescore` (Code und venv), `/etc/livescore`
(Server-Config und Auth) sowie `/var/lib/livescore/data` (Veranstaltungen).
`/usr/local/bin/livescore` stellt die CLI bereit. Der Dienst `livescore.service`
läuft als eigener Benutzer `livescore` und startet automatisch beim Booten.
Bei einer frischen Installation ist **Prag 2026 bereits aktiv ausgewählt**:
6 Teilnehmer, 6 Referees, 14 vorbereitete Spielplan-Einträge mit Officials und
Teamfoul-Profil. Nach Operator-Login kann sofort das erste Spiel vorbereitet werden.

Web: **http://HOST:8730/** · öffentliche API: **http://HOST:8730/api/v1/live**.
Initial: **admin / admin**, **operator / operator**.
**Vor Internetfreigabe beide Passwörter ändern und HTTPS verwenden.**

```sh
sudo livescore --upgrade
sudo /opt/livescore/current/uninstall.sh
# Nur bei ausdrücklich gewünschter Löschung aller Daten und Passwörter:
sudo ./uninstall.sh --purge
```

`sudo livescore --upgrade` und alternativ `sudo ./bin/livescore --install` fragen bei
jedem Aufruf GitHub-Username und Token interaktiv ab und speichern nichts: kein
Credential-Helper, kein Token in URL, Argumenten oder Fehlermeldungen. Bei
abgelehntem Zugriff erscheint „Anmeldung fehlgeschlagen – Username/Token prüfen,
Token braucht Leserecht auf richtertoralf/LiveScore“. Mit `--source PFAD` wird
stattdessen ein lokaler Checkout ohne Abfrage verwendet.

Upgrade lädt GitHub/main, baut zuerst eine neue venv, prüft die vorhandene Config,
sichert Config/Auth/Eventdaten und startet den Dienst mit der neuen Laufzeit.
Die Dateien und die aktive Veranstaltung bleiben erhalten. Fehler beim Start
führen zur Rückkehr zur bisherigen Laufzeit. Uninstall behält standardmäßig
Config, Passwörter, Veranstaltungsdaten und Backups. Ein erneuter `install.sh`-Lauf
bei vorhandener Laufzeit verweist kontrolliert auf `--upgrade`.
Details, Voraussetzungen, Fehlerbehandlung und isolierte Tests:
[docs/INSTALLATION.md](docs/INSTALLATION.md).

### Manuell aus dem Checkout starten

Voraussetzung: Python **3.12 oder neuer** mit `venv` und `pip`.
Unter Linux im Repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m livescore
```

Unter Windows in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m livescore
```

Veranstaltungen: **http://localhost:8730/events** ·
Bedienung: **http://localhost:8730/** · Konfiguration:
**http://localhost:8730/config** · API: **http://localhost:8730/api/v1/live**.
Im Veranstaltungsnetz `localhost` durch die Serveradresse ersetzen, beispielsweise
`http://10.77.0.108:8730/` auf codex-dev, solange LiveScore dort gestartet ist.

Dependencies müssen einmal installiert werden; die laufende Anwendung und die
Browseroberfläche benötigen keine externen Ressourcen. Alle CSS-/JS-Dateien liegen
lokal. Die Oberfläche startet auf **Englisch**, mit Umschaltung **EN / DE / CS**
im Header. Zwei lokale Accounts schützen die Bedienung. Für Internetzugriff sind
HTTPS und geänderte Startpasswörter erforderlich.

### Konfiguration

`config/livescore.yml` ist die zentrale Serverkonfiguration im Checkout.
Die Linux-Installation verwendet `/etc/livescore/livescore.yml` mit
`data_dir: /var/lib/livescore/data`. Relative Pfade bleiben möglich:

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

- `bind_host`: `0.0.0.0` erlaubt Zugriff über die Netzwerkschnittstellen;
  `127.0.0.1` beschränkt ihn auf den eigenen Rechner.
- `port`: gültiger TCP-Port von 1 bis 65535. Default **8730**.
- `data_dir`: Datenverzeichnis mit einzelnen Veranstaltungsdateien und aktiver
  Auswahl. Relative Pfade beziehen sich **auf das Verzeichnis der Config-Datei**,
  unabhängig vom Arbeitsverzeichnis.
- Alternativ bleibt die bisherige Option `data_file` für Single-Event-Installationen gültig:
  Ihr Elternverzeichnis wird zum `data_dir`, die bezeichnete Datei zur Legacy-Quelle.
  In der YAML-Datei genau eine der Optionen angeben. Mehrere unabhängige Instanzen
  benötigen getrennte Datenverzeichnisse und Ports.

Eigene Konfiguration, zum Beispiel `config/local.yml`:

```sh
.venv/bin/python -m livescore --config config/local.yml
```

Ungültige Config oder beschädigte vorhandene Veranstaltungs-/Auswahldateien
brechen den Start ab. Bestehende Daten werden niemals durch leere Standarddaten
ersetzt. Beim manuellen Start ohne vorhandene Daten entsteht ein leerer Katalog.
Nur der Installer initialisiert bei fehlenden Veranstaltungsdaten den Prag-Seed.
`data/` ist von Git ausgeschlossen.

**Genau ein Serverprozess pro Datenverzeichnis.** Ein Uvicorn-Worker und eine
Betriebssystem-Sperre in `active-event.json.lock` schützen den gesamten Katalog.
Zusätzlich wird die bisherige Legacy-Datei gesperrt, damit nicht gleichzeitig ein
Single-Event-Prozess darauf arbeitet. Lock-Dateien dürfen liegen bleiben; ihre Sperren
werden auch bei Prozessabbruch freigegeben. Keine weiteren Worker oder parallelen
Writer starten. JSON-Dateien nur bei beendetem Server manuell bearbeiten.

`systemd/livescore.service` ist die vom Linux-Installer verwendete System-Unit.
Beim manuellen Start wird kein Dienst installiert. Im lokalen Netz ist kein Reverse Proxy erforderlich; Internetzugriff
benötigt HTTPS wie unten beschrieben.

## Sprache und lokale Benutzer

**EN ist der Default**, unabhängig von der Browsersprache. EN/DE/CS im Header
speichert die Auswahl unter `livescore-language` in `localStorage` und lädt die
Seite neu; ungespeicherte Formulare vorher speichern. Ohne Browser-Speicher gilt
beim nächsten Laden wieder Englisch. Fehlende Übersetzungen fallen auf Englisch
zurück. Alle UI-Texte liegen zentral in `static/i18n.js`; HTML verwendet
`data-i18n`, dynamische Anzeigen `t()`. Keine Sprachkopien der Seiten und keine
Sprache im Event-State. Namen und frei eingegebene Texte bleiben erhalten;
bekannte Standardbegriffe wie „Halbzeit“, „Tore“ und die Prag-Warntexte werden
bei der Anzeige übersetzt. Technische API-Feldnamen bleiben unverändert.

Auf `/`, `/events`, `/config`, `/users` und `/login` zeigt ein unauffälliger Footer
**LiveScore v0.1.0**. Die öffentliche `GET /api/version` liefert dafür
`{"version":"0.1.0"}` aus derselben `VERSION`-Datei wie Python und CLI.
Die Anzeige bleibt in allen drei Sprachen gleich.

Bei aktiviertem Schutz führt `/` zunächst zu **/login**. Initial credentials:

| Benutzer | Startpasswort | Rolle |
|---|---|---|
| `admin` | `admin` | Administration |
| `operator` | `operator` | Fachliche Vollberechtigung |

**Diese Passwörter vor Internetfreigabe ändern. HTTPS ist zwingend erforderlich.**

Genau diese zwei Namen und Rollen sind fest. Beim ersten Start mit Auth entsteht
`config/auth.yml` (Linux-Installation: `/etc/livescore/auth.yml`) mit individuellen
scrypt-Hashes, niemals Klartextpasswörtern.
`auth.file` wird relativ zur Server-Config aufgelöst. Eine vorhandene ungültige
Datei führt zum Startabbruch und wird nicht zurückgesetzt. Auth-Datei und Lock
sind in `.gitignore`; andere selbst gewählte Secret-Pfade nicht versionieren.
`config/auth.example.yml` zeigt nur Platzhalter; nicht als echte Config kopieren.

Der Admin wird beim Erstlogin zu **Users / Benutzer / /users** geführt und muss
zuerst sein eigenes Startpasswort ändern. Bis dahin bleiben normale Admin-APIs
und State-WebSockets gesperrt. Danach kann er dort beide Passwörter setzen,
ohne das bisherige Passwort zu kennen. Neues Passwort zweimal eingeben:
**12–1024 Zeichen**, ohne automatische Änderung von Leerzeichen. Der Server prüft
Übereinstimmung, erstellt einen neuen Hash und setzt `default_password: false`.
Alle Sessions des betroffenen Accounts werden ungültig, auch die eigene
Admin-Session. Ein erneuter Login ist erforderlich. Eigene Passwortänderungen
durch Operator sind nicht implementiert; dafür den Admin verwenden.

Solange ein Standardpasswort aktiv ist, zeigt die Admin-UI:
„Default credentials are active. Do not expose this LiveScore instance to the
Internet.“ Die Benutzerseite markiert betroffene Accounts zusätzlich mit
„DEFAULT PASSWORD ACTIVE“. Lokal funktioniert der Operator zunächst mit seinem Startpasswort. Erst nach Änderung beider Passwörter verschwindet die Warnung.

| Berechtigung | operator | admin |
|---|---|---|
| Alle fachlichen Veranstaltungs- und Live-Daten lesen/bearbeiten | ja | ja |
| Events anlegen/auswählen, Namen/Daten und Sportprofil ändern | ja | ja |
| Participants, Referees und Matches anlegen/bearbeiten, Import/Export | ja | ja |
| Paarung, L/R, Score, Counter, Perioden, Pause/Resume, Finish | ja | ja |
| Benutzer-/Passwortverwaltung und Sicherheitsparameter | nein | ja |
| `/docs`, `/redoc`, `/openapi.json` | nein | ja |

**operator = fachliche Vollberechtigung. admin = fachliche Vollberechtigung plus
Sicherheits-/Benutzerverwaltung.** Die bestehenden Fachregeln gelten für beide:
Konfiguration bleibt während vorbereiteter/laufender Spiele gesperrt, Ergebnisse
und Counter bleiben an Teilnehmer gebunden. Sicherheitsparameter werden weiterhin
in der lokalen Server-Config gepflegt; es gibt dafür keine neue Webmaske.

Rechte werden **serverseitig** geprüft. Ohne Login liefern geschützte APIs **401**,
fehlende Rechte **403**. Die einzige öffentliche fachliche API ist
`GET /api/v1/live`. `/`, `/events`, `/config` und WebSocket benötigen Login.
`/users` und Passwort-APIs sind Admin-only. Login und notwendige statische Assets
sind öffentlich. Bei deaktiviertem Auth sind Fachfunktionen ohne Login verfügbar;
die Passwortverwaltung ist dann deaktiviert. Keine Benutzeranlage, Benutzerlöschung,
Passwort-Reset-Mail, OAuth, SSO, LDAP oder Datenbank.

Beim Start mit einer bereits vorhandenen Auth-Datei übernimmt LiveScore nur
`admin` und `operator` mit ihren unveränderten Passwort-Hashes und Default-Flags.
Nicht mehr benötigte Accounts und zusätzliche alte Auth-Einstellungen werden
entfernt. Erst nach erfolgreicher Validierung wird die reduzierte Datei unter der
OS-Sperre atomar gespeichert. Fehlt einer der beiden Accounts oder ist sein Hash
ungültig, bricht der Start ohne Überschreiben ab. Bestehende Passwörter werden
niemals auf Startwerte zurückgesetzt. Laufende Instanzen benötigen einen Neustart,
damit die neue Rollenlogik und die Dateibereinigung wirksam werden.

### Hashes, Sessions und CSRF

Passwort-Hash interaktiv erzeugen (kein Passwort als CLI-Argument):

```sh
.venv/bin/python -m livescore.auth hash-password
```

`getpass` liest das Passwort verdeckt und bestätigt es; stdout enthält nur den
Hash. Format: `scrypt$32768$8$3$<16-Byte-Salt-hex>$<32-Byte-Hash-hex>`.
`hashlib.scrypt` mit N=2¹⁵, r=8, p=3, zufälligen Salts und konstanten
Digest-Vergleichen benötigt keine zusätzliche Dependency. Diese Parameter sind
eine der [OWASP-scrypt-Varianten](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt);
Implementierung über die [Python-Standardbibliothek](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt).
Andere Parameterformate werden beim Laden abgewiesen. Bei manueller Änderung
die unten beschriebene Recovery verwenden; dafür ist kein Serverneustart nötig.

Die Auth-Datei wird unter einem Lock atomar mit Temp-Datei, Flush, fsync und
Replace gespeichert. Neue Dateien erhalten unter Linux Modus 0600. Eine
OS-Dateisperre in `auth.yml.lock` verhindert parallele Writer. Sie wird nur während
des tatsächlichen Lesens/Änderns/Schreibens gehalten, nicht für die Serverlaufzeit.
Web-UI und CLI verwenden dieselbe Sperre und lesen innerhalb der Transaktion
den neuesten Dateistand. Auth-Datei und Backups vertraulich
behandeln. Sie ist unabhängig von Event-JSON und Exporten; `schema_version`
bleibt 1, keine neue State-Migration.

### Admin-Passwort vergessen: Recovery ohne Downtime

```sh
sudo livescore --reset-admin-password
```

Das neue Passwort wird zweimal verdeckt mit `getpass` abgefragt (12–1024 Zeichen).
Kein Passwort als Argument oder Umgebungsvariable übergeben. Die bestehende
Auth-Datei muss gültig sein; Recovery erzeugt keine Ersatzaccounts. Es werden nur
`admin.password_hash` und dessen `default_password: false` gesetzt. Der Operator
bleibt unverändert. Atomarer Replace erhält auch bei `sudo` den Dateieigentümer
des Dienstkontos und die restriktiven Rechte.

Für den passenden laufenden systemd-Dienst löst die CLI anschließend automatisch
`systemctl reload livescore` aus. Die Unit sendet **SIGHUP**, ohne Stop/Start/Restart.
Der Prozess validiert ausschließlich die konfigurierte Auth-Datei und übernimmt
sie erst bei Erfolg. Alte Admin-Sessions werden ungültig; Operator-Sessions und
deren WebSockets bleiben bestehen. Veranstaltung, aktives Match, Scores, Fouls,
Perioden und die öffentliche Live-API bleiben unverändert verfügbar.

Die CLI meldet das **Anfordern** des Reloads; dessen asynchrone Validierung steht
im Dienstlog (`journalctl -u livescore`). Bei ungültiger oder fehlender neuer Datei
bleiben bisherige Credentials und Sessions im Speicher erhalten. Der Fehler wird
ohne Passwörter/Hashes geloggt. Ein SIGHUP mit unveränderten Credentials meldet
keine Benutzer ab. Ändert eine gültige Datei auch den Operator, werden ausschließlich
dessen betroffene Sessions zusätzlich entzogen.

Ohne laufenden systemd-Dienst wird das Passwort trotzdem gespeichert. Ein bereits
laufender Standalone-Prozess benötigt ausdrücklich **SIGHUP an seine geprüfte PID**;
andernfalls wird die Datei beim nächsten normalen Start geladen. Zum Beispiel:

```sh
.venv/bin/python -m livescore --config config/local.yml --reset-admin-password
kill -HUP <geprüfte-LiveScore-PID>
```

Die CLI prüft vor automatischem Reload den Config-Pfad, die verwaltete Unit, deren
reinen HUP-Reload-Befehl und ob der Prozess SIGHUP tatsächlich behandelt. Bei einer
älteren laufenden Version ohne Handler sendet sie **kein Signal** und fordert keinen
Neustart an; sie meldet den noch ausstehenden Reload mit Exitcode 1. Nach einem
Reload-Fehler ist das Passwort bereits auf Platte geändert; deshalb den Status
prüfen, statt blind erneut zurückzusetzen. SIGHUP-Recovery setzt Linux/Unix voraus.
Die erstmalige Bereitstellung dieser Funktion erfolgt im regulären Wartungsfenster;
ein schon laufender älterer Prozess bekommt neue Python-Funktionen nicht allein
durch einen Austausch der Quelldateien.

Sessions verwenden kryptografisch zufällige 256-Bit-Kennungen und liegen nur im
RAM. Cookies: `HttpOnly`, `SameSite=Lax`, `Secure` gemäß Config; Default-Laufzeit
12 Stunden ab Login, ohne gleitende Verlängerung. Neustart beendet alle Sessions,
erhält aber Passwort-Hashes. **Sign out / Abmelden** ruft `POST /logout` auf und
entfernt Session und Cookie. Passwörter und Session-/CSRF-Tokens werden nicht
geloggt oder in Eventdateien gespeichert. Falsche Passwörter und unbekannte
Benutzernamen erzeugen dieselbe Meldung. Maximal 30 Loginversuche je fünf Minuten
für die gesamte Instanz; KDF-Prüfungen laufen seriell außerhalb des ASGI-Loops.
Der globale Grenzwert funktioniert ohne Vertrauen in Proxy-IP-Header.

Bei aktiviertem Schutz benötigen alle Mutationen `X-CSRF-Token`, auch Logout und Passwortänderung.
`GET /api/auth/session` liefert dem Browser Rolleninformationen und sein
CSRF-Token, keine Passwort-Hashes. Vor Login liefert es eine zufällige
Login-Kennung mit HttpOnly-/SameSite=Strict-Cookie. `POST /login` benötigt
`username`, `password` und diese Kennung im Header. Origin wird, soweit
vorhanden, geprüft. State-WebSockets verlangen eine gültige Browser-Session und
einen passenden Origin. Ablauf, Logout und Passwortreset stoppen ihre weiteren
Updates, spätestens beim nächsten Heartbeat (normalerweise binnen fünf Sekunden).
Request-ID-, Event-Kontext- und Revisionsprüfungen bleiben zusätzlich bestehen.

`GET /api/auth/users` liefert dem Admin nur Namen, Rollen und Default-Flags.
`POST /api/auth/password` erwartet `username`, `password`, `repeat` und den
CSRF-Header; die Antwort meldet bei eigener Änderung `reauthenticate: true`.

### Öffentliche Live-API

**Live-Daten sind öffentlich lesbar**, auch bei `auth.enabled: true`:

```sh
curl --fail http://HOST:8730/api/v1/live
```

Die GFX benötigt ausschließlich die URL; keine Anmeldung, keine Cookies und
keine Zugangsdaten. Der Endpoint liefert den bestehenden aufbereiteten Live-State
mit Score, Seiten, Nationen, Officials samt Funktion, aktuellen Countern,
Spielperiode, Turnierphase und Runde. Er kann keine Daten ändern.
Alle anderen fachlichen GET-APIs, Exporte, sämtliche Mutationen und der WebSocket
bleiben bei aktiviertem Auth geschützt. Unauthentifizierte POSTs ergeben 401.

Für lokale Entwicklung kann ausdrücklich `auth.enabled: false` in einer eigenen
Server-Config gesetzt werden. Standardconfig und fehlende Auth-Optionen aktivieren
den Schutz der Weboberfläche. Die öffentliche Live-API ist davon unabhängig.

## Betrieb hinter HTTPS

**Benutzername, Passwort und Cookies niemals ohne TLS über das Internet
übertragen.** Vor Freigabe beide Startpasswörter ändern und
`auth.secure_cookie: true` setzen. Empfohlene Struktur:

```text
Internet → HTTPS → Reverse Proxy / TLS → LiveScore :8730
```

LiveScore kann weiterhin auf `0.0.0.0:8730` laufen. Nur der HTTPS-Zugang darf
öffentlich erreichbar sein; Backend-Port nicht direkt öffentlich freigeben.
Bei lokalem Proxy ist `bind_host: 127.0.0.1` möglich. Der Proxy muss den
öffentlichen `Host` erhalten und WebSocket-Upgrades weiterleiten, sodass
Browser-Origin und Host übereinstimmen. Uvicorn vertraut keinen Forwarded-Headers;
die Cookie-Sicherheit wird ausdrücklich konfiguriert. Bei getrennten Maschinen
auch die Proxy-/Backend-Verbindung absichern. Für lokale HTTP-Entwicklung bleibt
`secure_cookie: false` nötig. Es wurden keine Proxy-, Firewall-, Zertifikats-
oder systemweiten Serviceänderungen vorgenommen. TLS richtet der Betreiber ein.

### Warum Port 8730?

Die lesende Bestandsaufnahme auf codex-dev am 28./29.09.2026 ergab unter anderem
aktive Listener auf **8080** (MediaMTX Monitor) und **8720** (GFX-Engine).
**8081** ist in WinLaufen-Web und Richter Stream Pages vorgesehen, **8090** für
die WinLaufen-Bridge. **8730** war frei und ist in den geprüften Konfigurationen
nicht reserviert. Es ist vollständig konfigurierbar.
Weitere Listener und die übernommenen Projektmuster stehen in
[docs/REFERENZEN.md](docs/REFERENZEN.md).

## Beispielveranstaltung

`imports/prague-2026.json` enthält den bereitgestellten echten Spielplan des
„13th Cup of Central Europe Cities 2026“: **6 Teilnehmer, 6 Referees, 14 Spiele**,
jeweils **3 Officials** in vorgegebener Reihenfolge. Die Turnierphase stammt aus der
Spalte „Phase“ des Spielplans (`Gruppenphase` bzw. `Play-Offs`), die Runde aus der
Spalte „Gruppe“. `examples/prague-2026.json`
ist dieselbe Veranstaltung. Spätere Paarungen bleiben Platzhalter und werden
manuell gesetzt; es gibt keine automatische Tabellen- oder Play-off-Logik.
Teilnehmer enthalten die Ländercodes CZ, DE, KZ, GR, DE und DE. Das Sportprofil
`blind_football` / `IBSA 2025-2029` enthält die vom Veranstalter vorgegebenen
Teamfoul-Schwellen und zwei Halbzeiten. Alle Spiele beginnen in Periode 1 mit
Counterwerten null; bei offenen Paarungen werden die Teilnehmerwerte erst beim
Vorbereiten angelegt.

Die angelieferte Datei war mit `schema_version: 2` gekennzeichnet. Diese Kennzeichnung
wurde auf die weiterhin verwendete Version **1** korrigiert; es wurde keine
V1→V2- oder zusätzliche Legacy-Migration eingeführt. Der Name lautet
**Luis Ramon Pérez Macias**, ID `luis-ramon-perez-macias`.

Nach frischer Linux-Installation ist Prag bereits ausgewählt. Bei einem manuellen
Checkout-Start zum Ausprobieren `/events` öffnen, **JSON importieren** aufklappen und
`imports/prague-2026.json` oder die Beispieldatei auswählen. Die Vorschau nennt
6 Teilnehmer, 6 Referees, eine Play Area und 14 Spiele. Nach **Importieren**
und **Auswählen** ist die Veranstaltung bedienbar. Der Import selbst verändert
die Quelldatei nicht. Die Daten sind keine fest verdrahtete Produktlogik.

## Veranstaltungen verwalten

Auf **/events** werden gespeicherte Veranstaltungen mit Namen, Zeitraum, Ort und
Anzahl der Spiele angezeigt. **Auswählen** wechselt die Veranstaltung serverseitig
für alle Browser und alle bestehenden Live-/Konfigurations-APIs. Der Name der
aktiven Veranstaltung und der Weg zur Verwaltung sind auf `/` und `/config`
sichtbar. Ein Wechsel benötigt keinen zusätzlichen Bestätigungsdialog.

**+ Neue Veranstaltung** erfasst Name, Zeitraum, optional Ort und die
Score-Bezeichnung. Anlegen erzeugt eine eigene Datei, aktiviert sie aber nicht
automatisch. Anschließend auswählen und über die vorhandene `/config`-Seite
Play Areas, Teilnehmer, Referees und Spielplan pflegen. Änderungen an den Veranstaltungsdaten
unter `/config` bearbeiten nur die ausgewählte Veranstaltung.

Es bleibt bei **einer aktiven Veranstaltung und einem global ausgewählten Spiel**.
Ein Wechsel ist bei `idle`, `scheduled` und `finished` erlaubt. Solange das aktuelle
Spiel `ready`, `live` oder `paused` ist, wird der Wechsel mit einer verständlichen
Meldung blockiert. Erst Vorbereitung zurücknehmen oder das Ergebnis bestätigen.
Ein importierter Live-/Pausenstand bleibt erhalten und kann nach Auswahl fortgesetzt
werden; er wird nicht parallel zu einem anderen Event bedient.

### Import, Vorschau und Konflikte

1. Lokale `.json`-Datei über das Datei-Auswahlfeld wählen (maximal **10 MiB**).
2. Der Browser sendet den Text an die Vorschau-API. Der Server prüft JSON-Syntax,
   Schema-Version, Referenzen, L/R-/Score-Invarianten und die für Undo relevante
   Score-Historie. Veranstaltungsdaten mit Name und Zeitraum sind erforderlich.
3. Die Vorschau zeigt Name, Zeitraum, Ort sowie Teilnehmer-/Referee-/Play-Area-/Spielzahlen.
   **Bis hier wird nichts gespeichert oder ausgewählt.**
4. **Importieren** bestätigt den Vorgang. Der Server validiert erneut und prüft eine
   an Inhalt und ID gebundene Vorschau-Kennung. Änderungen an der Datei oder ein
   Serverneustart verlangen eine neue Vorschau. **Abbrechen** verwirft die Vorschau.
5. Erst danach wird eine neue Event-Datei atomar gespeichert und die Liste in allen
   Browsern aktualisiert. Auswahl erfolgt separat; die lokale Quelldatei bleibt erhalten.

Die stabile interne Event-ID steht im **Dateinamen**, nicht im portablen State.
Bei manueller Anlage wird sie aus Name/Jahr abgeleitet; Kollisionen bekommen `-2`,
`-3` usw. Eine spätere Namensänderung ändert die ID nicht.
Beim GUI-Import wird ein gültiger Dateiname ohne `.json` als ID vorgeschlagen.
Andernfalls wird die ID aus den Veranstaltungsdaten abgeleitet. Zulässig sind
Buchstaben, Ziffern, Bindestrich und Unterstrich, maximal 80 Zeichen; das erste
Zeichen muss alphanumerisch sein. Dateipfade werden nicht als IDs akzeptiert.

Existiert die Import-ID bereits, wird **niemals überschrieben**. Möglich sind
**Abbrechen** oder **Als neue Veranstaltung importieren** mit einer eindeutigen
zusätzlichen ID. Eine Kollision, die erst nach der Vorschau entsteht, wird ebenfalls
abgewiesen und erfordert diese ausdrückliche Entscheidung. Kein Merge, kein Update
bestehender Veranstaltungen, kein Löschen.

**JSON exportieren** lädt genau den vollständigen State einer Veranstaltung als
`<event-id>.json`, inklusive Ländercodes, Sportprofil, Perioden und Counterhistorie,
Referees, Officials, Scores und Actionlog. Auswahl-, Stream- und
Katalogmetadaten werden nicht in den State eingebaut. Auch inaktive Events sind
exportierbar. Der Export ist ein konsistenter serverseitiger Snapshot.

### Dateien, Migration und Backup

```text
data/
  events/
    prague-2026.json
    showdown-berlin-2026.json
  active-event.json
  active-event.json.lock
  tournament.json         # gegebenenfalls unverändertes Single-Event-Original
  tournament.json.lock
```

`active-event.json` enthält `active_event_id` (oder `null`) und `selection_token`
(eine UUID). Die Kennung ändert sich bei jedem echten Wechsel und bleibt über
Neustarts erhalten. Jede Event-Datei bleibt ein eigenständiger **schema_version-1**-
State. Ein gemeinsamer Katalog-Lock genügt, weil nur ein Prozess alle Event-Dateien
schreibt. Eine zusätzliche große gemeinsame State-Datei gibt es nicht.

Beim ersten Start ohne `active-event.json`:

- Existiert die bisherige `tournament.json` (bei Legacy-Config die dort angegebene
  `data_file`), wird sie vollständig validiert, als erstes Event unter einer aus
  Name/Jahr abgeleiteten ID kopiert und anschließend aktiv ausgewählt.
- **Die Originaldatei wird weder gelöscht noch verändert.** Erst die erfolgreich
  gespeicherte Auswahl schließt die Migration ab. Alle folgenden Änderungen gehen
  ausschließlich in die neue Event-Datei.
- Bricht der Prozess zwischen Kopie und Auswahl ab, erkennt der nächste Start die
  identische Kopie und vervollständigt die Auswahl. Eine abweichende bereits
  vorhandene Kopie oder ein uneindeutiger Katalog führt zum Startabbruch, ohne
  vorhandene Dateien zu überschreiben.
- Eine allein vorhandene `tournament.json.lock` ist kein Veranstaltungsstand.
- Ohne Legacy-Datei wird ein leerer Auswahlzeiger angelegt. Event-Dateien, die bereits
  unter `events/` liegen, werden aufgelistet und können ausdrücklich ausgewählt werden.

Sobald `active-event.json` existiert, ist die Migration abgeschlossen. Die alte
Datei wird nicht nochmals übernommen; andere Dateien lassen sich über die GUI
importieren. Fehlende aktive Event-Datei oder beschädigte Dateien führen zum
Startabbruch statt zu einer stillen Rücksetzung.

Für ein vollständiges Backup bei beendetem Server das Datenverzeichnis inklusive
`events/` und `active-event.json` kopieren. Lock-Dateien sind keine Nutzdaten.
Ein einzelner JSON-Export ist eine portable Veranstaltungsdatei für den Import auf
einer anderen Instanz. Bei laufendem Server sind separate Exporte konsistent je
Veranstaltung; sie sind kein zeitgleicher Gesamtsnapshot aller Events.

## Bedienung

1. Unter **Veranstaltungen** anlegen/importieren und auswählen. Unter
   **Konfiguration** lassen sich Name, Zeitraum, Ort, Logo-Pfad und Score-Bezeichnung
   der aktiven Veranstaltung bearbeiten.
2. Play Areas frei benennen: Field 1, Table 1, Court 1, Mat 1, Ring A usw.
3. Teilnehmer mit Namen, optional Kurzname, Ländercode und Logo-Pfad erfassen. IDs werden in
   der Oberfläche automatisch vergeben und bleiben bei Bearbeitung erhalten.
4. Spielplan mit Datum, Uhrzeit, Play Area, optionaler Turnierphase und Runde
   (Gruppe/Spielrunde) anlegen. Unbekannte Teilnehmer
   bleiben leer; Platzhalter können beispielsweise „1st Group A“ heißen.
   Spiele müssen innerhalb des Veranstaltungszeitraums liegen.
5. Zur Bedienung wechseln und ein Spiel auswählen. Die Liste ist nach Datum und
   Uhrzeit sortiert. Nach Spielende werden die verbleibenden Spiele angeboten.
6. **Paarung bestätigen** oder **Paarung ändern**. Zwei verschiedene bekannte
   Teilnehmer sind zum Start erforderlich. Dann L/R prüfen, gegebenenfalls
   **Seiten tauschen**, anschließend **Spiel starten**.
7. Score mit **+1 / −1** bedienen. Scores dürfen nicht negativ werden. **UNDO**
   nimmt die letzte noch nicht zurückgenommene Score-Aktion dieses Spiels zurück,
   auch wenn ein anderer Bediener sie ausgelöst hat oder inzwischen die Seiten
   gewechselt wurden. Undo ist auch nach Reload und Serverneustart verfügbar.
8. **Pause / Fortsetzen** und **Seitenwechsel** wirken sofort für alle Browser.
   In der Pause sind Score-Korrekturen und Undo weiterhin möglich.
9. **Spiel Ende** öffnet die Endstandprüfung. Erst **Ergebnis bestätigen** setzt
   das Spiel auf `finished`. Ändert ein anderer Bediener inzwischen den Zustand,
   wird die Bestätigung verworfen und der neue Stand muss erneut geprüft werden.
10. Nächstes Spiel auswählen. Abgeschlossene Ergebnisse bleiben im Spielplan und
    können nicht wieder geöffnet oder verändert werden.

Es gibt **ein global ausgewähltes Spiel**, auch wenn mehrere Play Areas hinterlegt
sind. Mehrere Browser bedienen dieses gleiche Spiel. Vorbereiten (`ready`), laufende
Spiele und Pause sperren die Konfiguration. Vor dem Start lässt sich die
Vorbereitung zurücknehmen. Vorhandene Einträge können in der Konfiguration zum
Bearbeiten ausgewählt werden; Löschfunktionen sind nicht enthalten.
Logo-Pfade werden als Metadaten gespeichert, ohne Upload oder Bildverwaltung.

Bei Verbindungsverlust zeigt die Oberfläche **Offline · Bedienung gesperrt**.
Aktionen werden offline nicht gesammelt. Nach Reconnect kommt ein vollständiger
aktueller Zustand. Bei einer unklaren HTTP-Antwort den angezeigten Zustand prüfen,
bevor eine Aktion erneut gebucht wird. Ein Reload löst keine Aktion aus.

## Referees und Officials

Unter `/config` lassen sich **Referees** mit Name und optionalem zweistelligem
Ländercode erfassen und bearbeiten. Ländercodes werden großgeschrieben, zum Beispiel
`de` → `DE`; ohne Angabe wird `""` gespeichert. IDs sind innerhalb der Referee-Liste
eindeutig und bleiben beim Bearbeiten erhalten. Eine Löschfunktion ist nicht enthalten.

Im Match-Editor stehen drei optionale Official-Plätze zur Auswahl. Bei importierten
Spielen mit mehr als drei Officials werden alle vorhandenen Plätze angezeigt und
bearbeitet; zusätzliche Zuweisungen werden nicht abgeschnitten. Leere Plätze werden
weggelassen. Die Reihenfolge der belegten Plätze bleibt erhalten. Unbekannte IDs oder
Dopplungen innerhalb desselben Spiels werden abgewiesen. API und Modell erlauben
**0 bis beliebig viele** Officials.

In der Live-Ansicht stehen Namen und optionale Ländercodes klein unter den
Bedienelementen. `GET /api/v1/live` gibt sie mit `position`, `role: "referee"` und
`role_label_en: "Referee"` aus. Officials haben keinen Einfluss auf Status, Score oder L/R.
Paarungskorrektur, Vorbereitung, Seitenwechsel, Undo, Pause/Fortsetzen und Neustart
lassen ihre Zuweisung unverändert. Die bestehende Konfigurationssperre während
`ready/live/paused` gilt auch für Referees und Official-Zuweisungen.

Das State-Schema bleibt **Version 1**. Fehlende `referees` und `officials` bedeuten
leere Listen; dafür gibt es keine Migration. Beim Bearbeiten eines geplanten Spiels
über die API bleiben bestehende Officials erhalten, wenn das Feld fehlt.
Ein ausdrückliches `"officials": []` entfernt die Zuweisungen.

## Sportprofil, Perioden und Counter

Teilnehmer besitzen wie Referees ein optionales `country_code` im zweistelligen
ISO-Alpha-2-Format, zum Beispiel `CZ` oder `DE`. Eingaben werden getrimmt und
großgeschrieben; ohne Angabe steht `""`. Das Feld ist unter `/config` editierbar
und wird in `/api/v1/live` unter `left` und `right` ausgegeben. Bei API-Änderungen
eines bestehenden Teilnehmers bleibt der Code erhalten, wenn das Feld fehlt;
`"country_code": ""` entfernt ihn.

Das optionale `event.sport_profile` ist eine kleine Konfiguration, keine Rules-Engine.
Es wird über die portable Veranstaltungs-JSON oder `POST /api/v1/config/event`
gesetzt; ein eigener Profil-Editor gehört nicht zur GUI. Beispiel Prag:

```json
{
  "sport": "blind_football",
  "ruleset": "IBSA 2025-2029",
  "periods": 2,
  "period_label": "Halbzeit",
  "counters": [
    {
      "id": "team_fouls",
      "label": "Fouls",
      "scope": "participant",
      "reset_each_period": true,
      "warning_at": 4,
      "critical_at": 5,
      "warning_label": "Nächstes Foul → Double Penalty",
      "critical_label": "Double Penalty"
    }
  ]
}
```

`sport` und `ruleset` sind beschreibende Metadaten. Im Core gibt es keinen
Blindenfußball-Zweig. Counter-IDs sind innerhalb des Profils eindeutig; aktuell
wird nur `scope: "participant"` unterstützt. `periods` ist eine positive ganze
Zahl, `period_label` frei wählbar. Andere Counter wie `knockdowns`, `warnings`
oder `point_deductions` und eine Bezeichnung „Runde“ passen in dieselbe Struktur,
ohne dass daraus Boxregeln oder automatische Score-Abzüge entstehen.

Ein Match speichert `period` (initial 1) und
`counters[counter_id][participant_id][period_als_string]`, beispielsweise:

```json
{
  "period": 2,
  "counters": {
    "team_fouls": {
      "bsc-praha": {"1": 3, "2": 0},
      "fc-ingolstadt-04": {"1": 4, "2": 1}
    }
  }
}
```

Counter gehören wie Scores zum **Teilnehmer**, nie zur Seite. Während `live` und
`paused` sind +1 und −1 möglich, ohne Bestätigungsdialog und niemals unter null.
Die Warn- und Critical-Schwellen sind reine Anzeigehilfen und begrenzen den Wert
nicht. In Prag erscheint bei 4 „Nächstes Foul → Double Penalty“, ab 5
„DOUBLE PENALTY“; auch 6, 7 usw. sind möglich. Es wird keine Strafaktion ausgelöst.
**UNDO bleibt ausschließlich Score-Undo**; Counter lassen sich mit −1/+1 korrigieren.

**2. Halbzeit starten** öffnet einen Bestätigungsdialog. Nur der nächste konfigurierte
Abschnitt ist während LIVE oder PAUSE erlaubt; Zurückspringen und Überspringen
sind nicht vorgesehen. Eine Änderung durch einen anderen Browser verwirft einen
offenen Dialog. Beim bestätigten Wechsel:

- bleiben vorherige Periodenwerte gespeichert;
- startet `reset_each_period: true` bei null;
- übernimmt `reset_each_period: false` den bisherigen Wert in den neuen Abschnitt;
- bleiben Score, Officials, L/R-Zuordnung und LIVE-/PAUSE-Status unverändert.

Seitenwechsel und Fortsetzen sind weiterhin eigene Aktionen. Es gibt keine Uhr
und keinen automatischen Perioden- oder Seitenwechsel.

### Halbzeitpause

Solange noch ein weiterer Abschnitt folgt, zeigt die Bedienung während LIVE/PAUSE
unter den Steuerelementen **Halbzeitpause** (bei Profilen ohne Halbzeiten:
**Pause zwischen Abschnitten**). Der Klick setzt ohne Dialog `intermission: true`;
die Periodenanzeige zeigt „1. Halbzeit · Halbzeitpause“, die API `half_time` /
„Half-time“. Ein versehentliches Setzen lässt sich mit **Zurück zu 1. Halbzeit**
korrigieren. **2. Halbzeit starten** (bestehender Bestätigungsdialog) beendet eine
gesetzte Halbzeitpause automatisch. Damit ergibt sich die Auswahl
1st half → Half-time → 2nd half.

- Halbzeitpause, Pause/Fortsetzen und Seitenwechsel sind voneinander unabhängig.
  Eine normale Pause ist keine Halbzeitpause; ein Seitenwechsel ändert keine Periode.
- Score, Counter, Undo und Seitenwechsel bleiben in der Halbzeitpause möglich;
  Counter zählen weiter zum aktuellen Abschnitt.
- Zurückspringen aus der 2. Halbzeit ist weiterhin nicht vorgesehen, weil dabei
  bereits erfasste Periodenwerte ihre Bedeutung verlören.
- `Ergebnis bestätigen` beendet auch eine gesetzte Halbzeitpause (`full_time`).
- Jedes Spiel startet ohne Halbzeitpause in Abschnitt 1; Werte eines vorherigen
  Spiels werden nicht übernommen. Bestandsdaten ohne `intermission` gelten als
  `false`; es wird keine Halbzeit abgeleitet oder erfunden.
- Die Ereignisliste protokolliert `intermission_started` und `intermission_ended`
  mit dem aktuellen Abschnitt. Fehlende Counterwerte
werden als null interpretiert; bei nicht zurückgesetzten Countern wird ein fehlender
aktueller Abschnitt aus dem letzten gespeicherten Abschnitt übernommen. Historische
Werte werden beim Weiterzählen nicht rückwirkend verändert. Nichtnull-Werte für
zukünftige Perioden, unbekannte Counter/Teilnehmer und negative Werte werden beim
Import abgewiesen. Geplante/vorbereitete Spiele benötigen Periode 1 und Nullwerte.

Schema-Version bleibt **1**: Ohne Profil gelten eine Periode und keine Counter;
fehlende `period`/`counters` bedeuten `1`/`{}`. Es gibt keine neue Migration.
Die vorhandene Event-Konfiguration bewahrt ein Profil, wenn `sport_profile` im
Request fehlt. Sobald ein Spiel gestartet wurde, lässt sich das Profil nicht mehr
ändern, damit gespeicherte Periodenwerte ihre Bedeutung behalten.

## Fachmodell und Persistenz

**L und R sind Positionen im Programmbild/Overlay, keine Teilnehmeridentitäten.**
Es gibt keine allgemeine Home/Away-Semantik. Der Score gehört immer dem Teilnehmer
innerhalb des jeweiligen Spiels:

```json
{
  "side_l": "bsc-praha",
  "side_r": "fc-ingolstadt-04",
  "scores": {"bsc-praha": 2, "fc-ingolstadt-04": 1}
}
```

Ein Seitenwechsel tauscht ausschließlich `side_l` und `side_r`.
BSC Praha behält 2, Ingolstadt behält 1. Frühere Ergebnisse bleiben pro Spiel
separat erhalten.

Die vollständige Datei hat `schema_version: 1`, eine monotone `revision`, `event`,
`play_areas`, `participants`, `referees`, `matches`, `active_match_id` und `events`.
Das [Beispiel](examples/prague-2026.json) zeigt das vollständige Format.
Ein Match enthält die Planfelder `id`, `date`, `time`, `play_area_id`, `round`,
`stage`, `stage_label`, `round_label`, `participant_1`, `participant_2`, `officials`,
optionale Platzhalter und zusätzlich `status`, `side_l`, `side_r`, `scores`,
`control_revision`, `period`, `intermission` und `counters`. `stage` ist die
Turnierphase (Excel-Spalte „Phase“), `round` die Gruppe bzw. Spielrunde (Spalte
„Gruppe“); `stage_label`/`round_label` sind optionale englische Anzeigetexte.
Fehlende neue Felder bedeuten `""` bzw. `false`; die Schema-Version bleibt 1,
eine Migration ist nicht nötig. API-Clients, die ein geplantes Spiel ohne diese
Felder speichern, lassen vorhandene Werte unverändert.
Datum und Uhrzeit sind lokale Veranstaltungsangaben; Ereigniszeitstempel sind UTC
im ISO-Format.

Erlaubte Übergänge:

```text
scheduled → ready → live ⇄ paused
             ↓        ↘   ↙
          scheduled   finished
```

`prepare` bestätigt/korrigiert eine Paarung und legt die Seiten fest;
`unprepare` nimmt ausschließlich vor Spielbeginn die Vorbereitung zurück.
`idle` wird nur von der API verwendet, wenn kein Spiel ausgewählt ist.
Unbekannte Paarungen können `scheduled` bleiben; `ready` benötigt eine gültige
Paarung mit zwei unterschiedlichen Teilnehmern und Scores von null.

Jede Änderung läuft unter einem zentralen Lock:

1. gültigen Übergang und Eingaben prüfen,
2. Kopie des Zustands ändern und vollständig validieren,
3. JSON in eine temporäre Datei **im selben Verzeichnis** schreiben,
4. Datei flushen, mit `fsync` sichern und schließen,
5. mit `os.replace` atomar an die Stelle der Datendatei setzen,
6. erst danach In-Memory-Zustand und Browser aktualisieren.

Bei einem Schreibfehler bleiben bisheriger Dateistand und Serverzustand erhalten.
Disk-I/O läuft in einem Thread; das Lock bleibt bis zum Abschluss gehalten.
Die atomare Ersetzung schützt vor halben JSON-Dateien bei Prozessabbruch auf
üblichen lokalen Dateisystemen; sie ersetzt kein Backup gegen Plattenausfall oder
Stromverlust. Die Event-Dateien behalten Schema-Version 1; die oben beschriebene
Migration verändert ihren fachlichen State nicht. Unbekannte Schema-Versionen
werden abgewiesen. Auch der Auswahlzeiger wird validiert und mit demselben
Temp-/Flush-/fsync-/Replace-Verfahren gespeichert. Anlegen/Importieren speichern
nur die neue Event-Datei; Auswählen schreibt nur den Auswahlzeiger.

Die Ereignisliste protokolliert insbesondere `match_started`, `score`, `pause`,
`resume`, `side_switch`, `match_finished`, `counter`, `period_changed`,
`intermission_started`, `intermission_ended` und `undo` samt Spiel-/Teilnehmerbezug,
Zeitstempel, Revision und Request-ID. Undo markiert das Score-Ereignis und verweist
auf seine ID. Counter-Ereignisse enthalten zusätzlich `counter_id`, `period` und
`delta`; Periodenwechsel nennen den neuen Abschnitt. Die Liste dient auch zur persistenten Request-Deduplizierung.
Sie bleibt für die gesamte Veranstaltungsdatei erhalten; kein Event-Sourcing und
keine automatische Archivierung.

## Architektur und mehrere Bediener

- `livescore/models.py`: validierte Datenmodelle und Invarianten.
- `livescore/service.py`: zentraler autoritativer Zustand, explizite Übergänge,
  Serialisierung aller Mutationen und Projektion für die Anzeige.
- `livescore/catalog.py`: Event-Dateien, Auswahl, Import/Export und Migration;
  nutzt dieselbe Mutationssperre und dieselbe Live-Logik.
- `livescore/storage.py`: atomare JSON-Speicherung und Prozesssperre.
- `livescore/app.py`: FastAPI, HTTP-Endpunkte, WebSocket und statische Dateien.
- `livescore/config.py`, `__main__.py`: Config und Uvicorn-Start.
- `static/`: responsive HTML/CSS und Vanilla JavaScript ohne Build-Schritt.

Browser erhalten beim Verbinden und nach Änderungen vollständige Snapshots über
`/api/v1/ws`. Jeder Browser hat eine Warteschlange für den **neuesten** Snapshot;
langsame Verbindungen blockieren weder Mutationen noch andere Browser. Sendetimeout,
Heartbeat, Wiederverbindung und Revisionen schützen gegen veraltete Anzeigen.
Die Event-Revisionen bleiben je Veranstaltung erhalten und können beim Wechsel
kleiner werden. Deshalb trägt der UI-Snapshot zusätzlich `stream_id` (Serverstart)
und `stream_revision` (Reihenfolge aller Änderungen seit Start). Die Oberfläche
verwirft ältere HTTP-/WebSocket-Antworten und übernimmt beim Reconnect den neuen
Initialsnapshot. Katalogänderungen werden ebenfalls über denselben Kanal verteilt.

Konfigurations- und Zustandsaktionen benötigen die zuletzt angezeigte
`expected_revision`; veraltete Aktionen erhalten HTTP **409**. Für Score- und Counter-Aktionen
wird stattdessen die `control_revision` des Spiels geprüft. Dadurch dürfen zwei
Browser vom gleichen Score-Stand aus gleichzeitig buchen: Beide Änderungen werden
addiert. Seitenwechsel, Pause, Fortsetzen, Undo und andere Steueraktionen erhöhen
diese Kontrollrevision und machen alte Score-Requests ungültig. Zusätzlich werden
Spiel-ID und Teilnehmer-ID geprüft, beim Score außerdem die Seitenzuordnung,
beim Counter der aktuelle Abschnitt. Auch ein Periodenwechsel erhöht die
Kontrollrevision. Parallele Score-/Counter-Buchungen addieren sich unter demselben
Lock; veraltete Requests dürfen keinen Wert in einer neuen Periode verändern.

**Alle mutierenden Bedien-/Config-Requests benötigen zusätzlich `event_id` und
`selection_token` aus dem angezeigten UI-Snapshot.** Die Kennung schützt auch vor
A → B → A-Wechseln bei gleicher Event-Revision. Requests ohne passenden Kontext
werden mit 409 abgewiesen. Das ist eine bewusste Ergänzung der internen Bedien-API;
die GET-Live-API behält ihre bisherigen Felder; Officials, Ländercodes, Perioden, Counter,
`period_info`, `stage`, `round` und Officials-Funktionen kommen additiv hinzu. Alte Browserseiten müssen
nach dem Upgrade neu geladen werden. Ein Event-Wechsel aktualisiert auch offene
Config-Seiten, schließt alte Formulare und meldet verworfene ungespeicherte Entwürfe.

Alle Mutationen benötigen eine UUID `request_id`. Bei Spiel-/Config-Aktionen gilt: Wiederholung desselben Requests
liefert den aktuellen Zustand, ohne erneut zu buchen, auch nach Neustart.
Gleiche ID mit abweichendem Inhalt ergibt 409. Die Oberfläche sperrt Buttons während
einer Anfrage und kurz danach gegen Doppelklicks. Zwei bewusst getrennte Requests
verschiedener Bediener zählen als zwei Aktionen; der Server kann nicht erkennen,
ob beide dasselbe reale Tor meinten. Das lässt sich mit gemeinsamem Undo korrigieren.

Katalogaktionen verwenden zusätzlich `catalog_session` aus `stream_id`. Gleiche
Request-ID und gleicher Inhalt werden innerhalb dieses Serverstarts nur einmal
verarbeitet. Nach einem Neustart werden alte Katalogrequests abgewiesen; vor einem
neuen Versuch die Liste prüfen. So kann eine unklare Create-/Import-Antwort nicht
nach Neustart blind eine weitere Kopie anlegen. Dafür ist kein zusätzliches
persistentes Katalog-Transaktionslog erforderlich. Import-Vorschauen werden durch
eine serverseitige HMAC-Kennung gebunden; es werden keine Upload-Dateien vorgelagert.

## HTTP- und WebSocket-API

Interaktive OpenAPI-Dokumentation: `/docs`, Schema: `/openapi.json`.

### Externer Vertrag: GET /api/v1/live

```json
{
  "status": "live",
  "revision": 6,
  "match_id": "match-001",
  "period": 1,
  "period_info": {"number": 1, "intermission": false, "code": "first_half", "label_en": "1st half"},
  "stage": {"code": "group_stage", "name": "Gruppenphase", "label_en": "Group stage"},
  "round": {"code": "group_a", "name": "Gruppe A", "label_en": "Group A"},
  "play_area": {"id": "field-1", "label": "Field 1"},
  "left": {"id": "bsc-praha", "name": "BSC Praha", "short_name": "BSC", "country_code": "CZ", "score": 2, "counters": {"team_fouls": 0}, "counter_states": {"team_fouls": "normal"}},
  "right": {"id": "fc-ingolstadt-04", "name": "FC Ingolstadt 04", "short_name": "FCI", "country_code": "DE", "score": 1, "counters": {"team_fouls": 0}, "counter_states": {"team_fouls": "normal"}},
  "officials": [
    {"id": "luis-ramon-perez-macias", "name": "Luis Ramon Pérez Macias", "country_code": "ES", "position": 1, "role": "referee", "role_label_en": "Referee"},
    {"id": "bennet-kruekemeier", "name": "Bennet Krükemeier", "country_code": "DE", "position": 2, "role": "referee", "role_label_en": "Referee"},
    {"id": "juan-carlos-paule", "name": "Juan Carlos Paule", "country_code": "ES", "position": 3, "role": "referee", "role_label_en": "Referee"}
  ]
}
```

Das Beispiel entspricht Auswahl, Vorbereitung, Start und drei Score-Aktionen auf
Basis der Beispieldatei und wird automatisiert gegen die API geprüft.
Nach Seitenwechsel enthält `left` Ingolstadt mit 1 und `right` Praha mit 2.
Ohne ausgewähltes Spiel: `status: "idle"`, `period`, `period_info`, `stage`, `round`,
`match_id`, `play_area`, `left` und `right` sind `null`. Beim ausgewählten, noch nicht vorbereiteten Spiel:
`status: "scheduled"`, Match/Play Area sind vorhanden, `left` und `right` sind
`null`. Ein bestätigtes Ergebnis bleibt als `finished` sichtbar, bis ein anderes
Spiel ausgewählt wird. Fehlende Kurznamen erscheinen als leere Zeichenfolge.
`officials` enthält die aufgelösten Referee-Objekte des aktuellen Matches, bereits
ab `scheduled`. Ohne Match oder ohne Officials ist es `[]`. `/tournament` enthält
zusätzlich die gesamte `referees`-Liste; dort und in `/matches` bleiben
`match.officials` geordnete Listen von Referee-IDs.
`period` nennt den aktuellen Abschnitt, bereits ab `scheduled`.
`left/right.counters` liefern nur die aktuellen Werte; `counter_states` enthält
je Counter `normal`, `warning` oder `critical` (Critical hat Vorrang).
Ohne konfigurierten Counter sind beide Objekte leer. GFX muss keine Periodenhistorie
auswerten. Das gesamte Profil und die Historie stehen im Tournament-State bzw.
Export zur Verfügung.

#### Additive Felder: Spielperiode, Turnierphase, Runde, Officials-Funktion

Alle bisherigen Felder behalten Namen, Typ und Bedeutung. Neu hinzugekommen sind
(ab `scheduled`, bei `idle` jeweils `null`):

| Feld | Inhalt |
|---|---|
| `period_info.number` | identisch mit `period` |
| `period_info.intermission` | `true` während einer ausdrücklich gesetzten Pause zwischen zwei Abschnitten (Halbzeitpause) |
| `period_info.code` | stabiler Code, siehe unten |
| `period_info.label_en` | englisches Label oder `null` |
| `stage` | Turnierphase: `code`, `name` (Originaltext), `label_en`; `null` ohne Angabe |
| `round` | Gruppe bzw. Spielrunde aus `match.round`, gleiche Struktur wie `stage` |
| `officials[].position` | Reihenfolge im Spiel ab 1, keine Funktion |
| `officials[].role` / `role_label_en` | `referee` / `Referee` |

`period_info.code` richtet sich nach bestehendem Spielstatus, `period` und
`intermission`:

| Situation | Halbzeit-Profil | anderes oder kein Profil |
|---|---|---|
| `scheduled`, `ready` | `not_started` · „Not started“ | `not_started` · `null` |
| `live`/`paused`, Abschnitt 1 | `first_half` · „1st half“ | `period_1` · `null` |
| `live`/`paused` mit `intermission` | `half_time` · „Half-time“ | `intermission_after_1` · `null` |
| `live`/`paused`, Abschnitt 2 | `second_half` · „2nd half“ | `period_2` · `null` |
| `finished` | `full_time` · „Full-time“ | `finished` · `null` |

Ein **Halbzeit-Profil** liegt vor, wenn `sport_profile.periods` genau 2 ist und
`period_label` (ohne Groß-/Kleinschreibung) `Halbzeit`, `Half` oder `Poločas` lautet.
Das ist bei Prag der Fall. Boxen, Showdown oder Profile mit „Runde“/„Satz“
erhalten keine Fußball-Labels, sondern nur neutrale Codes. `paused` ist eine
normale Unterbrechung und erzeugt **nicht** „Half-time“.

Für `stage` und `round` gilt diese feste Zuordnung (Vergleich ohne Groß-/Kleinschreibung,
Originaltext bleibt in `name` erhalten):

| Originalwert | `code` | `label_en` |
|---|---|---|
| Gruppenphase | `group_stage` | Group stage |
| Gruppe A … Gruppe Z | `group_a` … `group_z` | Group A … Group Z |
| Play-Offs | `play_offs` | Play-offs |
| semi final #1 / #2 | `semi_final_1` / `semi_final_2` | Semi-final 1 / Semi-final 2 |
| match for place 5th | `fifth_place_match` | 5th-place match |
| bronze medal match | `bronze_medal_match` | Bronze medal match |
| gold medal match | `gold_medal_match` | Gold medal match |

Unbekannte Werte werden nicht übersetzt: `code` und `label_en` sind dann `null`,
`name` enthält den Originaltext. Im Spiel-Editor kann optional ein englischer
Anzeigetext (`stage_label`, `round_label`) hinterlegt werden; er ersetzt dann nur
`label_en`. Teilnehmer- und Personennamen werden nie übersetzt.

Alle Officials eines Spiels sind im Modell Einträge der **Referee**-Liste und
werden deshalb als `referee`/„Referee“ ausgegeben. `position` gibt nur die
Reihenfolge wieder; Funktionen wie Assistant Referee oder Timekeeper werden daraus
nicht abgeleitet.

**Verfügbarkeit** – drei Fälle werden unterschieden:

- *Von der Quelle nicht unterstützt:* Das Feld fehlt ganz, z. B. bei älteren
  LiveScore-Versionen `period_info`/`stage`/`round`/`role`, bei Countern ein
  nicht konfigurierter Counter in `counters`. **Trikotfarben liefert LiveScore
  nicht**; es gibt kein Farbfeld.
- *Unterstützt, aber beim aktuellen Spiel keine Angabe:* `stage`/`round` sind
  `null`, `label_en`/`code` sind `null`, `country_code` ist gemäß bestehendem
  Vertrag `""`, `officials` ist `[]`.
- *Gültiger Wert:* auch `0` ist ein echter Wert, z. B. `counters.team_fouls: 0`.

Ländercodes bleiben **ISO 3166-1 Alpha-2** (`CZ`, `DE`, `KZ`, `GR`), wie sie die
GFX-Engine für ihre Flaggendateien erwartet. Spielpläne mit IOC-/FIFA-Kürzeln müssen
bei der Erfassung umgesetzt werden: `CZE → CZ`, `GER → DE`, `KAZ → KZ`, `GRE → GR`.
`GER` und `GRE` sind **keine** ISO-Alpha-3-Codes (dort `DEU`/`GRC`); LiveScore nimmt
drei Buchstaben deshalb nicht an und rät keine Nation. Die Nation gehört zum
Teilnehmer und wandert bei Seitenwechsel mit Name, Score und Countern mit.

Alle neuen Felder stehen auch im `live`-Objekt des WebSocket-/Tournament-Snapshots.
Jede Änderung von Halbzeitpause, Periode oder Spielplan erhöht `revision`, auch ohne
Scoreänderung; Pollende Clients sehen sie beim nächsten Abruf.

```sh
curl --fail http://127.0.0.1:8730/api/v1/live
```

Alle vier bestehenden GET-Endpunkte (`live`, `tournament`, `matches`, `events`)
beziehen sich immer auf die **aktive Veranstaltung**. Ohne Auswahl bleibt `live`
`idle`, die Match-/Actionlog-Listen sind leer. `/api/v1/events` bleibt das Actionlog,
kein Veranstaltungskatalog. Die externe Live-Revision ist weiterhin eine
**Event-Revision**, kein globaler Änderungszähler; nach Wechsel kann sie sinken.
GFX kann diesen Endpunkt beispielsweise einmal pro Sekunde pollen und benötigt
keine Sport-, Turnier- oder Seitenwechsellogik. HTTP-Antworten werden mit
`Cache-Control: no-store` geliefert.

### Bedien-API

| Methode / Pfad | Bedeutung |
|---|---|
| `GET /api/v1/tournament` | vollständiger UI-Snapshot, ohne Ereignisliste, mit `live` und `can_undo` |
| `GET /api/v1/matches` | Spielplan inklusive Spielstatus und teilnehmerbezogenen Scores |
| `GET /api/v1/events` | Ereignisse ohne interne Request-Signatur |
| `POST /api/v1/config/event` | Veranstaltung setzen |
| `POST /api/v1/config/play-areas` | Play Area anlegen/über ID aktualisieren |
| `POST /api/v1/config/participants` | Teilnehmer anlegen/über ID aktualisieren |
| `POST /api/v1/config/referees` | Referee mit `id`, `name`, optional `country_code` anlegen/aktualisieren |
| `POST /api/v1/config/matches` | geplantes Spiel anlegen/über ID aktualisieren |
| `POST /api/v1/live/select` | geplantes Spiel auswählen |
| `POST /api/v1/live/prepare` | Paarung bestätigen/korrigieren und L/R festlegen |
| `POST /api/v1/live/unprepare` | Vorbereitung zurücknehmen |
| `POST /api/v1/live/start` | vorbereitetes Spiel starten |
| `POST /api/v1/live/score` | +1 oder −1 für Teilnehmer auf angegebener Seite |
| `POST /api/v1/live/counter` | +1 oder −1 für einen Teilnehmer-Counter im aktuellen Abschnitt |
| `POST /api/v1/live/period` | bestätigter Wechsel zum nächsten Abschnitt, nur live/paused |
| `POST /api/v1/live/intermission` | Pause zwischen Abschnitten setzen/zurücknehmen (`intermission`: true/false), nur live/paused |
| `POST /api/v1/live/pause` | live → paused |
| `POST /api/v1/live/resume` | paused → live |
| `POST /api/v1/live/switch-sides` | nur L/R tauschen (ready/live/paused) |
| `POST /api/v1/live/undo` | letzte geeignete Score-Aktion zurücknehmen |
| `POST /api/v1/live/finish` | Ergebnis bestätigen (live/paused → finished) |
| `WS /api/v1/ws` | initialer UI-Snapshot, weitere Snapshots, Heartbeat alle 5 Sekunden bei Leerlauf |

Mutationen geben den aktuellen UI-Snapshot zurück. Allgemeine Spielaktionen
benötigen `request_id`, `expected_revision` und `match_id`. `prepare` benötigt
zusätzlich `participant_1`, `participant_2`, `side_l` und `side_r` als IDs.
Config-Aktionen benötigen `request_id`, `expected_revision`, `event_id`,
`selection_token` und `data` mit den
jeweiligen Planfeldern; Status und Scores dürfen dort nicht gesetzt werden.

Beispiel Score-Request (Werte immer aus aktuellem UI-Snapshot übernehmen):

```json
{
  "request_id": "66cf0c9b-2d91-4e8a-a67c-1cf0738d0be3",
  "event_id": "prague-2026",
  "selection_token": "91ba2d69-83a5-4ef8-acec-5c94b92de77d",
  "match_id": "match-001",
  "control_revision": 2,
  "participant_id": "bsc-praha",
  "side": "L",
  "delta": 1
}
```

Fehler: **422** bei ungültigen Feldern/Referenzen, **409** bei unzulässigem
Übergang oder veraltetem Zustand, **503** bei Speicherfehler. Nach 409 Zustand
neu laden und bewusst erneut bedienen; keine blinde Wiederholung mit neuer Revision.
Nach unklarer Transportantwort ist derselbe Request mit derselben ID wiederholbar.
`POST /api/v1/live/counter` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `control_revision`, `participant_id`, `counter_id`, die aktuelle `period`
und `delta` (−1 oder +1). Es verwendet wie Score **keine** `expected_revision`.
`POST /api/v1/live/period` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `expected_revision` und die **Zielperiode** `period` (aktuell + 1).
Die Bestätigung erfolgt im Browser; der Server prüft Zustand, Revision und Profilgrenze.
`POST /api/v1/live/intermission` benötigt `request_id`, `event_id`, `selection_token`,
`match_id`, `expected_revision` und `intermission` (boolean). Setzen ist nur vor dem
letzten Abschnitt möglich; derselbe Zielwert wie der aktuelle ergibt 409.
WebSocket-Heartbeat: `{"heartbeat": true}`. Normale Nachrichten entsprechen
`GET /api/v1/tournament`. Nach spätestens etwa 14 Sekunden ohne Nachricht sperrt
die UI die Bedienung; erkannter Browser-Offline-Status sperrt sofort.

### Veranstaltungskatalog-API

| Methode / Pfad | Bedeutung |
|---|---|
| `GET /api/v1/event-catalog` | `items` mit IDs, Veranstaltungsdaten und Anzahlen; aktive ID und Auswahlkennung |
| `GET /api/v1/event-catalog/active` | `active_event_id` und `selection_token` |
| `POST /api/v1/event-catalog/create` | neue Veranstaltung; `event` mit Veranstaltungsdaten |
| `POST /api/v1/event-catalog/select` | auswählen; Ziel-`event_id` und bisheriger `selection_token` |
| `POST /api/v1/event-catalog/import/preview` | `json_text` und optionale `event_id`; vollständig validierte Vorschau, `collision`, `preview_token` |
| `POST /api/v1/event-catalog/import` | bestätigter Import mit `json_text`, Vorschau-`event_id`, `preview_token`, `as_new` (Default false) |
| `GET /api/v1/event-catalog/{event_id}/export` | Download einer einzelnen portablen State-JSON |

`create`, `select` und bestätigter `import` benötigen außerdem `request_id` und
`catalog_session`. Antworten sind aktuelle UI-Snapshots; Create/Import liefern
zusätzlich `created_event_id`. Anlage und Import aktivieren die Veranstaltung
nicht automatisch. Preview benötigt keine Request-ID und hat keine Seiteneffekte.
Fehlerhafte Syntax/States ergeben 422, ID-/Kontext-/Vorschaukonflikte 409,
Schreibfehler 503, Export einer unbekannten ID 404. Das aktuelle Event wird auch
bei fehlgeschlagenem Import oder Wechsel nicht verändert.

Der UI-Snapshot enthält zusätzlich `active_event_id`, `selection_token`, `catalog`,
`stream_id` und `stream_revision`. Diese Felder gehören nicht zur exportierten
Veranstaltungsdatei und nicht zum stabilen `GET /api/v1/live`-Format.

## Tests und Entwicklungsprüfung

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Für den automatisierten Browserlauf einmal Chromium installieren:

```sh
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
.venv/bin/python tests/browser_auth_smoke.py
# Zusätzlicher isolierter Installer-/Upgrade-/Uninstall-Test mit echter venv/pip:
.venv/bin/python tests/deployment_smoke.py
.venv/bin/python tests/auth_recovery_smoke.py
```

Alternativ einen vorhandenen Browser lesend verwenden:

```sh
.venv/bin/python tests/browser_smoke.py --chromium /pfad/zu/chrome
.venv/bin/python tests/browser_auth_smoke.py --chromium /pfad/zu/chrome
```

Der Browsertest setzt zusätzlich `curl` voraus. Er startet einen eigenen
Loopback-Server auf einem freien Port, verwendet getrennte Browser-Kontexte mit
Smartphone-/Tablet-Viewport und beendet nur seinen eigenen Server. Temporäre
Daten, Browserprofile, Logs und Screenshots liegen unter `.test-artifacts/`.
Automatisierte Tests verwenden eigene Datenverzeichnisse, niemals produktive Event-Dateien.
Der bisherige Fach-Smoke läuft ausdrücklich mit `auth.enabled: false` und deutscher
Sprache. `browser_auth_smoke.py` ergänzt einen eigenen Server mit aktiviertem Auth:
EN-Default, DE/CS und Fallback, Erstlogin, Admin-Passwortwechsel und Resets,
Default-Warnungen, fachliche Vollberechtigung für Admin und Operator, gesperrte
Passwortverwaltung für Operator, zwei angemeldete Operatoren
mit Score-/Counter-/Periodensynchronisation, Sessionentzug, Logout und Neustart.
Die Auth-Unit-Tests prüfen darüber hinaus Rollen direkt an den Endpunkten,
CSRF, öffentliche Live-GET-API bei geschützten übrigen Endpunkten, Secure-Cookies, Ablauf, Rate-Limit, fehlgeschlagene
Passwortspeicherung und WebSocket-Origin-Prüfung.

Abgedeckt sind Datenvalidierung, atomare Speicherung, Schreibfehler, Wiederherstellung,
Paarungskorrektur, alle Bedienaktionen, die 2:1-Seitenwechsel-Invariante, API,
Request-Deduplizierung, Revisionskonflikte, parallele Requests und zwei WebSockets.
Der Browserlauf prüft außerdem Konfigurationsformulare, automatische Synchronisation,
Doppelklick, Reload, Offline/Reconnect, Endstandprüfung, nächstes Spiel, `curl` und
echten Serverneustart. Neu geprüft werden Katalog, Migration samt Unterbrechung,
Importvorschau ohne Schreibeffekt, Konflikte, Export, Wechselblockaden, Isolation,
veraltete Config-Requests und Event-Wechsel bei sinkender Event-Revision. Der Browser
importiert die echte Prag-Datei über ein echtes Datei-Auswahlfeld und prüft zwei
Veranstaltungen, Config-Entwürfe sowie Erhalt beider Stände nach Neustart. Unter Windows sind Startpfad und Dateisperre implementiert,
der bisherige praktische Testlauf erfolgte unter Linux/Chromium.
Referee-Tests prüfen Anlage/Bearbeitung, Referenzen und Duplikate, 0/1/3/>3 Officials,
Reihenfolge, Bestandsschutz bei allen Live-Aktionen und Neustart, Live-API sowie
Export/Reimport. Der Browser prüft zusätzlich Referee-Formulare, Match-Zuweisung
und die synchrone Officials-Anzeige in zwei Sessions.
Counter-Tests prüfen Ländercodes, Profilvalidierung, Teilnehmerbindung bei
Seitenwechsel, Grenzen/Anzeigeschwellen, getrennte Perioden, Reset und Übernahme,
parallele Requests, persistente Deduplizierung, veraltete Aktionen und zwei WebSockets.
Der Browserlauf importiert das Prag-Profil, prüft Warnung bei 4 und Critical bei
5/6, Bestätigung/Abbruch und Konflikte beim Halbzeitwechsel, zwei synchronisierte
Browser sowie Export/Reimport und echten Serverneustart mit Periode-2-Countern.
`tests/test_live_metadata.py` prüft die additiven Live-API-Felder: Turnierphase und
Runde getrennt samt englischer Labels und unbekannter Werte, drei Officials mit
Funktion, Position und Sonderzeichen, vorhandene/fehlende Nationen und korrigierte
Paarungen, 1. Halbzeit/normale Pause/Halbzeitpause/2. Halbzeit/Full-time,
Seitenwechsel ohne Periodenwechsel, WebSocket/Poll ohne Scoreänderung, Neustart,
neutrale Codes für andere Profile, Bestandsdateien ohne neue Felder und die
bisherigen Feldtypen für bestehende Clients.

## Bewusste Grenzen

Keine automatische Tabellenberechnung, Finalpaarungen, Sportregelberechnung, Sätze, Karten,
Strafaktionen, Spielerfouls, Spielerkader, Match-Uhr, Boxregeln, Torschützen, Statistiken, Cloud-Sync, GFX-Rendering oder
OBS-/LPE-Integration. Implementiert sind manuelle Eingabe und Import/Export nativer
LiveScore-JSON-Dateien. CSV, Fremdformate und externe Turnieradapter sind weiterhin
**nicht implementiert**. Tournify ist keine Laufzeitabhängigkeit. Event-Löschen,
Archivierung, Suche und mehrere gleichzeitig aktive Veranstaltungen sind nicht enthalten.
