"""Opening the files the reader takes: PDFs, and page images read as a
one-page PDF. Kept apart from the commands (omr inspect, omr convert) so
that the reader can open a file without importing them."""

from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class InspectError(Exception):
    """A file could not be read. The message says why."""


def open_pdf(path):
    """The file as a PyMuPDF document: a PDF as it is, an image file as a
    one-page image PDF."""
    import pymupdf   # loaded when a file is opened, not when the command line starts

    if Path(path).suffix.lower() in IMAGE_SUFFIXES:
        image = pymupdf.open(str(path))
        doc = pymupdf.open("pdf", image.convert_to_pdf())
        image.close()
        return doc
    return pymupdf.open(str(path))


def open_document(path):
    """open_pdf, with an InspectError that says why for a file that is
    missing, damaged or encrypted."""
    path = Path(path)
    if not path.is_file():
        raise InspectError(f"{path} does not exist or is not a file.")
    try:
        doc = open_pdf(path)
    except Exception as error:
        raise InspectError(f"{path.name} could not be opened ({error}). It may be damaged or not a PDF.")
    if doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise InspectError(f"{path.name} is encrypted. Remove the password first.")
    return doc
