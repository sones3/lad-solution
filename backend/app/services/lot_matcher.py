from __future__ import annotations

from dataclasses import dataclass
import difflib

from app.models.lot_models import (
    LotCsvRowModel,
    LotDocumentModel,
    LotIssueModel,
    LotMatchCandidateModel,
    LotMatchFieldResultModel,
    LotSeparationPageModel,
)
from app.services.lot_csv import LotCsvRow
from app.services.lot_separator import compact_lot_digits, compact_lot_text


@dataclass(frozen=True)
class LotDocumentSeed:
    index: int
    start_page: int
    end_page: int
    page_count: int
    first_page: LotSeparationPageModel | None


@dataclass(frozen=True)
class FuzzyOccurrenceResult:
    occurrence: str
    score: float


def build_lot_match_results(
    *,
    documents: list[LotDocumentSeed],
    csv_rows: list[LotCsvRow],
) -> tuple[list[LotDocumentModel], list[LotIssueModel], bool]:
    document_models: list[LotDocumentModel] = []
    issues: list[LotIssueModel] = []
    claimed_rows: dict[int, list[int]] = {}

    if len(documents) != len(csv_rows):
        issues.append(
            LotIssueModel(
                code="document_count_mismatch",
                message=f"Detected {len(documents)} documents for {len(csv_rows)} CSV rows",
            )
        )

    for document in documents:
        document_model, document_issues, claimed_row = evaluate_lot_document(
            document=document, csv_rows=csv_rows
        )
        document_models.append(document_model)
        issues.extend(document_issues)
        if claimed_row is not None:
            claimed_rows.setdefault(claimed_row, []).append(document.index)

    return finalize_lot_documents(
        documents=document_models,
        issues=issues,
        claimed_rows=claimed_rows,
    )


def evaluate_lot_document(
    *,
    document: LotDocumentSeed,
    csv_rows: list[LotCsvRow],
) -> tuple[LotDocumentModel, list[LotIssueModel], int | None]:
    issues: list[LotIssueModel] = []

    if document.first_page is None:
        issues.append(
            LotIssueModel(
                code="missing_first_page_ocr",
                message=f"Document {document.index} has no first-page OCR payload",
                documentIndex=document.index,
                pageNumber=document.start_page,
            )
        )
        return (
            LotDocumentModel(
                index=document.index,
                startPage=document.start_page,
                endPage=document.end_page,
                pageCount=document.page_count,
                firstPageOcrRaw="",
                firstPageOcrNormalized="",
                firstPageOcrCompact="",
                acceptedCandidateCount=0,
                candidates=[],
                assignedRow=None,
                blockedReason="Missing first-page OCR",
            ),
            issues,
            None,
        )

    candidates = _build_candidates(document.first_page, csv_rows)
    accepted_candidates = [candidate for candidate in candidates if candidate.qualifies]
    assigned_row = accepted_candidates[0].row if len(accepted_candidates) == 1 else None
    blocked_reason: str | None = None

    if len(accepted_candidates) == 0:
        blocked_reason = "No CSV row satisfied the exact numeric and fuzzy text rule"
        issues.append(
            LotIssueModel(
                code="no_match",
                message=f"Document {document.index} has no valid CSV match",
                documentIndex=document.index,
                pageNumber=document.start_page,
            )
        )
    elif len(accepted_candidates) > 1:
        blocked_reason = "Multiple CSV rows satisfy the matching rule"
        issues.append(
            LotIssueModel(
                code="ambiguous_match",
                message=f"Document {document.index} has {len(accepted_candidates)} valid CSV candidates",
                documentIndex=document.index,
                pageNumber=document.start_page,
            )
        )

    document_model = LotDocumentModel(
        index=document.index,
        startPage=document.start_page,
        endPage=document.end_page,
        pageCount=document.page_count,
        firstPageOcrRaw=document.first_page.ocrTextRaw,
        firstPageOcrNormalized=document.first_page.ocrTextNormalized,
        firstPageOcrCompact=document.first_page.ocrTextCompact,
        acceptedCandidateCount=len(accepted_candidates),
        candidates=candidates,
        assignedRow=assigned_row,
        blockedReason=blocked_reason,
    )
    return (
        document_model,
        issues,
        assigned_row.rowNumber if assigned_row is not None else None,
    )


def finalize_lot_documents(
    *,
    documents: list[LotDocumentModel],
    issues: list[LotIssueModel],
    claimed_rows: dict[int, list[int]],
) -> tuple[list[LotDocumentModel], list[LotIssueModel], bool]:
    duplicate_rows = {
        row_number: document_indexes
        for row_number, document_indexes in claimed_rows.items()
        if len(document_indexes) > 1
    }
    if duplicate_rows:
        document_by_index = {document.index: document for document in documents}
        for row_number, document_indexes in duplicate_rows.items():
            for document_index in document_indexes:
                document = document_by_index.get(document_index)
                if document is None:
                    continue
                document.assignedRow = None
                document.blockedReason = (
                    f"CSV row {row_number} is claimed by multiple documents"
                )
                issues.append(
                    LotIssueModel(
                        code="duplicate_row_assignment",
                        message=f"CSV row {row_number} is assigned to multiple documents",
                        documentIndex=document_index,
                        rowNumber=row_number,
                    )
                )

    validation_blocked = any(issue.severity != "warning" for issue in issues)
    return documents, issues, validation_blocked


def _build_candidates(
    page: LotSeparationPageModel, csv_rows: list[LotCsvRow]
) -> list[LotMatchCandidateModel]:
    page_compact = page.ocrTextCompact
    candidates: list[LotMatchCandidateModel] = []

    for row in csv_rows:
        commande_variants = _commande_variants(row.commande)
        commande_digits = commande_variants[0] if commande_variants else ""
        client_digits = compact_lot_digits(row.client_number)
        commande_exact = any(variant in page_compact for variant in commande_variants)
        client_exact = bool(client_digits) and client_digits in page_compact

        distributeur_expected = compact_lot_text(row.distributeur)
        client_expected = compact_lot_text(row.client)
        distributeur_match = _best_fuzzy_occurrence(distributeur_expected, page_compact)
        client_match = _best_fuzzy_occurrence(client_expected, page_compact)
        distributeur_strong = distributeur_match.score > 0.90
        client_strong = client_match.score > 0.90
        qualifies = (
            commande_exact and client_exact and distributeur_strong and client_strong
        )

        if not (commande_exact or client_exact or distributeur_strong or client_strong):
            continue

        score = (
            (0.35 if commande_exact else 0.0)
            + (0.25 if client_exact else 0.0)
            + (distributeur_match.score * 0.20)
            + (client_match.score * 0.20)
        )

        candidates.append(
            LotMatchCandidateModel(
                row=LotCsvRowModel(
                    rowNumber=row.row_number,
                    commande=row.commande,
                    clientNumber=row.client_number,
                    distributeur=row.distributeur,
                    client=row.client,
                    statut=row.statut,
                    cote=row.cote,
                    caisse=row.caisse,
                ),
                qualifies=qualifies,
                score=score,
                commandeExact=commande_exact,
                clientNumberExact=client_exact,
                distributeurScore=distributeur_match.score,
                clientScore=client_match.score,
                fieldResults=[
                    LotMatchFieldResultModel(
                        field="commande",
                        matched=commande_exact,
                        expected=row.commande,
                        normalized=" | ".join(commande_variants),
                        score=1.0 if commande_exact else 0.0,
                        occurrence=_first_matching_variant(
                            commande_variants, page_compact
                        ),
                    ),
                    LotMatchFieldResultModel(
                        field="client_number",
                        matched=client_exact,
                        expected=row.client_number,
                        normalized=client_digits,
                        score=1.0 if client_exact else 0.0,
                        occurrence=client_digits if client_exact else None,
                    ),
                    LotMatchFieldResultModel(
                        field="distributeur",
                        matched=distributeur_match.score > 0.90,
                        expected=row.distributeur,
                        normalized=distributeur_expected,
                        score=distributeur_match.score,
                        occurrence=distributeur_match.occurrence,
                    ),
                    LotMatchFieldResultModel(
                        field="client",
                        matched=client_match.score > 0.90,
                        expected=row.client,
                        normalized=client_expected,
                        score=client_match.score,
                        occurrence=client_match.occurrence,
                    ),
                ],
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.qualifies,
            candidate.commandeExact,
            candidate.clientNumberExact,
            sum(result.matched for result in candidate.fieldResults),
            candidate.score,
        ),
        reverse=True,
    )
    return candidates


def _commande_variants(value: str) -> list[str]:
    digits = compact_lot_digits(value)
    variants: list[str] = []
    if digits:
        variants.append(digits)
    if value.startswith("0") and digits:
        variants.append(compact_lot_text(f"F-{value[1:]}"))
    return list(dict.fromkeys(variant for variant in variants if variant))


def _first_matching_variant(variants: list[str], page_compact: str) -> str | None:
    for variant in variants:
        if variant in page_compact:
            return variant
    return None


def _best_fuzzy_occurrence(
    expected_compact: str, page_compact: str
) -> FuzzyOccurrenceResult:
    if not expected_compact or not page_compact:
        return FuzzyOccurrenceResult(occurrence="", score=0.0)

    if expected_compact in page_compact:
        return FuzzyOccurrenceResult(occurrence=expected_compact, score=1.0)

    target_length = len(expected_compact)
    if len(page_compact) <= target_length:
        return FuzzyOccurrenceResult(
            occurrence=page_compact,
            score=round(
                difflib.SequenceMatcher(None, expected_compact, page_compact).ratio(), 6
            ),
        )

    best_score = -1.0
    best_occurrence = ""
    limit = len(page_compact) - target_length + 1
    for start in range(limit):
        candidate = page_compact[start : start + target_length]
        score = difflib.SequenceMatcher(None, expected_compact, candidate).ratio()
        if score > best_score:
            best_score = score
            best_occurrence = candidate
            if score >= 0.999:
                break

    return FuzzyOccurrenceResult(
        occurrence=best_occurrence, score=round(max(0.0, best_score), 6)
    )
