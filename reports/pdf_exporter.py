"""Bug reports as a PDF: one page per bug, with its fields and both screenshots.

Each bug is one PDF bookmark (outline item), titled "Bug 00007: <summary>",
so a reader can jump between bugs in the viewer's sidebar
(tests/test_pdf_exporter.py fixes this interface).
"""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, Image, KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from reports.model import BugReport
from reports.repository import DATA_DIR

DEFAULT_PDF_DIR = DATA_DIR / "pdf"

# reportlab's built-in fonts (Helvetica) have no Polish letters (ą, ę, ł, ...),
# so use DejaVu Sans when it's installed (it comes with Chromium on Debian)
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
PAGE = landscape(A4)  # two screenshots side by side fit better across
MARGIN = 12 * mm
GAP = 6 * mm  # between the two screenshots
FRAME_PADDING = 12  # points: SimpleDocTemplate's frame pads 6 pt at the top and bottom


def pdf_path_for(report: BugReport, folder: Path = DEFAULT_PDF_DIR) -> Path:
    """bug_data/pdf/bug_00007.pdf, the same numbering as the screenshots."""
    return folder / f"bug_{report.id:05d}.pdf"


def _register_fonts() -> tuple[str, str]:
    """(regular, bold) font names: DejaVu Sans if available, else Helvetica."""
    regular, bold = FONT_DIR / "DejaVuSans.ttf", FONT_DIR / "DejaVuSans-Bold.ttf"
    if not (regular.exists() and bold.exists()):
        return "Helvetica", "Helvetica-Bold"
    if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
    return "DejaVuSans", "DejaVuSans-Bold"


class _Bookmark(Flowable):
    """Invisible marker: adds a sidebar entry pointing at the page it lands on."""

    def __init__(self, key: str, title: str) -> None:
        super().__init__()
        self.key, self.title = key, title

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return 0, 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=0)


class PdfExporter:
    def __init__(self) -> None:
        regular, bold = _register_fonts()
        base = getSampleStyleSheet()
        self.title_style = ParagraphStyle("BugTitle", parent=base["Heading2"], fontName=bold)
        self.body_style = ParagraphStyle("BugBody", parent=base["BodyText"], fontName=regular, fontSize=9, leading=12)
        self.label_style = ParagraphStyle("BugLabel", parent=self.body_style, fontName=bold)

    def export(self, reports: list[BugReport], path: Path) -> None:
        """Write the reports to path, one page each. Creates the folder if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN,
                                topMargin=MARGIN, bottomMargin=MARGIN, title="Bug reports")
        story: list[Flowable] = []
        for i, report in enumerate(reports):
            if i:
                story.append(PageBreak())
            # One page per bug: if it still doesn't fit (a very long description),
            # shrink the page's content instead of splitting it over two pages
            # (the bookmark stays outside: KeepInFrame skips zero-size flowables)
            height = doc.height - FRAME_PADDING
            story.append(_Bookmark(f"bug{report.id}", f"Bug {report.id:05d}: {report.summary}"))
            story.append(KeepInFrame(doc.width, height, self._bug_page(report, doc.width, height), mode="shrink"))
        if not story:  # reportlab can't build an empty document
            story.append(Paragraph("No bug reports.", self.body_style))
        doc.build(story)

    def _bug_page(self, report: BugReport, width: float, height: float) -> list[Flowable]:
        title = f"Bug {report.id:05d}: {report.summary}"
        rows = [
            ("Severity", report.severity.value), ("Status", report.status.value),
            ("Resolution", report.resolution.value or "-"), ("Engine", report.engine),
            ("Created", report.created_at.strftime("%Y-%m-%d %H:%M")),
            ("Source URL", report.source_url), ("Target URL", report.target_url),
        ]
        fields = Table([[Paragraph(label, self.label_style), self._text(value)] for label, value in rows],
                       colWidths=[28 * mm, width - 28 * mm])
        fields.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        flowables: list[Flowable] = [Paragraph(escape(title), self.title_style), fields, Spacer(1, 3 * mm)]
        if report.description:
            flowables += [Paragraph("Description", self.label_style), self._text(report.description),
                          Spacer(1, 3 * mm)]
        # The screenshots fill what's left of the page, side by side
        used = sum(f.wrap(width, height)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in flowables)
        flowables.append(self._screenshots(report, width, height - used))
        return flowables

    def _text(self, value: str) -> Paragraph:
        """Plain text in a Paragraph: escape its markup characters and keep line breaks."""
        return Paragraph(escape(value).replace("\n", "<br/>"), self.body_style)

    def _screenshots(self, report: BugReport, width: float, max_height: float) -> Table:
        cell_width = (width - GAP) / 2
        image_height = max(max_height - 6 * mm, 20 * mm)  # 6 mm: the "Left"/"Right" label row
        cells = []
        for label, shot in (("Source", report.source_screenshot), ("Target", report.target_screenshot)):
            if shot and Path(shot).exists():
                image = Image(shot)
                scale = min(cell_width / image.imageWidth, image_height / image.imageHeight)
                image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
                cells.append([Paragraph(label, self.label_style), image])
            else:
                cells.append([Paragraph(label, self.label_style), self._text("(no screenshot)")])
        table = Table([[cells[0][0], "", cells[1][0]], [cells[0][1], "", cells[1][1]]],
                      colWidths=[cell_width, GAP, cell_width])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return table
