"""Profilbibliothek und Anzeigevokabular; keine Wettkampfregeln."""
from pydantic import Field, model_validator

from .models import Count, ID, Model, SportProfile, CounterDefinition, ProfileRole


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
                        break_label=BREAK_TERMS.get(base_period[0] if base_period else '', GENERIC_BREAK)[index], hint='',
                        score_label='', sets_label=('Gewonnene Sätze','Sets won','Vyhrané sety')[index])
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
    profile = profile or SportProfile()
    return (profile.periods, {c.id: c.reset_each_period for c in profile.counters},
            profile.score_mode, profile.sets_enabled)


class ProfileEntry(Model):
    id: ID
    profile: SportProfile


class ProfileLibrary(Model):
    schema_version: int = Field(default=1, strict=True, ge=1, le=1)
    revision: Count = 0
    profiles: list[ProfileEntry] = Field(default_factory=list)
    bundled_profiles: list[ID] = Field(default_factory=list)

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
    atomic_write(path, checked.model_dump_json(indent=2) + '\n', preserve_owner=True)


def standard_profiles():
    """Shipped starting configurations; nothing here selects sports-specific logic."""
    def profile(identifier, names, periods, period, pause, mode='total', steps=(1,), sets=False,
                score=('Tore', 'Goals', 'Góly'), hint=('', '', '')):
        return ProfileEntry(id='standard-' + identifier, profile=SportProfile(
            sport=identifier, periods=periods, period_label=period[0], score_mode=mode,
            score_steps=list(steps), sets_enabled=sets,
            translations={lang: dict(name=names[i], period_label=period[i], break_label=pause[i],
                score_label=score[i], sets_label=('Gewonnene Sätze','Sets won','Vyhrané sety')[i], hint=hint[i])
                for i, lang in enumerate(LANGUAGES)}))
    half = ('Halbzeit', 'Half', 'Poločas')
    half_break = ('Halbzeitpause', 'Half-time', 'Poločasová přestávka')
    set_name = ('Satz', 'Set', 'Set')
    set_break = ('Satzpause', 'Set break', 'Přestávka mezi sety')
    points = ('Satzpunkte', 'Set points', 'Body v setu')
    blind = profile('blind-football', ('Blindenfußball','Blind football','Fotbal nevidomých'), 2, half, half_break)
    blind.profile.counters = [CounterDefinition(id='team_fouls',label='Teamfouls', warning_at=4,critical_at=5,
        translations={lang: dict(label=('Teamfouls','Team fouls','Týmové fauly')[i],
            warning_label=('4 Teamfouls erreicht','4 team fouls recorded','Zaznamenány 4 týmové fauly')[i],
            critical_label=('Ab 5 Teamfouls','5 or more team fouls','5 a více týmových faulů')[i])
            for i,lang in enumerate(LANGUAGES)})]
    showdown = profile('showdown', ('Showdown','Showdown','Showdown'), 3, set_name, set_break,
        mode='period', steps=(1,2), sets=True, score=points,
        hint=('Best-of-Three als Ausgangspunkt; andere Formate vor Spielbeginn einstellen.',
              'Best of three by default; configure other formats before play.',
              'Výchozí formát na dva vítězné sety; jiný formát nastavte před zápasem.'))
    boxing = profile('boxing', ('Boxen','Boxing','Box'), 3,
        ('Runde','Round','Kolo'),('Rundenpause','Round break','Přestávka mezi koly'), mode='none', score=('', '', ''))
    boxing.profile.roles = {
        'participant_1':ProfileRole(id='red',labels=dict(zip(LANGUAGES,('Rote Ecke','Red corner','Červený roh')))),
        'participant_2':ProfileRole(id='blue',labels=dict(zip(LANGUAGES,('Blaue Ecke','Blue corner','Modrý roh'))))}
    boxing.profile.show_details = boxing.profile.show_officials = False
    football = profile('football', ('Fußball','Football','Fotbal'), 2, half, half_break)
    handball = profile('handball', ('Handball','Handball','Házená'), 2, half, half_break)
    table = profile('table-tennis', ('Tischtennis','Table tennis','Stolní tenis'), 5,
        ('Satz','Game','Set'),('Satzpause','Game interval','Přestávka mezi sety'), mode='period', sets=True,
        score=('Satzpunkte','Game points','Body v setu'), hint=(
            'Best-of-Five als Ausgangspunkt; andere Formate vor Spielbeginn einstellen.',
            'Best of five by default; configure other formats before play.',
            'Výchozí formát na tři vítězné sety; jiný formát nastavte před zápasem.'))
    table.profile.translations['en'].sets_label = 'Games won'
    volleyball = profile('volleyball', ('Volleyball','Volleyball','Volejbal'), 5, set_name, set_break,
        mode='period', sets=True, score=points)
    return [blind, showdown, boxing, football, handball, table, volleyball]


def provision_profiles(path):
    """Atomically add uninstalled defaults, preserving IDs, edits and deliberate deletions."""
    if path.is_symlink():
        raise ValueError('Profilbibliothek darf kein symbolischer Link sein.')
    library = ProfileLibrary.model_validate_json(path.read_text(encoding='utf-8')) if path.exists() else ProfileLibrary()
    known = {p.id for p in library.profiles}
    installed = set(library.bundled_profiles)
    changed = False
    for entry in standard_profiles():
        if entry.id in installed:
            continue
        if entry.id not in known:
            library.profiles.append(entry)
        library.bundled_profiles.append(entry.id)
        changed = True
    if changed:
        library.revision += 1
        save_library(path, library)
    return library
