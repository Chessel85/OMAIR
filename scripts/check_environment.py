"""Report, in plain text, which external tools are installed, their versions and paths."""

import glob
import os
import re
import shutil
import subprocess
import sys

PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")
LOCAL_PROGRAMS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")


def run(args, timeout=30):
    """Run a command and return its combined output, or None if it could not run."""
    try:
        done = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, errors="replace"
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (done.stdout + done.stderr).strip()


def first_line(text):
    return text.splitlines()[0].strip() if text else ""


def find_on_path_or_in(name, patterns):
    """Look on PATH first, then in each glob pattern. Return a path or None."""
    found = shutil.which(name)
    if found:
        return found
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


def store_package_location(name_filter):
    """Return the install folder of a Microsoft Store package, or None."""
    command = (
        f"(Get-AppxPackage *{name_filter}* | Select-Object -First 1).InstallLocation"
    )
    out = run(["powershell", "-NoProfile", "-Command", command])
    return out if out and os.path.isdir(out) else None


def check_python():
    version = sys.version.split()[0]
    detail = f"Python {version} at {sys.executable}"
    if not version.startswith("3.14"):
        return None, detail + " (the design specifies 3.14)"
    return sys.executable, detail


def check_git():
    path = shutil.which("git")
    return path, first_line(run([path, "--version"])) if path else ""


def check_musescore4():
    path = find_on_path_or_in(
        "MuseScore4.exe", [os.path.join(PROGRAM_FILES, "MuseScore 4", "bin", "MuseScore4.exe")]
    )
    return path, first_line(run([path, "--long-version"])) if path else ""


def check_musescore3():
    path = shutil.which("MuseScore3.exe")
    if not path:
        folder = store_package_location("MuseScore")
        candidate = os.path.join(folder, "bin", "MuseScore3.exe") if folder else None
        if candidate and os.path.isfile(candidate):
            path = candidate
    if not path:
        path = find_on_path_or_in(
            "MuseScore3.exe", [os.path.join(PROGRAM_FILES, "MuseScore 3", "bin", "MuseScore3.exe")]
        )
    return path, first_line(run([path, "--version"])) if path else ""


def lilypond_patterns(exe):
    return [os.path.join(PROGRAM_FILES, "lilypond*", "bin", exe)]


def check_lilypond():
    path = find_on_path_or_in("lilypond", lilypond_patterns("lilypond.exe"))
    return path, first_line(run([path, "--version"])) if path else ""


def check_musicxml2ly():
    path = find_on_path_or_in("musicxml2ly", lilypond_patterns("musicxml2ly.py"))
    if not path:
        return None, ""
    if path.endswith(".py"):
        python = os.path.join(os.path.dirname(path), "python.exe")
        out = run([python, path, "--version"])
    else:
        out = run([path, "--version"])
    return path, first_line(out)


def check_java():
    path = find_on_path_or_in(
        "java",
        [
            os.path.join(PROGRAM_FILES, "Java", "*", "bin", "java.exe"),
            os.path.join(PROGRAM_FILES, "Eclipse Adoptium", "*", "bin", "java.exe"),
            os.path.join(PROGRAM_FILES, "Microsoft", "jdk-*", "bin", "java.exe"),
            os.path.join(LOCAL_PROGRAMS, "Eclipse Adoptium", "jdk-*", "bin", "java.exe"),
        ],
    )
    return path, first_line(run([path, "-version"])) if path else ""


def check_dorico():
    path = find_on_path_or_in(
        "Dorico.exe",
        [
            os.path.join(PROGRAM_FILES, "Steinberg", "Dorico*", "Dorico*.exe"),
            os.path.join(PROGRAM_FILES, "Dorico*", "Dorico*.exe"),
        ],
    )
    if path:
        return path, "installed (version not read from the command line)"
    folder = store_package_location("Dorico")
    if folder:
        return folder, "installed as a Store package"
    return None, ""


def check_nvidia():
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None, ""
    gpu = first_line(
        run([smi, "--query-gpu=name,driver_version", "--format=csv,noheader"])
    )
    banner = run([smi]) or ""
    match = re.search(r"CUDA Version:\s*([\d.]+)", banner)
    cuda = match.group(1) if match else "unknown"
    return smi, f"{gpu}, driver reports CUDA {cuda}"


# (label, check function, required)
CHECKS = [
    ("Python 3.14", check_python, True),
    ("Git", check_git, True),
    ("MuseScore 4", check_musescore4, True),
    ("MuseScore 3", check_musescore3, True),
    ("LilyPond", check_lilypond, True),
    ("musicxml2ly", check_musicxml2ly, True),
    ("Java runtime", check_java, True),
    ("Dorico SE (parked, not accessible with a screen reader)", check_dorico, False),
    ("NVIDIA driver (nvidia-smi)", check_nvidia, True),
]


def main():
    missing = []
    for label, check, required in CHECKS:
        path, detail = check()
        if path:
            print(f"FOUND: {label}. {detail}. Path: {path}")
        else:
            note = f" {detail}." if detail else ""
            if required:
                print(f"MISSING: {label}.{note} Install it, or put it on the PATH.")
                missing.append(label)
            else:
                print(f"NOT FOUND (optional): {label}.{note}")
    if missing:
        print(f"Summary: {len(missing)} required item(s) missing: {', '.join(missing)}.")
        return 1
    print("Summary: all required tools were found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
