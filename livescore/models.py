from datetime import date as Date, time as Time, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
Text = Annotated[str, Field(min_length=1, max_length=200)]
Count = Annotated[int, Field(strict=True, ge=0)]
Status = Literal["scheduled", "ready", "live", "paused", "finished"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CounterDefinition(Model):
    id: ID
    label: Text
    scope: Literal["participant"] = "participant"
    reset_each_period: bool = Field(default=True, strict=True)
    warning_at: Count | None = None
    critical_at: Count | None = None
    warning_label: str = Field(default="", max_length=200)
    critical_label: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def thresholds(self):
        if self.warning_at is not None and self.critical_at is not None and self.warning_at >= self.critical_at:
            raise ValueError("Warnschwelle muss unter der kritischen Schwelle liegen.")
        return self


class SportProfile(Model):
    sport: Text
    ruleset: str = Field(default="", max_length=200)
    periods: int = Field(default=1, strict=True, ge=1)
    period_label: Text = "Abschnitt"
    counters: list[CounterDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_counters(self):
        if len({c.id for c in self.counters}) != len(self.counters):
            raise ValueError("Counter-IDs müssen eindeutig sein.")
        return self


class Event(Model):
    name: Text
    date_from: Date
    date_to: Date
    location: str = Field(default="", max_length=200)
    logo_path: str = Field(default="", max_length=500)
    score_label: Text = "Score"
    sport_profile: SportProfile | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.date_to < self.date_from:
            raise ValueError("Enddatum liegt vor dem Startdatum.")
        return self


class PlayArea(Model):
    id: ID
    label: Text


class CountryModel(Model):
    country_code: str = Field(default="", pattern=r"^(?:[A-Z]{2})?$")

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class Referee(CountryModel):
    id: ID
    name: Text


class Participant(CountryModel):
    id: ID
    name: Text
    short_name: str = Field(default="", max_length=40)
    logo_path: str = Field(default="", max_length=500)


class MatchPlan(Model):
    id: ID
    date: Date
    time: Time
    play_area_id: ID
    round: str = Field(default="", max_length=200)
    # Turnierphase laut Spielleitung, z. B. „Gruppenphase“; getrennt von round (Gruppe/Spielrunde).
    stage: str = Field(default="", max_length=200)
    # Optionale englische Anzeigetexte; leer = bekannte Zuordnung oder nicht verfügbar.
    stage_label: str = Field(default="", max_length=200)
    round_label: str = Field(default="", max_length=200)
    participant_1: ID | None = None
    participant_2: ID | None = None
    placeholder_1: str = Field(default="Noch offen", max_length=200)
    placeholder_2: str = Field(default="Noch offen", max_length=200)
    officials: list[ID] = Field(default_factory=list)


class Match(MatchPlan):
    status: Status = "scheduled"
    side_l: ID | None = None
    side_r: ID | None = None
    scores: dict[ID, Count] = Field(default_factory=dict)
    control_revision: Count = 0
    period: int = Field(default=1, strict=True, ge=1)
    # Pause zwischen `period` und dem nächsten Abschnitt (z. B. Halbzeitpause), unabhängig von paused.
    intermission: bool = Field(default=False, strict=True)
    counters: dict[ID, dict[ID, dict[str, Count]]] = Field(default_factory=dict)


class ActionEvent(Model):
    id: str
    type: str
    timestamp: datetime
    revision: Count
    request_id: str
    signature: str
    match_id: ID | None = None
    participant_id: ID | None = None
    delta: int | None = None
    undone: bool = False
    undo_of: str | None = None
    counter_id: ID | None = None
    period: int | None = Field(default=None, strict=True, ge=1)


class State(Model):
    schema_version: Literal[1] = 1
    revision: Count = 0
    event: Event | None = None
    play_areas: list[PlayArea] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)
    referees: list[Referee] = Field(default_factory=list)
    matches: list[Match] = Field(default_factory=list)
    active_match_id: ID | None = None
    events: list[ActionEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def invariants(self):
        for items in (self.play_areas, self.participants, self.referees, self.matches):
            if len({item.id for item in items}) != len(items):
                raise ValueError("IDs müssen je Kategorie eindeutig sein.")
        areas = {a.id for a in self.play_areas}
        people = {p.id for p in self.participants}
        referees = {r.id for r in self.referees}
        profile = self.event.sport_profile if self.event else None
        definitions = {c.id: c for c in profile.counters} if profile else {}
        for match in self.matches:
            if len(set(match.officials)) != len(match.officials):
                raise ValueError("Officials dürfen im selben Spiel nicht doppelt vorkommen.")
            if not set(match.officials) <= referees:
                raise ValueError("Officials müssen bekannte Referees sein.")
            if self.event is None or not self.event.date_from <= match.date <= self.event.date_to:
                raise ValueError("Spiel muss innerhalb der Veranstaltungsdaten liegen.")
            if match.play_area_id not in areas:
                raise ValueError("Unbekannte Play Area.")
            pair = [p for p in (match.participant_1, match.participant_2) if p is not None]
            if len(set(pair)) != len(pair) or not set(pair) <= people:
                raise ValueError("Paarung benötigt verschiedene, bekannte Teilnehmer.")
            if match.period > (profile.periods if profile else 1):
                raise ValueError("Abschnitt liegt außerhalb des Sportprofils.")
            if not set(match.counters) <= definitions.keys():
                raise ValueError("Unbekannter Counter im Spiel.")
            for values in match.counters.values():
                if not set(values) <= set(pair):
                    raise ValueError("Counter müssen Teilnehmern der Paarung gehören.")
                for history in values.values():
                    for period, value in history.items():
                        if (not period.isascii() or not period.isdigit() or str(int(period)) != period
                                or not 1 <= int(period) <= profile.periods):
                            raise ValueError("Ungültiger Counter-Abschnitt.")
                        if value and (int(period) > match.period or match.status in ("scheduled", "ready")):
                            raise ValueError("Zukünftige oder noch nicht gestartete Abschnitte müssen null sein.")
            if match.status in ("scheduled", "ready") and match.period != 1:
                raise ValueError("Vor Spielbeginn muss der Abschnitt 1 sein.")
            if match.intermission and (match.status not in ("live", "paused")
                                       or match.period >= (profile.periods if profile else 1)):
                raise ValueError("Pause zwischen Abschnitten nur im laufenden Spiel vor dem letzten Abschnitt.")
            if match.status == "scheduled":
                if match.side_l is not None or match.side_r is not None or match.scores:
                    raise ValueError("Geplantes Spiel darf noch keinen Live-Zustand haben.")
            elif (len(pair) != 2 or set(pair) != {match.side_l, match.side_r}
                  or set(match.scores) != set(pair)):
                raise ValueError("Seiten und Scores müssen zur Paarung gehören.")
            if match.status == "ready" and any(match.scores.values()):
                raise ValueError("Vor Spielbeginn müssen Scores null sein.")
            if match.status in ("ready", "live", "paused") and match.id != self.active_match_id:
                raise ValueError("Nur das ausgewählte Spiel darf aktiv sein.")
        if self.active_match_id is not None and self.active_match_id not in {m.id for m in self.matches}:
            raise ValueError("Unbekanntes aktives Spiel.")
        # Imported history must remain safe for the existing score-Undo operation.
        if len({e.id for e in self.events}) != len(self.events) or len({e.request_id for e in self.events}) != len(self.events):
            raise ValueError("Ereignis- und Request-IDs müssen eindeutig sein.")
        undo_scores = {m.id: dict(m.scores) for m in self.matches}
        for event in reversed(self.events):
            if event.type != "score":
                continue
            scores = undo_scores.get(event.match_id, {})
            if event.participant_id not in scores or event.delta not in (-1, 1):
                raise ValueError("Score-Ereignis benötigt gültiges Spiel, Teilnehmer und delta ±1.")
            if not event.undone:
                scores[event.participant_id] -= event.delta
                if scores[event.participant_id] < 0:
                    raise ValueError("Score-Ereignisse passen nicht zum gespeicherten Ergebnis (Undo wäre negativ).")
        return self
