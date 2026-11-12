"""The PDF view: a print-only HTML document rendered by WeasyPrint."""

from __future__ import annotations

import html
import re
from pathlib import Path

from md_viewer.highlight import PYGMENTS_FORMATTER
from md_viewer.layout import STYLE, static_text
from md_viewer.markdown import PLANTUML_SVG_URL, render_markdown

# Overrides for the PDF view: WeasyPrint lays out the same markup on paper.
PRINT_STYLE = static_text("print.css")


def pdf_document(title: str, body: str, rel: Path) -> str:
    """Self-contained HTML for WeasyPrint: no sidebar, scripts or view switcher."""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>{PYGMENTS_FORMATTER.get_style_defs(".code-block")}</style>
  <style>{STYLE}</style>
  <style>{PRINT_STYLE}</style>
</head>
<body>
  <main class="content">
    <div class="path">{html.escape(rel.as_posix())}</div>
    {body}
  </main>
</body>
</html>"""


# PlantUML draws note corners with zero-radius arcs (`A0,0 0 0 0 x,y`), which the
# SVG spec defines as straight lines but WeasyPrint's renderer garbles.
ZERO_ARC_RE = re.compile(r"A\s*0(?:\.0+)?[\s,]+0(?:\.0+)?[\s,]+[-\d.]+[\s,]+[01][\s,]+[01][\s,]+")


PDF_SETUP_HINT = "PDF needs Pango, Cairo and GLib, which WeasyPrint could not load. Run `brew install pango`."


def render_pdf(target: Path, rel: Path) -> bytes:
    """Imported here so a missing Pango only breaks this view (it raises OSError on import)."""
    import weasyprint
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    class PdfFetcher(URLFetcher):
        """WeasyPrint URL fetcher that patches PlantUML SVGs before they are drawn."""

        def fetch(self, url: str, headers: dict[str, str] | None = None) -> URLFetcherResponse:  # ty: ignore[missing-override-decorator]
            response = super().fetch(url, headers)
            if not url.startswith(PLANTUML_SVG_URL):
                return response  # ty: ignore[unsound-return-statement]
            svg = response.read().decode("utf-8")
            response.close()
            patched = ZERO_ARC_RE.sub("L", svg)
            return URLFetcherResponse(url, patched, {"Content-Type": "image/svg+xml"})

    body = f'<div class="markdown-body">{render_markdown(target)}</div>'
    document = weasyprint.HTML(
        string=pdf_document(target.name, body, rel),
        base_url=f"{target.parent}/",
        url_fetcher=PdfFetcher(),
    )
    return document.write_pdf()  # ty: ignore[unsound-return-statement]
