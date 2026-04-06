from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class SplitPdfDocument:
    file_stem: str
    file_name: str
    path: Path
    start_page: int
    end_page: int
    page_count: int


def build_split_documents(
    *, start_pages: list[int], total_pages: int
) -> list[tuple[str, int, int]]:
    if total_pages <= 0:
        return []

    normalized_starts = sorted(
        {page for page in start_pages if 1 <= page <= total_pages}
    )
    if not normalized_starts:
        return [("0", 1, total_pages)]

    documents: list[tuple[str, int, int]] = []
    if normalized_starts[0] > 1:
        documents.append(("0", 1, normalized_starts[0] - 1))

    for index, start_page in enumerate(normalized_starts, start=1):
        next_start = (
            normalized_starts[index] if index < len(normalized_starts) else None
        )
        end_page = (next_start - 1) if next_start is not None else total_pages
        documents.append((str(index), start_page, end_page))

    return documents


def write_split_pdfs(
    pdf_bytes: bytes, *, output_dir: Path, start_pages: list[int]
) -> list[SplitPdfDocument]:
    output_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(stream=pdf_bytes, filetype="pdf") as source_document:
        total_pages = source_document.page_count
        if total_pages <= 0:
            return []

        documents: list[SplitPdfDocument] = []
        for file_stem, start_page, end_page in build_split_documents(
            start_pages=start_pages, total_pages=total_pages
        ):
            target_path = output_dir / f"{file_stem}.pdf"
            with fitz.open() as target_document:
                target_document.insert_pdf(
                    source_document, from_page=start_page - 1, to_page=end_page - 1
                )
                target_document.save(target_path)
            documents.append(
                SplitPdfDocument(
                    file_stem=file_stem,
                    file_name=target_path.name,
                    path=target_path,
                    start_page=start_page,
                    end_page=end_page,
                    page_count=(end_page - start_page) + 1,
                )
            )

    return documents
