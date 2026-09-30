"""Einzelne portable States; nur Auswahl und ihre Kennung liegen separat."""
import asyncio
import hashlib
import hmac
import re
import secrets
import unicodedata
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter

from . import storage
from .models import Event, ID, Model, State
from .service import Conflict, Service, current_match, persist


class Selection(Model):
    active_event_id: ID | None = None
    selection_token: UUID = Field(default_factory=uuid4)


class CatalogCommand(Model):
    request_id: UUID
    catalog_session: UUID


class CreateEvent(CatalogCommand):
    event: Event


class SelectEvent(CatalogCommand):
    event_id: ID
    selection_token: UUID


class ImportPreview(Model):
    json_text: str = Field(max_length=10 * 1024 * 1024)
    event_id: ID | None = None


class ImportEvent(ImportPreview, CatalogCommand):
    preview_token: str = Field(pattern=r'^[0-9a-f]{64}$')
    as_new: bool = Field(default=False, strict=True)


class ReplaceEvent(ImportPreview, CatalogCommand):
    event_id: ID
    preview_token: str = Field(pattern=r'^[0-9a-f]{64}$')


def event_id_for(state):
    event = state.event
    name = event.name if event else 'Veranstaltung'
    year = str(event.date_from.year) if event else ''
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')[:60].rstrip('-') or 'veranstaltung'
    if year and year not in slug:
        slug += '-' + year
    return slug


def save_selection(path, selection):
    checked = Selection.model_validate(selection.model_dump())
    storage.atomic_write(path, checked.model_dump_json(indent=2) + '\n')


class Catalog(Service):
    def __init__(self, directory, legacy):
        # The application holds the catalogue and legacy process leases first.
        self.directory = directory
        self.events_dir = directory / 'events'
        self.selection_path = directory / 'active-event.json'
        self.states = {}
        if self.events_dir.is_symlink():
            raise ValueError('events darf kein symbolischer Link sein.')
        for path in sorted(self.events_dir.glob('*.json')):
            TypeAdapter(ID).validate_python(path.stem)
            if path.is_symlink():
                raise ValueError('Veranstaltungsdateien dürfen keine symbolischen Links sein.')
            self.states[path.stem] = storage.load(path)
        if self.selection_path.exists():
            self.selection = Selection.model_validate_json(self.selection_path.read_text(encoding='utf-8'))
        else:
            self.selection = Selection()
            if legacy.exists():
                state = storage.load(legacy)
                event_id = event_id_for(state)
                if self.states and (set(self.states) != {event_id} or self.states[event_id] != state):
                    raise ValueError('Legacy-Datei und bestehender Katalog sind nicht eindeutig zuzuordnen. Original bleibt unverändert.')
                if event_id not in self.states:
                    storage.save(self.event_path(event_id), state)
                self.states[event_id] = state
                self.selection.active_event_id = event_id
            save_selection(self.selection_path, self.selection)
        active = self.selection.active_event_id
        if active is not None and active not in self.states:
            raise ValueError('Aktive Veranstaltung fehlt. Keine automatische Rücksetzung.')
        self.stream_id = str(uuid4())
        self.stream_revision = 0
        self.preview_secret = secrets.token_bytes(32)
        self.receipts = {}
        super().__init__(self.event_path(active) if active else None, self.states[active] if active else State())

    def event_path(self, event_id):
        TypeAdapter(ID).validate_python(event_id)
        return self.events_dir / (event_id + '.json')

    def listing(self):
        items = []
        for event_id, state in self.states.items():
            event = state.event
            items.append(dict(id=event_id, event=event.model_dump(mode='json') if event else None,
                              participants=len(state.participants), play_areas=len(state.play_areas),
                              matches=len(state.matches), referees=len(state.referees)))
        return dict(active_event_id=self.selection.active_event_id,
                    selection_token=str(self.selection.selection_token),
                    items=sorted(items, key=lambda item: ((item['event'] or {}).get('date_from', ''), item['id'])))

    def view(self):
        return dict(super().view(), active_event_id=self.selection.active_event_id,
                    selection_token=str(self.selection.selection_token), catalog=self.listing(),
                    stream_id=self.stream_id, stream_revision=self.stream_revision)

    def changed(self):
        if self.selection.active_event_id:
            self.states[self.selection.active_event_id] = self.state
        self.stream_revision += 1
        return super().changed()

    def check_context(self, command):
        if (self.selection.active_event_id is None or command.event_id != self.selection.active_event_id
                or command.selection_token != self.selection.selection_token):
            raise Conflict('Veranstaltung wurde gewechselt oder ist nicht ausgewählt. Bitte aktuellen Stand laden.')

    def available_id(self, base):
        candidate, number = base, 2
        while candidate in self.states or self.event_path(candidate).exists():
            candidate = base[:70] + '-' + str(number)
            number += 1
        return candidate

    def validate_import(self, command):
        if len(command.json_text.encode('utf-8')) > 10 * 1024 * 1024:
            raise ValueError('Importdatei ist größer als 10 MiB.')
        state = State.model_validate_json(command.json_text)
        if state.event is None:
            raise ValueError('Import benötigt Veranstaltungsdaten mit Name und Zeitraum.')
        return state, command.event_id or event_id_for(state)

    def preview_token(self, state, event_id):
        text = event_id + '\n' + state.model_dump_json()
        return hmac.new(self.preview_secret, text.encode(), hashlib.sha256).hexdigest()

    def preview(self, command):
        state, event_id = self.validate_import(command)
        return dict(event_id=event_id, event=state.event.model_dump(mode='json'),
                    participants=len(state.participants), referees=len(state.referees),
                    play_areas=len(state.play_areas), matches=len(state.matches),
                    collision=event_id in self.states or self.event_path(event_id).exists(),
                    preview_token=self.preview_token(state, event_id))

    async def catalog_apply(self, operation, command):
        signature = hashlib.sha256((operation + command.model_dump_json()).encode()).hexdigest()
        async with self.lock:
            if str(command.catalog_session) != self.stream_id:
                raise Conflict('Server wurde neu gestartet. Katalog prüfen und Aktion erneut vorbereiten.')
            previous = self.receipts.get(str(command.request_id))
            if previous:
                if previous[0] != signature:
                    raise Conflict('Request-ID bereits für eine andere Katalogaktion verwendet.')
                return dict(self.view(), created_event_id=previous[1])
            created = None
            if operation == 'select':
                if command.selection_token != self.selection.selection_token:
                    raise Conflict('Aktive Veranstaltung wurde zwischenzeitlich gewechselt. Bitte Anzeige prüfen.')
                if command.event_id not in self.states:
                    raise Conflict('Veranstaltung nicht gefunden.')
                if command.event_id == self.selection.active_event_id:
                    return self.view()
                match = current_match(self.state)
                if match and match.status in ('ready', 'live', 'paused'):
                    raise Conflict('Aktuell ist ein Spiel vorbereitet oder aktiv. Beende das Spiel bzw. setze die Vorbereitung zurück, bevor du die Veranstaltung wechselst.')
                selection = Selection(active_event_id=command.event_id)
                cancelled = await persist(save_selection, self.selection_path, selection)
                self.selection = selection
                self.path = self.event_path(command.event_id)
                self.state = self.states[command.event_id]
            elif operation == 'replace':
                # Admin-Reset: vorhandene Veranstaltung vollständig durch die geprüfte Importdatei ersetzen.
                state, desired = self.validate_import(command)
                if not hmac.compare_digest(command.preview_token, self.preview_token(state, desired)):
                    raise Conflict('Import-Vorschau ist nicht mehr gültig. Datei erneut prüfen.')
                if desired not in self.states:
                    raise Conflict('Veranstaltung nicht gefunden.')
                active = desired == self.selection.active_event_id
                match = current_match(self.state) if active else None
                if match and match.status in ('ready', 'live', 'paused'):
                    raise Conflict('Aktuell ist ein Spiel vorbereitet oder aktiv. Beende das Spiel bzw. setze die Vorbereitung zurück, bevor du die Veranstaltung ersetzt.')
                # Revision bleibt monoton; eine neue Auswahlkennung macht offene Aktionen alter Anzeigen ungültig.
                state.revision = max(state.revision, self.states[desired].revision) + 1
                cancelled = False
                if active:
                    selection = Selection(active_event_id=desired)
                    cancelled = await persist(save_selection, self.selection_path, selection)
                    self.selection = selection
                cancelled = await persist(storage.save, self.event_path(desired), state) or cancelled
                self.states[desired] = state
                if active:
                    self.state = state
            else:
                if operation == 'create':
                    state = State(event=command.event)
                    created = self.available_id(event_id_for(state))
                else:
                    state, desired = self.validate_import(command)
                    if not hmac.compare_digest(command.preview_token, self.preview_token(state, desired)):
                        raise Conflict('Import-Vorschau ist nicht mehr gültig. Datei erneut prüfen.')
                    if not command.as_new and (desired in self.states or self.event_path(desired).exists()):
                        raise Conflict('Eine Veranstaltung mit dieser ID existiert bereits. Als neue Veranstaltung importieren.')
                    created = self.available_id(desired) if command.as_new else desired
                cancelled = await persist(storage.save, self.event_path(created), state)
                self.states[created] = state
            self.receipts[str(command.request_id)] = (signature, created)
            result = dict(self.changed(), created_event_id=created)
            if cancelled:
                raise asyncio.CancelledError
            return result
