import asyncio
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from . import storage
from .models import ActionEvent, Event, Match, MatchPlan, Participant, PlayArea, Referee, State


class Conflict(Exception):
    pass


def current_match(state):
    return next((m for m in state.matches if m.id == state.active_match_id), None)


def counter_value(match, definition, participant_id):
    history = match.counters.get(definition.id, {}).get(participant_id, {})
    if definition.reset_each_period:
        return history.get(str(match.period), 0)
    # A missing period in a portable sparse state inherits the last known value.
    previous = max((int(p) for p in history if int(p) <= match.period), default=0)
    return history.get(str(previous), 0)


def counter_level(definition, value):
    if definition.critical_at is not None and value >= definition.critical_at:
        return "critical"
    if definition.warning_at is not None and value >= definition.warning_at:
        return "warning"
    return "normal"


def initialize_period(match, profile):
    if profile:
        for definition in profile.counters:
            for pid in (match.participant_1, match.participant_2):
                if pid:
                    value = counter_value(match, definition, pid)
                    match.counters.setdefault(definition.id, {}).setdefault(pid, {})[str(match.period)] = value


def live_view(state):
    match = current_match(state)
    result = dict(status="idle", revision=state.revision, match_id=None,
                  play_area=None, left=None, right=None, officials=[], period=None)
    if match is None:
        return result
    result.update(status=match.status, match_id=match.id, period=match.period,
                  play_area=next(a.model_dump() for a in state.play_areas if a.id == match.play_area_id))
    referees = {referee.id: referee for referee in state.referees}
    result["officials"] = [referees[referee_id].model_dump() for referee_id in match.officials]
    for key, pid in (("left", match.side_l), ("right", match.side_r)):
        if pid:
            participant = next(p for p in state.participants if p.id == pid)
            definitions = state.event.sport_profile.counters if state.event.sport_profile else []
            counters = {d.id: counter_value(match, d, pid) for d in definitions}
            result[key] = dict(id=pid, name=participant.name, short_name=participant.short_name,
                               country_code=participant.country_code, score=match.scores[pid],
                               counters=counters,
                               counter_states={d.id: counter_level(d, counters[d.id]) for d in definitions})
    return result


def snapshot(state):
    data = state.model_dump(mode="json", exclude={"events"})
    data["live"] = live_view(state)
    match = current_match(state)
    data["can_undo"] = bool(match and match.status in ("live", "paused") and any(
        e.type == "score" and e.match_id == match.id and not e.undone for e in state.events))
    return data


async def persist(write, *args):
    """Schreibvorgang auch bei Request-Abbruch abschließen, bevor das Lock frei wird."""
    task = asyncio.create_task(asyncio.to_thread(write, *args))
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        await task
        return True


class Service:
    def __init__(self, path, state=None):
        self.path = path
        self.state = storage.load(path) if state is None else state
        self.lock = asyncio.Lock()
        self.subscribers = set()

    def subscribe(self):
        # All queue access runs on the ASGI loop, without intervening awaits.
        queue = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        queue.put_nowait(self.view())
        return queue

    def view(self):
        return snapshot(self.state)

    def check_context(self, command):
        """Der Veranstaltungskatalog ergänzt die Prüfung der aktiven Auswahl."""

    def changed(self):
        data = self.view()
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(data)
        return data

    async def apply(self, operation, command):
        payload = command.model_dump(mode="json")
        signature = hashlib.sha256(json.dumps([operation, payload], sort_keys=True).encode()).hexdigest()
        async with self.lock:
            self.check_context(command)
            previous = next((e for e in self.state.events if e.request_id == str(command.request_id)), None)
            if previous:
                if previous.signature != signature:
                    raise Conflict("Request-ID wurde bereits für eine andere Aktion verwendet.")
                return self.view()
            if operation not in ("score", "counter") and command.expected_revision != self.state.revision:
                raise Conflict("Zustand wurde inzwischen geändert. Bitte Anzeige prüfen und erneut bedienen.")
            candidate = self.state.model_copy(deep=True)
            event_data = self.mutate(candidate, operation, command)
            candidate.revision += 1
            candidate.events.append(ActionEvent(
                id=str(uuid4()), type=event_data.pop("type", operation),
                timestamp=datetime.now(timezone.utc), revision=candidate.revision,
                request_id=str(command.request_id), signature=signature, **event_data))
            candidate = State.model_validate(candidate.model_dump())
            cancelled = await persist(storage.save, self.path, candidate)
            self.state = candidate
            data = self.changed()
            if cancelled:
                raise asyncio.CancelledError
            return data

    def mutate(self, state, operation, command):
        match = current_match(state)
        if operation.startswith("config/"):
            if match and match.status in ("ready", "live", "paused"):
                raise Conflict("Konfiguration ist während eines vorbereiteten oder laufenden Spiels gesperrt.")
            kind = operation.split("/")[1]
            if kind == "event":
                item = Event.model_validate(command.data)
                if state.event:
                    if "sport_profile" not in item.model_fields_set:
                        item.sport_profile = state.event.sport_profile
                    if item.sport_profile != state.event.sport_profile and any(m.status != "scheduled" for m in state.matches):
                        raise Conflict("Sportprofil kann nach Spielbeginn nicht geändert werden.")
                state.event = item
            else:
                model, key = {"play-areas": (PlayArea, "play_areas"),
                              "participants": (Participant, "participants"),
                              "referees": (Referee, "referees"),
                              "matches": (MatchPlan, "matches")}[kind]
                item = model.model_validate(command.data)
                collection = getattr(state, key)
                old = next((i for i in collection if i.id == item.id), None)
                if kind == "participants" and old and "country_code" not in item.model_fields_set:
                    item.country_code = old.country_code
                if kind == "matches":
                    if old and old.status != "scheduled":
                        raise Conflict("Nur geplante Spiele können bearbeitet werden.")
                    if old and "officials" not in item.model_fields_set:
                        item.officials = list(old.officials)
                    item = Match(**item.model_dump())
                    initialize_period(item, state.event.sport_profile if state.event else None)
                if old:
                    collection[collection.index(old)] = item
                else:
                    collection.append(item)
            return {"type": "configuration_changed"}
        if operation == "select":
            if match and match.status in ("ready", "live", "paused"):
                raise Conflict("Aktuelles Spiel zuerst beenden oder Vorbereitung zurücknehmen.")
            selected = next((m for m in state.matches if m.id == command.match_id), None)
            if selected is None or selected.status != "scheduled":
                raise Conflict("Bitte ein geplantes Spiel auswählen.")
            state.active_match_id = selected.id
            return {"type": "match_selected", "match_id": selected.id}
        if match is None or command.match_id != match.id:
            raise Conflict("Das angezeigte Spiel ist nicht mehr ausgewählt.")
        allowed = {
            "prepare": {"scheduled", "ready"}, "unprepare": {"ready"},
            "start": {"ready"}, "score": {"live", "paused"},
            "counter": {"live", "paused"}, "period": {"live", "paused"},
            "pause": {"live"}, "resume": {"paused"},
            "switch-sides": {"ready", "live", "paused"},
            "undo": {"live", "paused"}, "finish": {"live", "paused"},
        }
        if match.status not in allowed[operation]:
            raise Conflict("Diese Aktion ist im aktuellen Spielzustand nicht erlaubt.")
        event = {"match_id": match.id}
        if operation == "prepare":
            match.participant_1 = command.participant_1
            match.participant_2 = command.participant_2
            match.side_l = command.side_l
            match.side_r = command.side_r
            match.scores = {command.participant_1: 0, command.participant_2: 0}
            match.counters = {}
            initialize_period(match, state.event.sport_profile)
            match.status = "ready"
        elif operation == "unprepare":
            match.status = "scheduled"
            match.side_l = match.side_r = None
            match.scores = {}
        elif operation == "start":
            match.status = "live"
            event["type"] = "match_started"
        elif operation == "score":
            if command.control_revision != match.control_revision:
                raise Conflict("Spielzustand oder Seiten wurden geändert. Bitte Anzeige prüfen.")
            pid = match.side_l if command.side == "L" else match.side_r
            if command.participant_id != pid:
                raise Conflict("Teilnehmer steht nicht mehr auf dieser Seite.")
            if match.scores[pid] + command.delta < 0:
                raise Conflict("Score darf nicht negativ werden.")
            match.scores[pid] += command.delta
            event.update(participant_id=pid, delta=command.delta)
        elif operation in ("pause", "resume"):
            match.status = "paused" if operation == "pause" else "live"
        elif operation == "counter":
            if command.control_revision != match.control_revision or command.period != match.period:
                raise Conflict("Spielzustand, Seiten oder Abschnitt wurden geändert. Bitte Anzeige prüfen.")
            profile = state.event.sport_profile
            definition = next((c for c in profile.counters if c.id == command.counter_id), None) if profile else None
            if definition is None or command.participant_id not in match.scores:
                raise Conflict("Unbekannter Counter oder Teilnehmer dieses Spiels.")
            value = counter_value(match, definition, command.participant_id) + command.delta
            if value < 0:
                raise Conflict("Counter darf nicht negativ werden.")
            match.counters.setdefault(definition.id, {}).setdefault(command.participant_id, {})[str(match.period)] = value
            event.update(participant_id=command.participant_id, counter_id=definition.id,
                         period=match.period, delta=command.delta)
        elif operation == "period":
            profile = state.event.sport_profile
            if not profile or command.period != match.period + 1 or command.period > profile.periods:
                raise Conflict("Nur der nächste konfigurierte Abschnitt kann gestartet werden.")
            initialize_period(match, profile)
            for definition in profile.counters:
                for pid in match.scores:
                    value = 0 if definition.reset_each_period else counter_value(match, definition, pid)
                    match.counters[definition.id][pid][str(command.period)] = value
            match.period = command.period
            event.update(type="period_changed", period=match.period)
        elif operation == "switch-sides":
            match.side_l, match.side_r = match.side_r, match.side_l
            event["type"] = "side_switch"
        elif operation == "undo":
            last = next((e for e in reversed(state.events)
                         if e.match_id == match.id and e.type == "score" and not e.undone), None)
            if last is None:
                raise Conflict("Keine Score-Aktion zum Zurücknehmen vorhanden.")
            match.scores[last.participant_id] -= last.delta
            last.undone = True
            event.update(participant_id=last.participant_id, delta=-last.delta, undo_of=last.id)
        elif operation == "finish":
            match.status = "finished"
            event["type"] = "match_finished"
        if operation not in ("score", "counter"):
            match.control_revision += 1
        return event
