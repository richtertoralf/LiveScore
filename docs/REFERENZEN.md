# Referenzprüfung und Portwahl

Lesende Bestandsaufnahme auf `codex-dev` (10.77.0.108), 28./29.09.2026.
Keine fremden Dateien oder Dienste wurden verändert.

## Untersuchte Muster

| Projekt | Gelesene Bereiche | Entscheidung für LiveScore |
|---|---|---|
| `~/gfx-engineV2` | README, `core/config.py`, `api/state/router.py`, `publisher.py`, `websocket_manager.py`, `tests/test_state_routes.py`, Dokumentations-/Testsuchen | FastAPI liefert statische UI und REST; vollständiger Initialsnapshot und weitere Snapshots über einen WebSocket. Reconnect lädt den autoritativen Zustand. |
| `~/mediamtxMonitor` | README, `bin/monitoring_api.py`, `config/collector.yaml`, `systemd/mediamtx-api.service`, Struktur und Betriebshinweise | Kleine Python-Anwendung, zentrale Serverkonfiguration, statisches Frontend, expliziter Startbefehl. Optionales systemd-Beispiel ohne systemweiten Installer. |
| `~/winlaufen-web` | AGENTS, Struktur, Entwicklungs-/Installationsdokumentation, Portangaben | Stabile Config und Nutzerdaten getrennt vom Code, nachvollziehbare Betriebsanleitung, Tests ohne produktive Daten. Java-/Modularchitektur wird nicht übernommen. |
| `~/live-production-engine` | README, Runtime-Config-Beispiel, Installationsdokumentation, Port-/Dienstsuche | Bestehende MediaMTX-/Monitor-/Redis-Ports berücksichtigen; keine Kopplung oder Integration. |
| `~/richter-stream-pages` | README, Betriebshinweise und Portsuche | 8081 ist ebenfalls als PHP-Admin-Webserver vorgesehen. Nicht als LiveScore-Default verwenden. |

Die GFX-Routen lesen/modifizieren/schreiben teilweise Redis-JSON und senden danach
Snapshots. Bei den untersuchten Routen war keine für LiveScore übernehmbare
Revisions-/Lock-Absicherung vorhanden. LiveScore ergänzt deshalb einen zentralen
Mutation-Lock, persistierte Revisionen, eine Prozesssperre und Request-IDs. Redis,
Runner-Prozesse und sportspezifische Projektionen werden nicht übernommen.

Der untersuchte GFX-Broadcast sendet nacheinander an Browser. LiveScore verwendet
stattdessen je Verbindung eine kleine Warteschlange für den neuesten Snapshot
sowie ein Sendetimeout, damit langsame Browser andere Bediener nicht aufhalten.
Es bleibt ein einzelner lokaler Prozess mit einer JSON-Datei.

## Listener und reservierte Ports

`ss -ltnp` zeigte bei der Bestandsaufnahme folgende TCP-Listener:

| Port | Befund |
|---|---|
| 22 | SSH |
| 53 | lokale DNS-Listener 127.0.0.53 / 127.0.0.54 |
| 6379 | Redis, Loopback IPv4/IPv6 |
| 8080 | MediaMTX Monitor; eigener Python/FastAPI-Server |
| 8720 | GFX-Engine; Uvicorn aus `/opt/gfx-engine` |
| 1935, 8554, 8888, 8889, 8892, 9997 | vorhandene Media-/Produktionslistener; die MediaMTX-Standardports sind auch in der LPE-Betriebsdokumentation genannt |
| 33561 | temporärer Codex-Loopback-Listener |
| 44440, 44441, 44442 | weitere vorhandene Listener; kein Eingriff |

Nicht aktiv lauschend, aber in Projekten vorgesehen: **8081** (WinLaufen-Web und
Stream-Pages-Admin), **8090** (WinLaufen-Bridge); **8000** wird in Stream Pages als
lokaler Vorschau-Port dokumentiert.

Für nginx, apache2 und caddy ergab `systemctl show` jeweils `LoadState=not-found`
und `ActiveState=inactive`. Auf 80/443 gab es keinen Listener. In den geprüften
Anwendungen wurde kein gemeinsamer Reverse Proxy vorausgesetzt; sie liefern ihre
UIs mit dem jeweiligen eigenen Webserver aus. Dies ist eine Momentaufnahme,
keine globale Portreservierung für alle künftigen Installationen.

**LiveScore verwendet standardmäßig 8730**, zum Prüfzeitpunkt frei und ohne
Reservierung in den gezielt geprüften Projektkonfigurationen. Host, Port und
Datenpfad bleiben über `config/livescore.yml` einstellbar. Es wurden keine
bestehenden Ports, Proxy-Konfigurationen oder Dienste verändert.

## Installer, Upgrade und Web-Version

Für den Deployment-Stand wurden zusätzlich ausschließlich lesend untersucht:

- **winlaufen-web:** `installer/linux/install.sh`, `uninstall.sh`, Installer-Tests
  sowie die Footer in Bridge-Control und Web-Viewer. Übernommen: Trennung
  `/opt` / `/etc` / `/var/lib`, eigenes Dienstkonto, Staging-Root ohne Hostdienste,
  Config-Erhalt, Daten behalten beim Uninstall und ausdrückliches `--purge`.
  Der kleine Versionsfooter wird hier über eine öffentliche API statt Maven erzeugt.
- **race-vision:** `install.sh`, `upgrade.sh`, `uninstall.sh`, Installer-Bibliothek.
  Übernommen: GitHub/main bzw. lokale `--source`, neue venv vor Umschalten prüfen,
  Rollback bei Startfehler, `/usr/local/bin`-CLI und geschützte Betreiberverzeichnisse.
- **gfx-engineV2:** Installer, Upgrader und Lifecycle-/Versions-/Uninstaller-Tests.
  Übernommen: explizite Dateien statt ganzer Arbeitskopie installieren, keine Git-
  oder Secret-Dateien in der Laufzeit, Dependency-Prüfung vor Dienstunterbrechung.
- **mediamtxMonitor:** Installer/Uninstaller und Lifecycle-Tests. Übernommen:
  vorhandene fremde Pfade/Dienste als Konflikt behandeln, nicht nebenbei verändern.
- **live-production-engine:** Bootstrap-Installer, systemd- und Prüfskriptstruktur.
  Bestätigt: lokale Python-venv und expliziter Betriebscheck; MediaMTX/Redis und
  andere dortige Abhängigkeiten werden für LiveScore nicht übernommen.

LiveScore verwendet dünne Shell-Einstiege und einen gemeinsamen Python-Installer
mit Standardbibliothek. Das hält Pfadprüfung, Dateiaustausch und Fehlerbehandlung
für Install/Upgrade/Uninstall an einer Stelle. Die venv bleibt an einem stabilen
Laufzeitpfad unter `releases/`; ein `current`-Link vermeidet das nachträgliche
Umschreiben von venv-Shebangs. Es bleibt eine kleine Git-basierte Installation,
keine eigene Paketverwaltung. Systempakete werden als Voraussetzung geprüft und
nicht automatisch aktualisiert; so betrifft ein LiveScore-Upgrade nur LiveScore.
