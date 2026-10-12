"""Profilbibliothek und Anzeigevokabular; keine Wettkampfregeln."""
from pydantic import Field, model_validator

from .models import Count, ID, Model, SportProfile


LANGUAGES = ("de", "en", "cs")
# Fallback for existing monolingual files only. Explicit translations always win.
PERIOD_TERMS = {
    "halbzeit": ("Halbzeit", "Half", "Poločas"),
    "runde": ("Runde", "Round", "Kolo"),
    "satz": ("Satz", "Set", "Set"),
    "abschnitt": ("Abschnitt", "Period", "Část"),
}
for aliases, key in ((('half', 'poločas'), 'halbzeit'), (('round', 'kolo'), 'runde'),
                     (('set',), 'satz'), (('period', 'část'), 'abschnitt')):
    for alias in aliases:
        PERIOD_TERMS[alias] = PERIOD_TERMS[key]
BREAK_TERMS = {
    "Halbzeit": ("Halbzeitpause", "Half-time", "Poločasová přestávka"),
    "Runde": ("Rundenpause", "Round break", "Přestávka mezi koly"),
    "Satz": ("Satzpause", "Set break", "Přestávka mezi sety"),
}
GENERIC_BREAK = ("Pause zwischen Abschnitten", "Break between periods", "Přestávka mezi částmi")
COUNTER_TERMS = {
    "fouls": ("Fouls", "Fouls", "Fauly"),
    "nächstes foul → double penalty": ("Nächstes Foul → Double Penalty", "Next foul → Double Penalty", "Další faul → Double Penalty"),
    "double penalty": ("Double Penalty", "Double Penalty", "Double Penalty"),
    "teamfouls": ("Teamfouls", "Team fouls", "Týmové fauly"),
    "warnschwelle erreicht": ("Warnschwelle erreicht", "Warning threshold reached", "Dosažena varovná hranice"),
    "kritische schwelle erreicht": ("Kritische Schwelle erreicht", "Critical threshold reached", "Dosažena kritická hranice"),
}


def translated(value, terms, index):
    return terms.get(value.casefold(), (value, value, value))[index]


def display_profile(profile):
    """All three languages together, without changing the stored event snapshot."""
    if profile is None:
        return None
    result = profile.model_dump(mode="json")
    base_period = PERIOD_TERMS.get(profile.period_label.casefold())
    for index, language in enumerate(LANGUAGES):
        labels = result['translations'].setdefault(language, {})
        defaults = dict(name=profile.sport, period_label=translated(profile.period_label, PERIOD_TERMS, index),
                        break_label=BREAK_TERMS.get(base_period[0] if base_period else '', GENERIC_BREAK)[index], hint='')
        for key, default in defaults.items():
            labels[key] = labels.get(key) or default
    for counter in result['counters']:
        for index, language in enumerate(LANGUAGES):
            labels = counter['translations'].setdefault(language, {})
            for key, fallback in (('label', counter['label']),
                                  ('warning_label', counter['warning_label'] or 'Warnschwelle erreicht'),
                                  ('critical_label', counter['critical_label'] or 'Kritische Schwelle erreicht')):
                labels[key] = labels.get(key) or translated(fallback, COUNTER_TERMS, index)
    return result


def structure(profile):
    """Fields which give meaning to period numbers and recorded counter histories."""
    return (profile.periods, {c.id: c.reset_each_period for c in profile.counters}) if profile else (1, {})


class ProfileEntry(Model):
    id: ID
    profile: SportProfile


class ProfileLibrary(Model):
    schema_version: int = Field(default=1, strict=True, ge=1, le=1)
    revision: Count = 0
    profiles: list[ProfileEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if len({entry.id for entry in self.profiles}) != len(self.profiles):
            raise ValueError('Profil-IDs müssen eindeutig sein.')
        return self

    def view(self):
        return dict(revision=self.revision, profiles=[dict(id=p.id, profile=display_profile(p.profile)) for p in self.profiles])


def save_library(path, library):
    from .storage import atomic_write
    checked = ProfileLibrary.model_validate(library.model_dump())
    atomic_write(path, checked.model_dump_json(indent=2) + '\n')
