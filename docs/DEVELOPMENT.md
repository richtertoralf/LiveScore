# Entwicklung und Tests

## Aufbau

LiveScore verwendet Python, FastAPI und Uvicorn mit einem einzelnen Worker.
Die Oberfläche besteht aus lokal ausgeliefertem HTML, CSS und JavaScript ohne
Build-Schritt. Ein zentraler Serverzustand wird als JSON gespeichert;
Browser erhalten vollständige Snapshots über WebSocket.

| Bereich | Aufgabe |
|---|---|
| `livescore/models.py` | Datenmodelle, Validierung und Invarianten |
| `livescore/service.py` | Spielaktionen, Zustandsübergänge und Live-Projektion |
| `livescore/catalog.py` | Veranstaltungen, Auswahl, Import/Export und Migration |
| `livescore/profiles.py`, `static/profiles.js` | Profilbibliothek, Sprachpflege und Anzeigevokabular |
| `livescore/storage.py` | atomare JSON-Speicherung und Prozesssperre |
| `livescore/app.py` | HTTP-Endpunkte, WebSocket und statische Seiten |
| `livescore/auth*.py`, `recovery.py` | Login, Rechte, Passwörter und Auth-Reload |
| `livescore/config.py`, `__main__.py` | Serverkonfiguration und Start |
| `static/` | Browseroberfläche; Übersetzungen in `i18n.js` |
| `tools/deploy.py`, Shell-Einstiege | Installation, Upgrade und Deinstallation |

Die [Arbeitsregeln](../AGENTS.md) gelten für Änderungen. Fachliche Details stehen
im [Datenmodell](DATA_MODEL.md), API-Verträge und Revisionsprüfungen in der [API](API.md).
Start und Serverkonfiguration: [Installation und Betrieb](INSTALLATION.md).

## Unit-Tests

Im Checkout mit eingerichteter `.venv`:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Die Tests prüfen unter anderem Speicherung und Wiederherstellung, erlaubte
Spielaktionen, Score-Undo, die 2:1-Seitenwechsel-Invariante, Import/Export,
Counter und Abschnitte, Auth, Request-Deduplizierung und API-Antworten.
Der Dokumentations-Test vergleicht die vollständige Live-Antwort und den
Score-Request aus `docs/API.md` mit echten API-Aufrufen.

## Browser- und Betriebsprüfungen

```sh
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
.venv/bin/python tests/browser_auth_smoke.py
.venv/bin/python tests/browser_sections_smoke.py
.venv/bin/python tests/browser_profiles_smoke.py
.venv/bin/python tests/deployment_smoke.py
.venv/bin/python tests/auth_recovery_smoke.py
```

Für Browser-Smokes kann ein vorhandener Browser mit `--chromium /pfad/zu/chrome`
angegeben werden. Der fachliche Browsertest benötigt außerdem `curl`.
Die Prüfungen verwenden eigene Datenverzeichnisse und Loopback-Server;
Logs, Browserprofile und Screenshots liegen unter `.test-artifacts/`.
Produktive Event-Dateien werden nicht verwendet.

Browser-Smokes prüfen mobile Ansichten, mehrere Bediener, Offline/Reconnect,
Imports, Endstandbestätigung, Sprachen und Zugriffsrechte. Deployment-Smokes
erstellen echte venvs und prüfen Installation, das CLI-Upgrade von der veröffentlichten
0.1.2 auf 0.2.0, Datenerhalt einschließlich Profilbibliothek und
Deinstallation. Details zur [isolierten Verifikation](INSTALLATION.md#isolierte-verifikation).
Der Recovery-Smoke prüft Passwortänderung mit echtem SIGHUP und weiterlaufenden
Live-Daten; sein systemctl-Stub kontaktiert keine Hostdienste.

`browser_sections_smoke.py` prüft neun Profilvarianten in EN/DE/CS mit zwei Browsern:
zwei Halbzeiten, drei Runden, fünf Sätze, eigene Begriffe, mehr als zwei Halbzeiten,
einen einzelnen Abschnitt und kein Profil. Geprüft werden Abschnittspausen,
Korrektur, Dialogabbruch, konkurrierende Änderungen und direktes Wiederöffnen.

`browser_profiles_smoke.py` prüft die vollständige GUI-Pflege ohne aktive Veranstaltung,
Speicherkonflikte zwischen Admins, alle Sprachfelder und Operatorrechte, Übernahme einer
Veranstaltungskopie, unabhängige Bibliotheksänderungen, Counterhistorien und Export.

Unter Windows sind manueller Start und Dateisperren implementiert;
die bisher dokumentierten praktischen Prüfungen erfolgten unter Linux/Chromium.

## Offene Produktentscheidungen

Die folgenden Dokumente beschreiben Entscheidungen beziehungsweise Vorschläge,
keine zusätzlichen implementierten Funktionen:

- [Einzelnes Spiel zurücksetzen und Paarung korrigieren](issues/issue-match-reset.md)
- [Spieluhr: Entscheidung und Zukunftsthema](issues/issue-match-clock.md)

Die [historische Referenzprüfung](REFERENZEN.md) dokumentiert Projektmuster und
die damalige Portwahl; sie ist keine Betriebsvoraussetzung.

Die umgesetzte Entscheidung zu [Abschnittspausen und Wiederöffnen](issues/issue-remove-pause.md)
beschreibt auch die Kompatibilitätsauswirkungen für ältere API-Clients.

Verifikation von 0.2.0 unter Linux: **151 Unit-Tests bestanden**, Browser-Smokes für
Bedienung, Auth, neun Abschnittsprofile in EN/DE/CS und die vollständige Profilpflege
mit zwei Admins und Operator. Ein zusätzlicher CS-Lauf prüfte die bereinigte
Textdarstellung. Mobile und Desktop-Screenshots wurden visuell geprüft. Das echte
CLI-Upgrade von 0.1.2 auf 0.2.0 erhielt Konfiguration, Passwörter, Veranstaltungsdaten
und Profilbibliothek unverändert. Native Windows- und Host-systemd-Prüfungen sind
nicht Teil dieser Verifikation.
