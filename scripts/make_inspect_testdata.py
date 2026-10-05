"""Build the small PDF set in tests/data/inspect/ from the Bach chorale BWV 66.6.

The chorale comes from the music21 corpus (BSD, public domain). Run this once;
the PDFs are committed. See docs/notes/inspector-spec.md, section Tests.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from omr.corpus import engravers
from omr.log import ProgressLog

OUT = Path(__file__).resolve().parents[1] / "tests" / "data" / "inspect"

MS4_FONTS = {
    "ms4_leland": "Leland",
    "ms4_bravura": "Bravura",
    "ms4_petaluma": "Petaluma",
    "ms4_gonville": "Gonville",
    "ms4_musejazz": "MuseJazz",
    "ms4_finale_maestro": "Finale Maestro",
    "ms4_finale_broadway": "Finale Broadway",
}


def main():
    import music21

    log = ProgressLog("make-inspect-testdata")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "bach.musicxml"
        music21.corpus.parse("bach/bwv66.6").write("musicxml", fp=str(source))
        jobs = [(name, lambda d, f=font: engravers.export_musescore4(source, d, font=f))
                for name, font in MS4_FONTS.items()]
        jobs += [
            ("ms3_default", lambda d: engravers.export_musescore3(source, d)),
            ("lilypond", lambda d: engravers.export_lilypond(source, d)),
            ("verovio", lambda d: engravers.export_verovio(source, d)),
        ]
        for name, job in jobs:
            try:
                result = job(Path(tmp) / name)
                shutil.copyfile(result.pdf, OUT / f"{name}.pdf")
                log.info(f"{name}: wrote {(OUT / f'{name}.pdf').stat().st_size} bytes")
            except engravers.ExportError as error:
                log.error(f"{name}: {error}")
    return log.finish("test PDFs written")


if __name__ == "__main__":
    sys.exit(main())
