"""Read a PDF or a page image into a Score: the whole reader, from the
page's symbols (omr.pdf.symbols) and layout (omr.pdf.layout) to the
structure (omr.pdf.structure) and, with notes, the notes, markings and
text (omr.pdf.notation)."""

from omr.documents import open_pdf
from omr.evaluate import events
from omr.pdf import layout as lay, notation, structure, symbols


def read_pdf(path, notes=False):
    """(Score, [PageLayout]) for a PDF: the structure, and with `notes` also
    the notes and rests (Stage 1.3, omr.pdf.notation) and the markings and
    text (Stage 1.4, omr.pdf.markings and omr.pdf.text). Pages holding a
    page image are read from it (Stage 2.4, omr.raster.reading). An image
    file is read as a one-page image PDF."""
    doc = open_pdf(path)
    try:
        # each page loaded once, so what PyMuPDF gives for it is fetched once
        # (omr.pdf.evidence.shown_drawings)
        use = [doc[i] for i in range(len(doc))]
        pages = symbols.read_document(doc, shown=use)
        if any(not p.symbols for p in pages):
            # the image reader (OpenCV and the detector) is loaded only for a page image
            from omr.raster import reading
            use, pages = reading.read_document(use, pages)
        layouts = lay.read_document(use, pages)
        assigned = structure.assign_parts(layouts)
        score = structure.read_structure(layouts, assigned)
        if notes:
            notation.read_notes(score, assigned[0], use, layouts)
            # Jump words read as text that system_navigation did not take are still jumps, as the harness reads them.
            events.navigation_from_words(score)
        return score, layouts
    finally:
        doc.close()
