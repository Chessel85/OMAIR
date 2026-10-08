"""Make the Stage 9 real-world set: real MuseScore.com PDFs from the Stage 8
PDMX survey sample, each paired with the MusicXML that PDMX gives for the same
upload. Written as a set folder (generated/realworld) with its own index.txt,
so `omr evaluate --set development --set-root ...` can run it.

Only works outside the training pool are used, with the same metadata filters
as the corpus (deduplicated, valid, 8 to 200 bars, up to 12 parts), and only
PDFs whose pages the survey found to be all Type A (or N, no music). The ground
truth is what the uploader entered, so it counts as "engraver input".
usage: python scripts/make_realworld_sample.py [--scores N] [--seed N]
"""

import argparse
import csv
import json
import random
import tarfile
import zipfile
from pathlib import Path

from omr import paths
from omr.corpus import config, labels


def survey_fonts():
    """PDF name -> (all pages Type A or text, music fonts) from the survey."""
    found = {}
    survey = paths.require_corpus_dir() / "survey" / "results.jsonl"
    for line in survey.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d.get("source") != "pdmx-pdf" or d.get("error"):
            continue
        types = d["summary"]["types"]
        ok = set(types) <= {"A", "N"} and "A" in types
        names = [f["name"] for f in d["summary"]["music_fonts"]]
        found[Path(d["file"]).name] = (ok, names, d["pages"])
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()
    corpus = paths.require_corpus_dir()
    src = corpus / "sources"
    pdf_names = {}
    for line in (src / "pdmx-pdf" / "index.txt").read_text(encoding="utf-8").splitlines():
        name, licence, archive_path = line.split("\t")
        pdf_names[archive_path] = (name, licence)
    fonts = survey_fonts()
    csv.field_size_limit(10**9)
    candidates = []
    with open(src / "pdmx" / "PDMX.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = row["pdf"].lstrip("./")
            if key not in pdf_names:
                continue
            if not (row["subset:deduplicated"] == "True" and row["subset:all_valid"] == "True"):
                continue
            try:
                bars, tracks = int(float(row["song_length.bars"])), int(row["n_tracks"])
            except ValueError:
                continue
            if not (config.MIN_BARS <= bars <= config.MAX_BARS and 1 <= tracks <= config.MAX_PARTS):
                continue
            title = (row["title"] or row["song_name"] or "").strip()
            composer = (row["composer_name"] or row["artist_name"] or "").strip()
            if composer == "NA":
                composer = ""
            if labels.pool_of(labels.work_key(composer, title)) == "training":
                continue
            name, licence = pdf_names[key]
            ok, music_fonts, pages = fonts.get(name, (False, [], 0))
            if not ok:
                continue
            candidates.append(dict(row=row, pdf=name, licence=licence, fonts=music_fonts, pages=pages,
                                   title=title, composer=composer, mxl=row["mxl"].lstrip("./")))
    candidates.sort(key=lambda c: c["pdf"])
    chosen = random.Random(args.seed).sample(candidates, min(args.scores, len(candidates)))
    print(f"{len(candidates)} eligible real-world PDFs, {len(chosen)} chosen.")

    out = corpus / "generated" / "realworld"
    out.mkdir(parents=True, exist_ok=True)
    wanted = {c["mxl"]: c for c in chosen}
    print("Reading mxl.tar.gz for the chosen files (one pass, a few minutes).")
    with tarfile.open(src / "pdmx" / "mxl.tar.gz", "r:gz") as tar:
        got = 0
        for member in tar:
            name = member.name.lstrip("./")
            if name in wanted and member.isfile():
                wanted[name]["data"] = tar.extractfile(member).read()
                got += 1
                if got == len(wanted):
                    break

    lines = ["# status | id | job | font | pdf | ground-truth MusicXML or reason",
             f"# real-world set: {len(chosen)} MuseScore.com PDFs from the PDMX survey sample, seed {args.seed}"]
    for c in sorted(chosen, key=lambda c: c["pdf"]):
        score_id = "real-" + Path(c["pdf"]).stem
        folder = out / score_id / "upload"
        folder.mkdir(parents=True, exist_ok=True)
        if "data" not in c:
            lines.append(f"failure | {score_id} | upload | ? | MusicXML missing from the archive")
            continue
        mxl = folder / "score.mxl"
        mxl.write_bytes(c["data"])
        with zipfile.ZipFile(mxl) as z:
            xml_name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            (folder / "score.musicxml").write_bytes(z.read(xml_name))
        mxl.unlink()
        pdf = folder / "score.pdf"
        pdf.write_bytes((src / "pdmx-pdf" / c["pdf"]).read_bytes())
        facts = labels.analyse(labels.read_musicxml(folder / "score.musicxml"))
        tex = labels.texture(facts) or "other"
        genre = labels.final_genre(labels.pdmx_genre(c["row"]["genres"]), tex, c["title"], c["row"]["tags"])
        font = c["fonts"][0] if c["fonts"] else "?"
        meta = {
            "source": "PDMX (MuseScore.com upload)", "source path": c["mxl"], "title": c["title"],
            "composer": c["composer"], "set": "realworld", "texture": tex, "genre": genre,
            "features": ", ".join(sorted(facts.features)), "engraver": "MuseScore.com",
            "font": font, "music fonts": ", ".join(c["fonts"]), "pages": str(c["pages"]),
            "licence": c["licence"], "ground truth file": "score.musicxml", "ground truth": "engraver input",
            "seed": str(args.seed),
        }
        (folder / "metadata.txt").write_text("".join(f"{k}: {v}\n" for k, v in meta.items()), encoding="utf-8")
        lines.append(f"pair | {score_id} | upload | {font} | {pdf} | {folder / 'score.musicxml'}")
    (out / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written to {out / 'index.txt'}")


if __name__ == "__main__":
    main()
