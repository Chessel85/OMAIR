"""Labels computed for each candidate score: texture, genre, features, work key.

See docs/notes/corpus-sampling.md ("Labels computed for each candidate" and
"Splitting into pools").
"""

import hashlib
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

from omr.corpus import config

VOICE_WORDS = (
    "voice", "vocal", "vocals", "voix", "voz", "stimme", "singstimme", "soprano", "sopran",
    "alto", "contralto", "tenor", "baritone", "bariton", "mezzo", "choir", "chorus", "chor",
    "coro", "choeur", "cantus", "canto", "bassus", "altus",
)
VOICE_WORDS_NEEDING_NO_SOUND = ("bass", "basso", "bajo", "sop", "sopr", "ten", "bar")
KEYBOARD_WORDS = (
    "piano", "pianoforte", "klavier", "clavier", "organ", "orgel", "orgue", "organo",
    "harpsichord", "cembalo", "clavecin", "clavicembalo", "keyboard", "harmonium", "klavichord",
)


@dataclass
class ScoreFacts:
    """What the inspection of a MusicXML file found."""

    parts: int = 0
    bars: int = 0
    voices: int = 0       # voice parts
    keyboards: int = 0    # keyboard parts
    staves_per_part: list = field(default_factory=list)
    lyric_staves_in_two_staff_part: bool = False
    features: set = field(default_factory=set)
    excluded: str | None = None  # reason, for tablature, percussion or figured bass


def read_musicxml(path):
    """Return the root element of a .musicxml, .xml or compressed .mxl file."""
    path = str(path)
    if path.lower().endswith(".mxl"):
        with zipfile.ZipFile(path) as z:
            name = None
            if "META-INF/container.xml" in z.namelist():
                container = ET.fromstring(z.read("META-INF/container.xml"))
                for rf in container.iter("rootfile"):
                    name = rf.get("full-path")
                    break
            if not name:
                name = next(n for n in z.namelist() if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            data = z.read(name)
    else:
        with open(path, "rb") as f:
            data = f.read()
    return ET.parse(io.BytesIO(data)).getroot()


def _words(text):
    return re.findall(r"[a-zà-ÿ]+", text.lower())


GUITAR_WORDS = ("guitar", "guitarra", "gitarre", "chitarra", "guitare", "lute", "vihuela")


def _is_guitar(name, sounds):
    """A guitar part: by instrument sound where given, else by name. Bass
    guitar and electric guitar do not count (this is for classical guitar)."""
    words = _words(name)
    if "bass" in words or "electric" in words:
        return False
    if sounds:
        return any(s.startswith("pluck.guitar") and "electric" not in s and "bass" not in s for s in sounds)
    return any(w in GUITAR_WORDS for w in words)


def _is_voice(name, sounds):
    if any(s.startswith("voice.") for s in sounds):
        return True
    if sounds:
        return False
    words = _words(name)
    return any(w in VOICE_WORDS or w in VOICE_WORDS_NEEDING_NO_SOUND for w in words)


def _is_keyboard(name, sounds):
    if any(s.startswith("keyboard.") for s in sounds):
        return True
    if sounds and not any(w in KEYBOARD_WORDS for w in _words(name)):
        return False
    return any(w in KEYBOARD_WORDS for w in _words(name))


def analyse(root):
    """Inspect MusicXML and return ScoreFacts."""
    facts = ScoreFacts()
    part_info = {}
    for sp in root.iter("score-part"):
        name = (sp.findtext("part-name") or "") + " " + (sp.findtext("part-abbreviation") or "")
        sounds = [s.text for s in sp.iter("instrument-sound") if s.text]
        part_info[sp.get("id")] = (name, sounds)
    parts = root.findall("part")
    facts.parts = len(parts)
    if not parts:
        facts.excluded = "no parts"
        return facts
    facts.bars = len(parts[0].findall("measure"))
    for part in parts:
        name, sounds = part_info.get(part.get("id"), ("", []))
        if _is_voice(name, sounds):
            facts.voices += 1
        elif _is_keyboard(name, sounds):
            facts.keyboards += 1
        if _is_guitar(name, sounds):
            facts.features.add("guitar")
        staves = 1
        voices_on_staff = {}
        lyric_staves = set()
        key_time_changes = 0
        for mi, measure in enumerate(part.findall("measure")):
            attrs = measure.findall("attributes")
            for a in attrs:
                if a.findtext("staves"):
                    staves = max(staves, int(a.findtext("staves")))
                for tag in ("key", "time"):
                    if a.find(tag) is not None and mi > 0:
                        key_time_changes += 1
                for clef in a.findall("clef"):
                    if (clef.findtext("sign") or "").upper() == "TAB":
                        facts.excluded = "tablature"
            if measure.find("harmony") is not None:
                facts.features.add("chord symbols")
            if measure.find("figured-bass") is not None:
                facts.excluded = facts.excluded or "figured bass"
            if measure.find("direction/direction-type/dynamics") is not None or \
                    measure.find("direction/direction-type/wedge") is not None or \
                    measure.find("note/notations/dynamics") is not None:
                facts.features.add("dynamics or hairpins")
            if measure.find("barline/repeat") is not None or measure.find("barline/ending") is not None:
                facts.features.add("repeats or endings")
            for note in measure.findall("note"):
                if note.find("unpitched") is not None:
                    facts.excluded = facts.excluded or "unpitched percussion"
                if note.find("grace") is not None:
                    facts.features.add("grace notes")
                if note.find("time-modification") is not None:
                    facts.features.add("tuplets")
                if note.find("lyric") is not None:
                    facts.features.add("lyrics")
                    lyric_staves.add(note.findtext("staff") or "1")
                if note.find("rest") is None:
                    key = note.findtext("staff") or "1"
                    voices_on_staff.setdefault(key, set()).add(note.findtext("voice") or "1")
        if key_time_changes:
            facts.features.add("key or time changes")
        if any(len(v) > 1 for v in voices_on_staff.values()):
            facts.features.add("several voices on a staff")
        facts.staves_per_part.append(staves)
        if staves == 2 and len(lyric_staves) >= 2:
            facts.lyric_staves_in_two_staff_part = True
    return facts


def texture(facts):
    """The first matching rule gives the texture (spec, 'Texture')."""
    if facts.voices >= 2 or facts.lyric_staves_in_two_staff_part:
        return "choir"
    if facts.parts == 2 and facts.voices == 1 and facts.keyboards == 1:
        return "voice with piano"
    if facts.parts == 1 and facts.keyboards == 1:
        return "piano"
    if facts.parts == 1 and facts.staves_per_part == [1]:
        return "single line"
    if 2 <= facts.parts <= 5:
        return "chamber"
    if 6 <= facts.parts <= 12:
        return "small ensemble"
    return None


def pdmx_genre(tags):
    """Map the PDMX genre column (tags joined by hyphens) to a REC-10 genre,
    or 'other', or None when the score has no tag."""
    if not tags or tags == "NA":
        return None
    mapped = {config.PDMX_TAG_GENRE[t] for t in tags.split("-") if t in config.PDMX_TAG_GENRE}
    for genre in config.GENRE_PRIORITY:
        if genre in mapped:
            return genre
    return "other"


def is_educational(title, tags=""):
    text = f"{title} {tags}".lower()
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in config.EDUCATIONAL_WORDS)


def final_genre(source_genre, tex, title, tags=""):
    """Combine the source genre with the choral and educational rules."""
    if is_educational(title, tags):
        return "educational"
    if tex == "choir" and source_genre != "sacred":
        return "choral"
    return source_genre or "unlabelled"


# ----------------------------------------------------------------- work key

NOISE_WORDS = {
    "arr", "arranged", "arrangement", "arrangements", "for", "piano", "easy", "version",
    "simplified", "transcription", "transcribed", "by", "the", "a", "an", "solo", "and", "in",
    "score", "full", "vocal", "voice", "instrumental", "mscz", "pdf", "copy", "edit", "edition",
}
CATALOGUE = re.compile(r"\b(op|opus|bwv|hwv|kv|k|hob|rv|wwv|sz|d|s|wq|wo|woo|bb)\.? ?\d+[a-z]?\b")


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def work_key(composer, title):
    """Composer (last word) and title with noise removed, so that different
    arrangements of one piece share a key."""
    composer_words = _plain(composer).split()
    who = composer_words[-1] if composer_words else ""
    text = CATALOGUE.sub(" ", _plain(title))
    words = [w for w in text.split() if w not in NOISE_WORDS]
    return f"{who}|{' '.join(words)}"


def pool_fraction(key, seed=config.SEED):
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def pool_of(key, seed=config.SEED):
    """'regression', 'development' or 'training' (spec, 'Splitting into pools')."""
    x = pool_fraction(key, seed)
    if x < config.REGRESSION_SHARE:
        return "regression"
    if x < config.DEVELOPMENT_SHARE:
        return "development"
    return "training"


# --------------------------------------------------- near copies of a piece
#
# The work key above decides the pools and is kept unchanged, so that the
# selected sets stay as they are. These rules find near copies of a selected
# piece in the training pool (spec, "Keeping the training pool clean").

# Words before an arranger, editor or lyricist: the composer string is cut there.
CREDIT_CUT_WORDS = {
    "arr", "arranged", "arrangement", "arranger", "rearranged", "transcribed", "transcription",
    "orch", "orchestrated", "orchestration", "adapted", "adaptation", "edited", "ed", "editor",
    "harmonized", "harmonised", "harmonization", "lyrics", "lyricist", "words", "text", "feat",
    "featuring", "performed", "played", "cover",
}
# Labels that come before a composer's name and are not part of it.
CREDIT_LABEL_WORDS = {
    "music", "composer", "composed", "comp", "by", "written", "org", "original", "song", "from",
    "english", "german", "french", "latin", "italian", "spanish",
}
# Composer strings that name no one.
UNKNOWN_COMPOSER_WORDS = {
    "misc", "traditional", "trad", "anon", "anonymous", "unknown", "unbekannt", "various",
    "composer", "tunes", "songs",
}

# A title made only of these words (and numbers) names a form, not a piece:
# many different pieces share it, so the composer must match as well.
GENERIC_TITLE_WORDS = {
    # forms
    "prelude", "preludes", "praeludium", "fugue", "fuga", "invention", "sinfonia", "sonata", "sonatina",
    "etude", "study", "studies", "exercise", "exercises", "waltz", "valse", "walzer", "minuet", "menuet",
    "menuetto", "minuetto", "march", "marche", "marsch", "dance", "danse", "tanz", "theme", "variations",
    "variation", "nocturne", "mazurka", "polonaise", "polka", "scherzo", "rondo", "rondino", "gavotte",
    "bourree", "gigue", "jig", "reel", "hornpipe", "sarabande", "allemande", "courante", "air", "aria",
    "arietta", "chorale", "choral", "hymn", "canon", "lullaby", "berceuse", "romance", "romanze",
    "impromptu", "bagatelle", "fantasia", "fantasy", "fantasie", "toccata", "suite", "partita",
    "intermezzo", "ballade", "elegy", "elegie", "serenade", "serenata", "song", "songs", "lied", "chanson",
    "piece", "pieces", "duet", "duo", "trio", "quartet", "quintet", "concerto", "symphony", "overture",
    "chorus", "anthem", "carol", "psalm", "mass", "missa", "kyrie", "gloria", "credo", "sanctus",
    "agnus", "dei", "magnificat", "ave", "maria", "requiem", "blues", "rag", "tango", "bolero",
    "intro", "outro", "untitled", "new", "my", "first", "little", "short", "simple", "melody", "tune",
    "improvisation", "sketch", "movement", "mvt", "mov", "part", "no", "nr", "num", "number",
    # keys and tempo words
    "a", "b", "c", "d", "e", "f", "g", "h", "flat", "sharp", "major", "minor", "dur", "moll",
    "allegro", "allegretto", "andante", "andantino", "adagio", "moderato", "presto", "largo", "lento",
    "vivace", "grave", "maestoso", "cantabile", "con", "moto", "non", "troppo", "ma", "poco",
    # small words
    "of", "on", "to", "with", "from", "major", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
}


def clean_composer(composer):
    """The surname of the composer named in a credit string, or "" if it names
    no one. Dates and bracketed text are removed, and the string is cut at the
    first arranger, editor or lyricist word."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", composer or "")
    # Credits that have lost a space: "Nat King ColeArr.", "Mel Tormearr."
    text = re.sub(r"([a-z])(Arr\b|By\b|Lyrics\b|Words\b)", r"\1 \2", text)
    text = re.sub(r"([a-z])(arr\.)", r"\1 \2", text)
    text = re.sub(r"\d+", " ", text)
    head = text.split(",")[0]
    words = _plain(head).split()
    kept = []
    for w in words:
        if w in CREDIT_CUT_WORDS:
            break
        if w in CREDIT_LABEL_WORDS:
            continue
        kept.append(w)
    if not kept or any(w in UNKNOWN_COMPOSER_WORDS for w in kept):
        return ""
    if "," in text and len(kept) == 1:  # "Bach, Johann Sebastian"
        return kept[0]
    return kept[-1]


def piece_title(title, composer=""):
    """The title with catalogue numbers, noise words and the composer's own
    name removed, for matching copies of one piece."""
    text = CATALOGUE.sub(" ", _plain(title))
    surname = clean_composer(composer)
    return " ".join(w for w in text.split() if w not in NOISE_WORDS and w != surname)


def is_generic_title(cleaned):
    """True if a cleaned title names only a form, key, tempo or number."""
    return all(w in GENERIC_TITLE_WORDS or w.isdigit() for w in cleaned.split())


def distinctive_words(cleaned):
    """The words of a cleaned title that are not form, key or small words."""
    return {w for w in cleaned.split() if w not in GENERIC_TITLE_WORDS and not w.isdigit()}


class NearCopyIndex:
    """The selected pieces, for finding their near copies elsewhere.

    A score is a near copy of a selected piece if, after cleaning:

    - its title is the same, and the title is distinctive, or the composers
      match, or either composer is unknown; or
    - its title contains the selected title as a phrase ("Pachelbel's Canon in
      D major" contains "canon d"), and the selected title has at least two
      distinctive words or the composers match.

    One-word and generic titles ("Falling", "Prelude in C minor") need the
    composer for a phrase match, or they would catch unrelated pieces.
    """

    def __init__(self, selected):
        self.titles = {}
        self._phrases = None  # (padded key, strong, composers), rebuilt after add
        for title, composer in selected:
            self.add(title, composer)

    def add(self, title, composer):
        key = piece_title(title, composer)
        if key:
            self.titles.setdefault(key, set()).add(clean_composer(composer))
            self._phrases = None

    def match(self, title, composer):
        key = piece_title(title, composer)
        who = clean_composer(composer)
        composers = self.titles.get(key)
        if composers is not None:
            if not is_generic_title(key):
                return True
            return not who or "" in composers or who in composers
        padded = f" {key} "
        if self._phrases is None:
            self._phrases = [(f" {k} ", len(distinctive_words(k)) >= 2, who_set)
                             for k, who_set in self.titles.items()]
        for phrase, strong, composers in self._phrases:
            if phrase in padded and (strong or (who and who in composers)):
                return True
        return False
