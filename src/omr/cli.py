"""Command-line entry point. All output is plain text."""

import argparse
import sys

COMMANDS = {
    "inspect": "Report the page types, fonts and shapes in a PDF.",
    "evaluate": "Score recogniser output against ground truth.",
    "convert": "Convert a PDF or image to MusicXML.",
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="omr", description="Optical music recognition.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    args = parser.parse_args(argv)
    print(f"The '{args.command}' command is not implemented yet.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
