from __future__ import annotations

from pathlib import Path


def pdf_to_text(path: Path) -> str:
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip() + "\n"


def write_simple_pdf(path: Path, text: str) -> None:
    """Write a one-page text PDF for fixtures and tests. Not used for live CPSA files."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")[:500]
    )
    stream = f"BT /F1 12 Tf 50 720 Td ({escaped}) Tj ET\n"
    stream_bytes = stream.encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream_bytes) + stream_bytes + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    position = len(header)
    for index, obj in enumerate(objects, start=1):
        offsets.append(position)
        rendered = f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
        body += rendered
        position += len(rendered)
    xref_pos = len(header) + len(body)
    xref = [b"xref\n", f"0 {len(objects) + 1}\n".encode(), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
        + b"startxref\n"
        + f"{xref_pos}\n".encode()
        + b"%%EOF\n"
    )
    path.write_bytes(header + body + b"".join(xref) + trailer)
