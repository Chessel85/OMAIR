"""Fail if a pinned dependency has no entry in docs/licence-register.md (C-3)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "licence-register.md"
FIELDS = ("Kind", "Licence", "Use", "Source", "Status")


def normalise(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_names():
    names = []
    for filename in ("requirements.txt", "requirements-torch.txt"):
        for line in (ROOT / filename).read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                names.append(re.split(r"[=<>!~\[ ;]", line)[0])
    return names


def entries():
    """Map normalised entry name to the text of its section."""
    parts = re.split(r"^### +(.+)$", REGISTER.read_text(encoding="utf-8"), flags=re.M)
    return {normalise(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def test_every_pinned_dependency_has_an_entry():
    register = entries()
    missing = [n for n in pinned_names() if normalise(n) not in register]
    assert not missing, "No licence register entry for: " + ", ".join(missing)


def test_every_entry_has_all_fields():
    for name, body in entries().items():
        for field in FIELDS:
            assert f"- {field}:" in body, f"Entry {name} has no {field} line"
