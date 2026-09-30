import asyncio
from datetime import datetime, timezone
import hashlib
import json
import re
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


# Bekannte Bezeichnungen der Spielleitung → stabiler Code und englische Anzeige.
# Unbekannte Werte werden nicht übersetzt (code/label_en null). Vergleich ohne Groß-/Kleinschreibung.
KNOWN_TERMS = {
    "gruppenphase": ("group_stage", "Group stage"),
    "play-offs": ("play_offs", "Play-offs"),
    "semi final #1": ("semi_final_1", "Semi-final 1"),
    "semi final #2": ("semi_final_2", "Semi-final 2"),
    "match for place 5th": ("fifth_place_match", "5th-place match"),
    "bronze medal match": ("bronze_medal_match", "Bronze medal match"),
    "gold medal match": ("gold_medal_match", "Gold medal match"),
}
GROUP = re.compile(r"^gruppe ([a-z])$")
# Abschnittsbezeichnungen, die bei genau zwei Abschnitten Halbzeiten bedeuten.
HALF_LABELS = {"halbzeit", "half", "poločas"}
HALF_TIME_LABELS = {"not_started": "Not started", "first_half": "1st half", "half_time": "Half-time",
                    "second_half": "2nd half", "full_time": "Full-time"}


def term(value, label_en=""):
    """Originalwert, Code und englisches Label; null, wenn keine Angabe vorhanden ist."""
    if not value:
        return None
    key = value.casefold()
    group = GROUP.match(key)
    code, label = KNOWN_TERMS.get(key) or (
        (f"group_{group[1]}", f"Group {group[1].upper()}") if group else (None, None))
    return dict(code=code, name=value, label_en=label_en or label)


def halves(profile):
    return bool(profile and profile.periods == 2 and profile.period_label.casefold() in HALF_LABELS)


def period_info(match, profile):
    use_halves = halves(profile)
    if match.status in ("scheduled", "ready"):
        code = "not_started"
    elif match.status == "finished":
        code = "full_time" if use_halves else "finished"
    elif match.intermission:
        code = "half_time" if use_halves else f"intermission_after_{match.period}"
    else:
        code = ("first_half", "second_half")[match.period - 1] if use_halves else f"period_{match.period}"
    return dict(number=match.period, intermission=match.intermission, code=code,
                label_en=HALF_TIME_LABELS[code] if use_halves else None)


def live_view(state):
    match = current_match(state)
    result = dict(status="idle", revision=state.revision, match_id=None,
                  play_area=None, left=None, right=None, officials=[], period=None,
                  period_info=None, stage=None, round=None)
    if match is None:
        return result
    profile = state.event.sport_profile if state.event else None
    result.update(status=match.status, match_id=match.id, period=match.period,
                  play_area=next(a.model_dump() for a in state.play_areas if a.id == match.play_area_id),
                  period_info=period_info(match, profile),
                  stage=term(match.stage, match.stage_label), round=term(match.round, match.round_label))
    referees = {referee.id: referee for referee in state.referees}
    # Officials sind im Modell ausschließlich Einträge der Referee-Liste; position = Reihenfolge im Spiel.
    result["officials"] = [dict(referees[referee_id].model_dump(), position=index, role="referee",
                                role_label_en="Referee")
                           for index, referee_id in enumerate(match.officials, start=1)]
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
                    # Ältere Clients kennen diese Felder nicht und dürfen sie nicht löschen.
                    for key in ("stage", "stage_label", "round_label"):
                        if old and key not in item.model_fields_set:
                            setattr(item, key, getattr(old, key))
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
            # Beendete Spiele dürfen erneut ausgewählt werden, um sie mit `reopen` fortzuführen.
            if selected is None or selected.status not in ("scheduled", "finished"):
                raise Conflict("Bitte ein geplantes oder beendetes Spiel auswählen.")
            state.active_match_id = selected.id
            return {"type": "match_selected", "match_id": selected.id}
        if match is None or command.match_id != match.id:
            raise Conflict("Das angezeigte Spiel ist nicht mehr ausgewählt.")
        allowed = {
            "prepare": {"scheduled", "ready"}, "unprepare": {"ready"},
            "start": {"ready"}, "score": {"live", "paused"},
            "counter": {"live", "paused"}, "period": {"live", "paused"},
            "intermission": {"live", "paused"},
            "pause": {"live"}, "resume": {"paused"},
            "switch-sides": {"ready", "live", "paused"},
            "undo": {"live", "paused"}, "finish": {"live", "paused"},
            "reopen": {"finished"},
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
            match.intermission = False
            event.update(type="period_changed", period=match.period)
        elif operation == "intermission":
            profile = state.event.sport_profile
            if command.intermission == match.intermission:
                raise Conflict("Pause zwischen Abschnitten ist bereits so gesetzt.")
            if command.intermission and (not profile or match.period >= profile.periods):
                raise Conflict("Pause zwischen Abschnitten nur vor dem letzten Abschnitt.")
            match.intermission = command.intermission
            event.update(type="intermission_started" if match.intermission else "intermission_ended",
                         period=match.period)
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
            match.intermission = False
            event["type"] = "match_finished"
        elif operation == "reopen":
            # Korrektur eines versehentlichen Spielendes: Score, Seiten und Abschnitt bleiben,
            # das Spiel wird bewusst in PAUSE fortgesetzt.
            match.status = "paused"
            event["type"] = "match_reopened"
        if operation not in ("score", "counter"):
            match.control_revision += 1
        return event
