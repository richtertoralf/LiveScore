"""Alle Oberflächentexte, Dialoge und Konfliktmeldungen liegen in EN, DE und CS vor."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ('en', 'de', 'cs')


def translations():
    source = (ROOT / 'static/i18n.js').read_text(encoding='utf-8')
    result = {}
    for lang in LANGUAGES:
        body = source.split(f'  "{lang}": {{', 1)[1].split('\n  }', 1)[0]
        result[lang] = {json.loads('"' + key + '"') for key in re.findall(r'^\s{4}"((?:[^"\\]|\\.)*)":', body, re.M)}
    return result


def used_texts():
    texts = {}
    for path in [*(ROOT / 'static').glob('*.js'), *(ROOT / 'static').glob('*.html')]:
        text = path.read_text(encoding='utf-8')
        for _, key in re.findall(r"""\bt\((['"])((?:(?!\1).)*)\1\)""", text):
            texts.setdefault(key, path.name)
        for key in re.findall(r'data-i18n(?:-aria|-title)?="([^"]*)"', text):
            texts.setdefault(key, path.name)
    # Konfliktmeldungen gelangen über errorText() in die Oberfläche.
    for path in (ROOT / 'livescore').glob('*.py'):
        for _, key in re.findall(r"""Conflict\((['"])((?:(?!\1).)*)\1\)""", path.read_text(encoding='utf-8')):
            texts.setdefault(key, path.name)
    return texts


class TranslationTest(unittest.TestCase):
    def test_every_used_text_exists_in_all_languages(self):
        available = translations()
        texts = used_texts()
        self.assertGreater(len(texts), 100)
        for lang in LANGUAGES:
            missing = {key: source for key, source in texts.items() if key not in available[lang]}
            self.assertEqual(missing, {}, lang)
