"""Collect A4 PDFs from the Mutopia Project for the Stage 8 survey.

Polite: one request every few seconds, an identifying User-Agent, resumable.
Mutopia's robots.txt allows crawling. Only pieces marked Public Domain or a
Creative Commons licence are kept, and the licence is recorded per piece in
`index.txt` (tab separated: id, licence, composer folder, url, file).
CC BY-SA pieces stay in the corpus folder and never go in the public repository.

Files go to `sources/mutopia` under the corpus folder from `omr.paths`.
Mutopia is almost all LilyPond output, so a sample is enough: `--limit N`
keeps N pieces, chosen with a fixed seed from the whole listing.
"""

import argparse
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

from omr import paths
from omr.log import ProgressLog

LISTING = ("https://www.mutopiaproject.org/cgibin/make-table.cgi?startat={start}"
           "&searchingfor=&Composer=&Instrument=&Style=&collection=&id=&solo="
           "&recent=&timelength=1&timeunit=week&lilyversion=&preview=")
AGENT = "OMAIR-research/0.1 (open source OMR project; ckgoodwin85@gmail.com)"
LICENCES = {"publicdomain": "Public Domain", "ccby": "CC BY", "ccasa": "CC BY-SA", "cc0": "CC0"}
SEED = 20261007


def fetch(url, delay):
    time.sleep(delay)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def parse_listing(html):
    """Yield (piece id, licence name, A4 PDF url) for each row of one listing page."""
    for block in html.split("piece-info.cgi?id=")[1:]:
        piece = re.match(r"\d+", block).group()
        pdf = re.search(r'href="(https://www\.mutopiaproject\.org/ftp/[^"]*-a4\.pdf)"', block)
        lic = re.search(r'legal\.html#(\w+)', block)
        if pdf:
            yield piece, LICENCES.get(lic.group(1) if lic else "", lic.group(1) if lic else "unknown"), pdf.group(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=150, help="pieces to keep (default 150)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3)")
    args = ap.parse_args(argv)

    root = paths.require_corpus_dir() / "sources" / "mutopia"
    root.mkdir(parents=True, exist_ok=True)
    paths.check_free_space(root)
    log = ProgressLog("collect-mutopia", path=root / "collect.log")
    listing_file = root / "listing.tsv"

    if not listing_file.exists():
        rows, start = [], 0
        while True:
            try:
                page = list(parse_listing(fetch(LISTING.format(start=start), args.delay).decode("utf-8", "replace")))
            except Exception as error:
                log.error(f"Listing from {start} failed ({error}). Run again to resume.")
                return log.finish(f"{len(rows)} pieces listed, listing incomplete")
            if not page:
                break
            rows += page
            start += 10
            if start % 200 == 0:
                log.info(f"{len(rows)} pieces listed so far.")
        listing_file.write_text("\n".join("\t".join(r) for r in rows), encoding="utf-8")
        log.info(f"Listing complete: {len(rows)} pieces.")
    rows = [tuple(l.split("\t")) for l in listing_file.read_text(encoding="utf-8").splitlines()]
    kept = [r for r in rows if r[1] in ("Public Domain", "CC0", "CC BY", "CC BY-SA")]
    random.Random(SEED).shuffle(kept)
    kept = kept[:args.limit]

    done = failed = 0
    index = root / "index.txt"
    have = set(index.read_text(encoding="utf-8").splitlines()) if index.exists() else set()
    for piece, licence, url in kept:
        name = f"{piece}-{url.rsplit('/', 1)[1]}"
        target = root / name
        if target.exists():
            continue
        try:
            data = fetch(url, args.delay)
            if not data.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            target.write_bytes(data)
            line = "\t".join((piece, licence, url, name))
            if line not in have:
                with open(index, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            done += 1
        except Exception as error:
            failed += 1
            log.error(f"Piece {piece} ({url}) failed: {error}")
    log.info(f"Folder size: {sum(p.stat().st_size for p in root.glob('*.pdf')) / 1e6:.0f} MB.")
    return log.finish(f"{done} PDFs downloaded, {failed} failed, {len(kept)} chosen")


if __name__ == "__main__":
    sys.exit(main())
