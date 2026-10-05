"""Fixed settings for the corpus generator. The rules they implement are in
docs/notes/corpus-sampling.md; change that file first, then this one."""

SEED = 20261005

# Pool split: work-key hash below REGRESSION_SHARE is regression-eligible,
# below DEVELOPMENT_SHARE (and not regression) is development-eligible.
REGRESSION_SHARE = 0.03
DEVELOPMENT_SHARE = 0.15

# Filters
MIN_BARS, MAX_BARS = 8, 200
MAX_PARTS = 12
MAX_MXL_BYTES = 1_000_000
REGRESSION_MAX_BARS = 64
REGRESSION_MAX_PAGES = 3
OPENSCORE_SHARE_LIMIT = 0.40  # of the voice-with-piano and chamber quotas

TEXTURES = ("choir", "chamber", "small ensemble", "voice with piano", "single line", "piano")
GENRES = ("classical", "popular", "jazz", "folk", "sacred", "choral", "educational")
FEATURES = (
    "lyrics", "chord symbols", "several voices on a staff", "tuplets",
    "grace notes", "repeats or endings", "key or time changes", "dynamics or hairpins",
)

SETS = {
    "development": {
        "size": 300,
        "textures": {"single line": 45, "voice with piano": 50, "piano": 70,
                     "choir": 50, "chamber": 50, "small ensemble": 35},
        "genre_min": {g: 20 for g in GENRES},
        "feature_min": {"lyrics": 60, "chord symbols": 30, "several voices on a staff": 40,
                        "tuplets": 25, "grace notes": 20, "repeats or endings": 40,
                        "key or time changes": 25, "dynamics or hairpins": 80},
    },
    "regression": {
        "size": 50,
        "textures": {"single line": 8, "voice with piano": 8, "piano": 10,
                     "choir": 8, "chamber": 8, "small ensemble": 8},
        "genre_min": {g: 3 for g in GENRES},
        "feature_min": {"lyrics": 10, "chord symbols": 5, "several voices on a staff": 8,
                        "tuplets": 5, "repeats or endings": 8, "dynamics or hairpins": 15},
    },
}

# PDMX genre tags (the CSV joins several with hyphens) to REC-10 genres.
# When a score has several tags the first matching group in GENRE_PRIORITY wins.
PDMX_TAG_GENRE = {
    "religiousmusic": "sacred",
    "jazz": "jazz",
    "folk": "folk", "worldmusic": "folk", "country": "folk",
    "classical": "classical",
    "pop": "popular", "rock": "popular", "rbfunksoul": "popular", "hiphop": "popular",
    "disco": "popular", "metal": "popular", "electronic": "popular",
    "reggaeska": "popular", "soundtrack": "popular",
}
GENRE_PRIORITY = ("sacred", "jazz", "folk", "classical", "popular")

EDUCATIONAL_WORDS = (
    "exercise", "exercises", "étude", "etude", "etudes", "study", "studies", "scale", "scales",
    "lesson", "method", "beginner", "grade", "sight-reading", "sightreading", "sight reading",
)

# The seven fonts MuseScore 4 rotates through, then MuseScore 3's three, and
# the three staff sizes (staff space in millimetres) for MuseScore 4.
MS4_VARIANT_FONTS = ("Bravura", "Petaluma", "Gonville", "MuseJazz",
                     "Finale Maestro", "Finale Broadway", "Emmentaler")
MS3_VARIANT_FONTS = ("Bravura", "Gonville", "MuseJazz")
MS4_STAFF_SIZES_MM = (1.5, 1.75, 2.0)

MIN_FREE_GB = 100
LILYPOND_TIMEOUT_S = 300
