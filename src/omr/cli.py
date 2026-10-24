"""Command-line entry point. All output is plain text."""

import argparse
import sys

COMMANDS = {
    "inspect": "Report the page types, fonts and shapes in a PDF.",
    "symbols": "Name the music symbols in vector PDFs and count those that cannot be named.",
    "layout": "Report the parts, bars, clefs, keys and times read from vector PDFs.",
    "confidence": "Read vector PDFs and report the bars that may be wrong.",
    "evaluate": "Score recogniser output against ground truth.",
    "convert": "Convert vector PDFs to MusicXML and braille, with a confidence report.",
}


def build_parser():
    parser = argparse.ArgumentParser(prog="omr", description="Optical music recognition.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        if name == "inspect":
            p.add_argument("files", nargs="+", metavar="FILE", help="PDF, PNG, JPEG or TIFF files.")
            p.add_argument("--json", metavar="PATH", help="Also write full results as JSON.")
            p.add_argument("--pages", metavar="LIST", help="Pages to inspect, for example 1-3,7.")
            p.add_argument("--brief", action="store_true", help="Only a summary of each file.")
        if name == "symbols":
            p.add_argument("files", nargs="+", metavar="FILE", help="PDF files.")
            p.add_argument("--json", metavar="PATH", help="Also write the counts as JSON.")
            p.add_argument("--pages", metavar="LIST", help="Pages to read, for example 1-3,7.")
        if name == "layout":
            p.add_argument("files", nargs="+", metavar="FILE", help="PDF files.")
            p.add_argument("--json", metavar="PATH", help="Also write the structure as JSON.")
        if name == "confidence":
            p.add_argument("files", nargs="+", metavar="FILE", help="PDF files.")
            p.add_argument("--out", metavar="FOLDER",
                           help="Also write FOLDER/<file name>/flags.json and confidence.txt for each file.")
        if name == "convert":
            add_convert_arguments(p)
        if name == "evaluate":
            add_evaluate_arguments(p)
    return parser


def add_convert_arguments(p):
    p.add_argument("files", nargs="+", metavar="FILE", help="Vector PDF files.")
    p.add_argument("--out", metavar="FOLDER",
                   help="Where the outputs go (default: beside each PDF), named after the PDF: name.musicxml, "
                        "name.brf, name-report.txt and name-flags.json.")
    p.add_argument("--musicxml", metavar="PATH", help="Write the MusicXML here (one FILE only).")
    p.add_argument("--braille", metavar="PATH",
                   help="Write the braille here (one FILE only). A .brf name gives Braille ASCII, "
                        "any other name Unicode braille.")
    p.add_argument("--report", metavar="PATH", help="Write the confidence report here (one FILE only).")
    p.add_argument("--flags", metavar="PATH", help="Write the flag file the evaluation harness reads here (one FILE only).")
    p.add_argument("--braille-format", choices=("brf", "unicode"),
                   help="brf (Braille ASCII) or unicode (Unicode braille text). The default follows the file "
                        "name, and is brf. The default code and format are not decided yet (OI-1).")
    p.add_argument("--no-braille", action="store_true", help="Do not write braille.")


def add_evaluate_arguments(p):
    from omr import parallel

    p.add_argument("--set", required=True, choices=("development", "regression"), help="The corpus set to evaluate.")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--recogniser", metavar="NAME_OR_COMMAND",
                        help="perfect, damaged, omr (this project), audiveris, homr, legato, or a command with {pdf} and {out}, for example "
                             "\"python my_omr.py {pdf} {out}\". It must write {out}/score.musicxml.")
    source.add_argument("--predictions", metavar="FOLDER",
                        help="Compare outputs already made, at FOLDER/<score id>/<job>/score.musicxml.")
    for name in ("engraver", "font", "genre", "texture"):
        p.add_argument(f"--{name}", help=f"Only pairs with this {name}.")
    p.add_argument("--limit", type=int, help="Only the first N pairs.")
    p.add_argument("--workers", type=int, default=parallel.DEFAULT_WORKERS,
                   help=f"Pairs to run at once (default {parallel.DEFAULT_WORKERS}).")
    p.add_argument("--timeout", type=int, default=600, help="Seconds allowed per file (default 600).")
    p.add_argument("--cpu-only", action="store_true", help="Hide the GPU from the recogniser, for timings on the CPU alone.")
    p.add_argument("--no-musicdiff", action="store_true", help="Skip musicdiff and OMR-NED, which are slower.")
    p.add_argument("--set-root", metavar="FOLDER",
                   help="Read the set from FOLDER (with its index.txt) instead of the corpus folder, "
                        "for example the regression set in the repository.")
    p.add_argument("--out", metavar="FOLDER", help="Where the reports go (default: evaluations/ under the corpus folder).")
    p.add_argument("--pausable", action="store_true",
                   help="Before each file, wait while continue.txt in the repository's folder does not say yes.")


def run_evaluate(args):
    from omr import parallel, paths
    from omr.evaluate import harness
    from omr.log import ProgressLog

    logs = paths.REPO_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = ProgressLog("evaluate", path=str(logs / "evaluate.log"))
    try:
        parallel.check_workers(args.workers)
        filters = {k: getattr(args, k) for k in ("engraver", "font", "genre", "texture", "limit")}
        results, report = harness.run(
            args.set, args.recogniser, log, out_dir=args.out, predictions=args.predictions,
            workers=args.workers, timeout=args.timeout, cpu_only=args.cpu_only,
            with_musicdiff=not args.no_musicdiff, set_root=args.set_root, pausable=args.pausable, **filters)
    except (ValueError, FileNotFoundError, paths.CorpusDirError) as error:
        log.error(str(error))
        return log.finish("evaluation stopped")
    from omr.evaluate import report as reports

    done = [r for r in results if "harness error" not in r]
    exact = sum(r["notes"]["exact"] for r in done)
    whole = sum(r["notes"]["truth"] + r["notes"]["extra"] for r in done)
    failed = sum(1 for r in done if "failed" in r)
    log.info(f"Report written to {report}.")
    return log.finish(f"{len(done)} files evaluated, note accuracy {reports.percent(exact, whole)}, {failed} failed")


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2
    if args.command == "inspect":
        from omr import inspect as inspector

        return inspector.run(args.files, json_path=args.json, pages=args.pages, brief=args.brief)
    if args.command == "symbols":
        from omr import symbol_report

        return symbol_report.run(args.files, json_path=args.json, pages=args.pages)
    if args.command == "layout":
        from omr import layout_report

        return layout_report.run(args.files, json_path=args.json)
    if args.command == "confidence":
        from omr import confidence_report

        return confidence_report.run(args.files, out_dir=args.out)
    if args.command == "convert":
        from omr import convert

        chosen = {k: getattr(args, k) for k in ("musicxml", "braille", "report", "flags")}
        return convert.run(args.files, out_dir=args.out, chosen=chosen, braille=not args.no_braille,
                           braille_format=args.braille_format)
    if args.command == "evaluate":
        return run_evaluate(args)
    print(f"The '{args.command}' command is not implemented yet.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
