"""Command-line entry point. All output is plain text."""

import argparse
import sys

COMMANDS = {
    "inspect": "Report the page types, fonts and shapes in a PDF.",
    "evaluate": "Score recogniser output against ground truth.",
    "convert": "Convert a PDF or image to MusicXML.",
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
        if name == "evaluate":
            add_evaluate_arguments(p)
    return parser


def add_evaluate_arguments(p):
    from omr import parallel

    p.add_argument("--set", required=True, choices=("development", "regression"), help="The corpus set to evaluate.")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--recogniser", metavar="NAME_OR_COMMAND",
                        help="perfect, damaged, or a command with {pdf} and {out}, for example "
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
    p.add_argument("--out", metavar="FOLDER", help="Where the reports go (default: evaluations/ under the corpus folder).")


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
            with_musicdiff=not args.no_musicdiff, **filters)
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
    if args.command == "evaluate":
        return run_evaluate(args)
    print(f"The '{args.command}' command is not implemented yet.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
