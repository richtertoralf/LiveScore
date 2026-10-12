import asyncio
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import uuid4

from . import storage
from .models import ActionEvent, Event, Match, MatchPlan, Participant, PlayArea, Referee, SportProfile, State
from .profiles import display_profile, structure


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


def term(value, label_en=""):
    """Originalwert, Code und englisches Label; null, wenn keine Angabe vorhanden ist."""
    if not value:
        return None
    key = value.casefold()
    group = GROUP.match(key)
    code, label = KNOWN_TERMS.get(key) or (
        (f"group_{group[1]}", f"Group {group[1].upper()}") if group else (None, None))
    return dict(code=code, name=value, label_en=label_en or label)


def period_info(match, profile):
    if match.status in ("scheduled", "ready"):
        code = "not_started"
    elif match.status == "finished":
        code = "finished"
    elif match.intermission:
        code = f"intermission_after_{match.period}"
    else:
        code = f"period_{match.period}"
    display = display_profile(profile or SportProfile())
    period_labels = {lang: (f"{text['period_label']} {match.period}" if lang == 'en'
                            else f"{match.period}. {text['period_label']}")
                     for lang, text in display['translations'].items()}
    labels = {lang: text['break_label'] if match.intermission else period_labels[lang]
              for lang, text in display['translations'].items()}
    return dict(number=match.period, total=profile.periods if profile else 1,
                intermission=match.intermission, code=code, period_labels=period_labels,
                label_en=labels['en'], labels=labels)


def live_view(state):
    match = current_match(state)
    profile = state.event.sport_profile if state.event else None
    settings = profile or SportProfile()
    vocabulary = display_profile(settings) if state.event else None
    if vocabulary:
        for labels in vocabulary['translations'].values():
            if settings.score_mode != 'none':
                labels['score_label'] = labels['score_label'] or state.event.score_label
    result = dict(status="idle", revision=state.revision, match_id=None,
                  play_area=None, left=None, right=None, officials=[] if settings.show_officials else None, period=None,
                  period_info=None, stage=None, round=None, sport_profile=vocabulary,
                  pairing_confirmed=False,
                  display=dict(score=settings.score_mode != "none", score_mode=settings.score_mode,
                               sets=settings.sets_enabled, counters=[c.id for c in settings.counters if c.enabled],
                               details=settings.show_details, officials=settings.show_officials) if state.event else None)
    if match is None:
        return result
    # Legacy paused states remain editable; the live contract describes an ongoing match.
    result.update(status="live" if match.status == "paused" else match.status, match_id=match.id, period=match.period,
                  play_area=next(a.model_dump() for a in state.play_areas if a.id == match.play_area_id),
                  period_info=period_info(match, profile),
                  stage=term(match.stage, match.stage_label) if settings.show_details else None,
                  round=term(match.round, match.round_label) if settings.show_details else None,
                  pairing_confirmed=match.side_l is not None and match.side_r is not None)
    referees = {referee.id: referee for referee in state.referees}
    # Officials sind im Modell ausschließlich Einträge der Referee-Liste; position = Reihenfolge im Spiel.
    result["officials"] = [dict(referees[referee_id].model_dump(), position=index, role="referee",
                                role_label_en="Referee")
                           for index, referee_id in enumerate(match.officials, start=1)] if settings.show_officials else None
    for key, pid in (("left", match.side_l), ("right", match.side_r)):
        if pid:
            participant = next(p for p in state.participants if p.id == pid)
            definitions = [c for c in settings.counters if c.enabled]
            counters = {d.id: counter_value(match, d, pid) for d in definitions}
            result[key] = dict(id=pid, name=participant.name, short_name=participant.short_name,
                               country_code=participant.country_code,
                               score=match.scores[pid] if settings.score_mode != 'none' else None,
                               counters=counters,
                               counter_states={d.id: counter_level(d, counters[d.id]) for d in definitions},
                               sets_won=match.sets_won.get(pid) if settings.sets_enabled else None,
                               period_scores=({p: values[pid] for p, values in match.period_scores.items()}
                                              if settings.score_mode == 'period' else None),
                               role=next((dict(id=definition.id, labels=definition.labels) for role, definition in settings.roles.items()
                                          if getattr(match, role) == pid), None))
    return result


def snapshot(state):
    data = state.model_dump(mode="json", exclude={"events"})
    data["live"] = live_view(state)
    match = current_match(state)
    data["can_undo"] = bool(match and match.status in ("live", "paused") and any(
        not e.undone for e in state.point_events(match.id)))
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
        result = snapshot(self.state)
        result['live'] = self.live()
        return result

    def live(self):
        return live_view(self.state)

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
            if operation not in ("score", "counter", "sets") and command.expected_revision != self.state.revision:
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

    def change_profile(self, state, profile):
        old = state.event.sport_profile
        if structure(old) != structure(profile):
            if any(m.status != 'scheduled' for m in state.matches):
                raise Conflict('Erfassungsstruktur ist nach Vorbereitung oder Spielbeginn festgelegt. Bezeichnungen und Anzeigeoptionen bleiben bearbeitbar.')
            # Only unstarted matches: replace empty initialized histories, never real results.
            if any(value for m in state.matches for values in m.counters.values()
                   for history in values.values() for value in history.values()):
                raise Conflict('Vorhandene Counterwerte dürfen durch Profiländerungen nicht verloren gehen.')
            for match in state.matches:
                match.counters = {}
                match.period_scores = {}
                match.sets_won = {}
                initialize_period(match, profile)
        state.event.sport_profile = profile

    def mutate(self, state, operation, command):
        match = current_match(state)
        if operation.startswith("config/"):
            if operation == 'config/sport-profile':
                if state.event is None:
                    raise Conflict('Keine Veranstaltung ausgewählt.')
                if set(command.data) != {'sport_profile'}:
                    raise ValueError('invalid_input')
                profile = SportProfile.model_validate(command.data['sport_profile']) if command.data['sport_profile'] is not None else None
                self.change_profile(state, profile)
                return {'type': 'configuration_changed'}
            if match and match.status in ("ready", "live", "paused"):
                raise Conflict("Konfiguration ist während eines vorbereiteten oder laufenden Spiels gesperrt.")
            kind = operation.split("/")[1]
            if kind == "event":
                item = Event.model_validate(command.data)
                if state.event:
                    if "sport_profile" not in item.model_fields_set:
                        item.sport_profile = state.event.sport_profile
                    self.change_profile(state, item.sport_profile)
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
                    if old:
                        # Never reuse a control token after resetting/editing the same match.
                        item.control_revision = old.control_revision
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
            "sets": {"live", "paused"},
            "counter": {"live", "paused"}, "period": {"live", "paused"},
            "intermission": {"live", "paused"},
            "switch-sides": {"ready", "live", "paused"},
            "undo": {"live", "paused"}, "finish": {"live", "paused"},
            "reopen": {"finished"},
            "reset": {"ready", "live", "paused", "finished"},
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
            match.period_scores = ({"1": dict(match.scores)} if state.event.sport_profile
                                   and state.event.sport_profile.score_mode == "period" else {})
            match.sets_won = (dict(match.scores) if state.event.sport_profile
                              and state.event.sport_profile.sets_enabled else {})
            initialize_period(match, state.event.sport_profile)
            match.status = "ready"
        elif operation in ("unprepare", "reset"):
            match.status = "scheduled"
            match.side_l = match.side_r = None
            match.scores = {}
            match.counters = {}
            match.period_scores = {}
            match.sets_won = {}
            match.period = 1
            match.intermission = False
            if operation == "reset":
                event["type"] = "match_reset"
        elif operation == "start":
            match.status = "live"
            event["type"] = "match_started"
        elif operation in ("score", "sets"):
            if command.control_revision != match.control_revision:
                raise Conflict("Spielzustand oder Seiten wurden geändert. Bitte Anzeige prüfen.")
            pid = match.side_l if command.side == "L" else match.side_r
            if command.participant_id != pid:
                raise Conflict("Teilnehmer steht nicht mehr auf dieser Seite.")
            profile = state.event.sport_profile or SportProfile()
            if operation == "score" and (profile.score_mode == "none" or abs(command.delta) not in profile.score_steps):
                raise ValueError("invalid_input")
            if operation == "sets" and not profile.sets_enabled:
                raise Conflict("Satzerfassung ist im Sportprofil deaktiviert.")
            if operation == "sets" and not match.sets_won:
                match.sets_won = {participant: 0 for participant in match.scores}
            scores = match.sets_won if operation == "sets" else match.scores
            if scores[pid] + command.delta < 0:
                raise Conflict("Score darf nicht negativ werden.")
            scores[pid] += command.delta
            if operation == "score" and profile.score_mode == "period":
                match.period_scores[str(match.period)] = dict(match.scores)
                event['period'] = match.period
            event.update(participant_id=pid, delta=command.delta)
        elif operation == "counter":
            if command.control_revision != match.control_revision or command.period != match.period:
                raise Conflict("Spielzustand, Seiten oder Abschnitt wurden geändert. Bitte Anzeige prüfen.")
            profile = state.event.sport_profile
            definition = next((c for c in profile.counters if c.id == command.counter_id), None) if profile else None
            if definition is None or not definition.enabled or command.participant_id not in match.scores:
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
            if profile.score_mode == "period":
                match.scores = {pid: 0 for pid in match.scores}
                match.period_scores[str(match.period)] = dict(match.scores)
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
            last = next((e for e in state.point_events(match.id) if not e.undone), None)
            if last is None:
                raise Conflict("Keine Punkte- oder Satzaktion zum Zurücknehmen vorhanden.")
            if last.type == "sets":
                match.sets_won[last.participant_id] -= last.delta
            elif state.event.sport_profile and state.event.sport_profile.score_mode == "period":
                match.period_scores[str(last.period)][last.participant_id] -= last.delta
                match.scores = dict(match.period_scores[str(match.period)])
            else:
                match.scores[last.participant_id] -= last.delta
            last.undone = True
            event.update(participant_id=last.participant_id, delta=-last.delta, undo_of=last.id, period=last.period)
        elif operation == "finish":
            match.status = "finished"
            match.intermission = False
            event["type"] = "match_finished"
        elif operation == "reopen":
            # Wiederöffnen erhält die Wettkampfdaten und benötigt keinen weiteren Resume-Schritt.
            match.status = "live"
            event["type"] = "match_reopened"
        if operation not in ("score", "counter", "sets"):
            match.control_revision += 1
        return event
