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
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2
    if args.command == "inspect":
        from omr import inspect as inspector

        return inspector.run(args.files, json_path=args.json, pages=args.pages, brief=args.brief)
    print(f"The '{args.command}' command is not implemented yet.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
