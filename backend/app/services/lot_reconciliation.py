from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import difflib

from app.services.lot_csv import LotCsvRow
from app.services.lot_separator import compact_lot_digits, compact_lot_text

STATUS_OK = "OK"
STATUS_REVIEW = "À vérifier"
STATUS_AMBIGUOUS = "Ambigu"
STATUS_MISSING_PDF = "Sans PDF"
STATUS_MANUAL = "Manuel"

DOC_STATUS_ASSIGNED = "Affecté"
DOC_STATUS_REVIEW = "À vérifier"
DOC_STATUS_AMBIGUOUS = "Ambigu"
DOC_STATUS_UNMATCHED = "Non affecté"

REASON_DUPLICATE = "Doublon possible"
REASON_MULTIPLE_EXACT = "Plusieurs exact matches"
REASON_SCORE_TIE = "Ex æquo sur le meilleur score"
REASON_UNDECIDABLE = "Affectation non tranchable"


@dataclass(frozen=True)
class ReconciliationDocumentInput:
    file_name: str
    start_page: int
    end_page: int
    page_count: int
    first_page_raw: str
    first_page_normalized: str
    first_page_compact: str


@dataclass(frozen=True)
class ReconciliationCandidate:
    row: LotCsvRow
    document: ReconciliationDocumentInput
    global_score: float
    global_score_percent: int
    commande_exact: bool
    client_number_exact: bool
    client_score: float
    distributeur_score: float
    is_exact_match: bool
    verify_fields: tuple[str, ...]

    @property
    def match_type(self) -> str:
        return "Correspondance exacte" if self.is_exact_match else "Meilleur candidat"

    @property
    def signature(self) -> tuple[int, int, int, int, int]:
        return (
            1 if self.commande_exact and self.client_number_exact else 0,
            1 if self.commande_exact else 0,
            1 if self.client_number_exact else 0,
            self.distributeur_score_percent,
            self.client_score_percent,
        )

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, float, int, int]:
        return (
            *self.signature,
            self.global_score,
            -self.row.row_number,
            -self.document.start_page,
        )

    @property
    def client_score_percent(self) -> int:
        return _to_percent(self.client_score)

    @property
    def distributeur_score_percent(self) -> int:
        return _to_percent(self.distributeur_score)


@dataclass(frozen=True)
class ReconciliationRow:
    source_row: int | None
    manual: str
    status: str
    validation_error: str
    pdf_name: str
    suggested_pdf_name: str
    detected_pdf_name: str
    start_page: int | None
    end_page: int | None
    page_count: int | None
    commande: str
    client_number: str
    distributeur: str
    client: str
    cote: str
    caisse: str
    match_type: str
    global_score: int | None
    commande_exact: str
    client_number_exact: str
    client_score: int | None
    distributeur_score: int | None
    verify_fields: str
    review_note: str
    diagnostic_reason: str


@dataclass(frozen=True)
class ReconciliationDocumentDiagnostic:
    pdf_name: str
    status: str
    start_page: int
    end_page: int
    page_count: int
    best_source_row: int | None
    global_score: int | None
    commande_exact: str
    client_number_exact: str
    client_score: int | None
    distributeur_score: int | None
    best_commande: str
    best_client_number: str
    best_distributeur: str
    best_client: str
    best_cote: str
    best_caisse: str
    reason: str


@dataclass(frozen=True)
class ReconciliationSummary:
    generated_pdf_count: int
    csv_row_count: int
    auto_assigned_count: int
    needs_verification_count: int
    ambiguous_count: int
    missing_pdf_count: int


@dataclass(frozen=True)
class ReconciliationResult:
    rows: list[ReconciliationRow]
    document_diagnostics: list[ReconciliationDocumentDiagnostic]
    summary: ReconciliationSummary


def build_reconciliation(
    *,
    csv_rows: list[LotCsvRow],
    documents: list[ReconciliationDocumentInput],
) -> ReconciliationResult:
    duplicate_rows = _find_duplicate_rows(csv_rows)
    candidates = _build_candidates(csv_rows=csv_rows, documents=documents)
    candidates_by_row = _group_candidates_by_row(candidates)
    candidates_by_document = _group_candidates_by_document(candidates)

    assigned_rows: dict[int, ReconciliationCandidate] = {}
    assigned_documents: dict[str, ReconciliationCandidate] = {}
    row_reasons: dict[int, tuple[str, str]] = {}
    document_reasons: dict[str, tuple[str, str]] = {}
    remaining_rows = {row.row_number for row in csv_rows}
    remaining_documents = {document.file_name for document in documents}

    unique_exact_candidates: list[ReconciliationCandidate] = []
    for document in documents:
        exact_candidates = [
            candidate
            for candidate in candidates_by_document.get(document.file_name, [])
            if candidate.is_exact_match
        ]
        if len(exact_candidates) == 1:
            unique_exact_candidates.append(exact_candidates[0])
            continue
        if len(exact_candidates) <= 1:
            continue

        exact_candidates = sorted(
            exact_candidates, key=lambda item: item.sort_key, reverse=True
        )
        if exact_candidates[0].signature != exact_candidates[1].signature:
            unique_exact_candidates.append(exact_candidates[0])
            continue

        reason = _build_ambiguity_reason(
            exact_candidates,
            duplicate_rows=duplicate_rows,
            exact_conflict=True,
        )
        document_reasons[document.file_name] = (STATUS_AMBIGUOUS, reason)
        remaining_documents.discard(document.file_name)
        for candidate in exact_candidates:
            row_reasons.setdefault(candidate.row.row_number, (STATUS_AMBIGUOUS, reason))
            remaining_rows.discard(candidate.row.row_number)

    blocked_exact_documents: set[str] = set()
    for candidate in sorted(
        unique_exact_candidates, key=lambda item: item.sort_key, reverse=True
    ):
        row_number = candidate.row.row_number
        document_name = candidate.document.file_name
        if row_number not in remaining_rows or document_name not in remaining_documents:
            blocked_exact_documents.add(document_name)
            continue
        assigned_rows[candidate.row.row_number] = candidate
        assigned_documents[candidate.document.file_name] = candidate
        remaining_rows.discard(row_number)
        remaining_documents.discard(document_name)

    for candidate in unique_exact_candidates:
        document_name = candidate.document.file_name
        if document_name not in blocked_exact_documents:
            continue
        document_reasons.setdefault(
            document_name,
            (STATUS_AMBIGUOUS, REASON_UNDECIDABLE),
        )
        remaining_documents.discard(document_name)

    while True:
        proposed_candidates: list[ReconciliationCandidate] = []
        for document_name in list(remaining_documents):
            available_candidates = [
                candidate
                for candidate in candidates_by_document.get(document_name, [])
                if candidate.row.row_number in remaining_rows
            ]
            if not available_candidates:
                continue

            top_candidate = available_candidates[0]
            if len(available_candidates) > 1 and (
                available_candidates[1].global_score == top_candidate.global_score
            ):
                continue
            proposed_candidates.append(top_candidate)

        if not proposed_candidates:
            break

        progress_made = False
        for candidate in sorted(
            proposed_candidates, key=lambda item: item.sort_key, reverse=True
        ):
            row_number = candidate.row.row_number
            document_name = candidate.document.file_name
            if (
                row_number not in remaining_rows
                or document_name not in remaining_documents
            ):
                continue
            assigned_rows[row_number] = candidate
            assigned_documents[document_name] = candidate
            remaining_rows.discard(row_number)
            remaining_documents.discard(document_name)
            progress_made = True

        if not progress_made:
            break

    for document_name in list(remaining_documents):
        available_candidates = [
            candidate
            for candidate in candidates_by_document.get(document_name, [])
            if candidate.row.row_number in remaining_rows
        ]
        if not available_candidates:
            continue

        top_candidate = available_candidates[0]
        top_candidates = [
            candidate
            for candidate in available_candidates
            if candidate.global_score == top_candidate.global_score
        ]
        if len(top_candidates) > 1:
            reason = _build_ambiguity_reason(
                top_candidates,
                duplicate_rows=duplicate_rows,
                exact_conflict=False,
            )
            document_reasons[document_name] = (STATUS_AMBIGUOUS, reason)
            remaining_documents.discard(document_name)
            for candidate in top_candidates:
                row_reasons.setdefault(
                    candidate.row.row_number, (STATUS_AMBIGUOUS, reason)
                )

    for row in csv_rows:
        if row.row_number in assigned_rows or row.row_number in row_reasons:
            continue
        if candidates_by_row.get(row.row_number):
            row_reasons[row.row_number] = (
                STATUS_MISSING_PDF,
                "Aucun PDF n'a pu être affecté automatiquement",
            )
        else:
            row_reasons[row.row_number] = (
                STATUS_MISSING_PDF,
                "Aucun PDF candidat disponible",
            )

    for document in documents:
        if (
            document.file_name in assigned_documents
            or document.file_name in document_reasons
        ):
            continue
        if candidates_by_document.get(document.file_name):
            document_reasons[document.file_name] = (
                DOC_STATUS_UNMATCHED,
                "Aucune ligne CSV n'a été affectée à ce PDF",
            )
        else:
            document_reasons[document.file_name] = (
                DOC_STATUS_UNMATCHED,
                "Aucune ligne candidate n'a été trouvée pour ce PDF",
            )

    rows = [
        _build_row_output(
            row=row,
            assigned_candidate=assigned_rows.get(row.row_number),
            best_candidate=(candidates_by_row.get(row.row_number) or [None])[0],
            status_and_reason=row_reasons.get(row.row_number),
        )
        for row in csv_rows
    ]
    diagnostics = [
        _build_document_diagnostic(
            document=document,
            assigned_candidate=assigned_documents.get(document.file_name),
            best_candidate=(candidates_by_document.get(document.file_name) or [None])[
                0
            ],
            status_and_reason=document_reasons.get(document.file_name),
        )
        for document in documents
    ]

    summary = ReconciliationSummary(
        generated_pdf_count=len(documents),
        csv_row_count=len(csv_rows),
        auto_assigned_count=sum(
            1 for row in rows if row.status in {STATUS_OK, STATUS_REVIEW}
        ),
        needs_verification_count=sum(1 for row in rows if row.status == STATUS_REVIEW),
        ambiguous_count=sum(1 for row in rows if row.status == STATUS_AMBIGUOUS),
        missing_pdf_count=sum(1 for row in rows if row.status == STATUS_MISSING_PDF),
    )
    return ReconciliationResult(
        rows=rows, document_diagnostics=diagnostics, summary=summary
    )


def _build_candidates(
    *,
    csv_rows: list[LotCsvRow],
    documents: list[ReconciliationDocumentInput],
) -> list[ReconciliationCandidate]:
    candidates: list[ReconciliationCandidate] = []

    for row in csv_rows:
        commande_variants = _commande_variants(row.commande)
        client_digits = compact_lot_digits(row.client_number)
        distributeur_expected = compact_lot_text(row.distributeur)
        client_expected = compact_lot_text(row.client)

        for document in documents:
            page_compact = document.first_page_compact
            commande_exact = any(
                variant and variant in page_compact for variant in commande_variants
            )
            client_number_exact = bool(client_digits) and client_digits in page_compact
            distributeur_score = _best_fuzzy_occurrence(
                distributeur_expected, page_compact
            )
            client_score = _best_fuzzy_occurrence(client_expected, page_compact)

            rule_one = (
                commande_exact
                and client_number_exact
                and (client_score >= 0.90 or distributeur_score >= 0.90)
            )
            rule_two = (
                (commande_exact or client_number_exact)
                and client_score >= 0.70
                and distributeur_score >= 0.80
            )
            verify_fields = _build_verify_fields(
                commande_exact=commande_exact,
                client_number_exact=client_number_exact,
                client_score=client_score,
                distributeur_score=distributeur_score,
            )
            global_score = (
                (35.0 if commande_exact else 0.0)
                + (35.0 if client_number_exact else 0.0)
                + (client_score * 15.0)
                + (distributeur_score * 15.0)
            )
            candidates.append(
                ReconciliationCandidate(
                    row=row,
                    document=document,
                    global_score=round(global_score, 3),
                    global_score_percent=max(0, min(100, round(global_score))),
                    commande_exact=commande_exact,
                    client_number_exact=client_number_exact,
                    client_score=round(client_score, 6),
                    distributeur_score=round(distributeur_score, 6),
                    is_exact_match=rule_one or rule_two,
                    verify_fields=verify_fields,
                )
            )

    candidates.sort(key=lambda candidate: candidate.sort_key, reverse=True)
    return candidates


def _group_candidates_by_row(
    candidates: list[ReconciliationCandidate],
) -> dict[int, list[ReconciliationCandidate]]:
    grouped: dict[int, list[ReconciliationCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.row.row_number].append(candidate)
    for group in grouped.values():
        group.sort(key=lambda candidate: candidate.sort_key, reverse=True)
    return dict(grouped)


def _group_candidates_by_document(
    candidates: list[ReconciliationCandidate],
) -> dict[str, list[ReconciliationCandidate]]:
    grouped: dict[str, list[ReconciliationCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.document.file_name].append(candidate)
    for group in grouped.values():
        group.sort(key=lambda candidate: candidate.sort_key, reverse=True)
    return dict(grouped)


def _build_row_output(
    *,
    row: LotCsvRow,
    assigned_candidate: ReconciliationCandidate | None,
    best_candidate: ReconciliationCandidate | None,
    status_and_reason: tuple[str, str] | None,
) -> ReconciliationRow:
    if assigned_candidate is not None:
        status = STATUS_OK if not assigned_candidate.verify_fields else STATUS_REVIEW
        verify_fields = "; ".join(assigned_candidate.verify_fields)
        return ReconciliationRow(
            source_row=row.row_number,
            manual="non",
            status=status,
            validation_error="",
            pdf_name=assigned_candidate.document.file_name,
            suggested_pdf_name="",
            detected_pdf_name=assigned_candidate.document.file_name,
            start_page=assigned_candidate.document.start_page,
            end_page=assigned_candidate.document.end_page,
            page_count=assigned_candidate.document.page_count,
            commande=row.commande,
            client_number=row.client_number,
            distributeur=row.distributeur,
            client=row.client,
            cote=row.cote,
            caisse=row.caisse,
            match_type=assigned_candidate.match_type,
            global_score=assigned_candidate.global_score_percent,
            commande_exact=_yes_no(assigned_candidate.commande_exact),
            client_number_exact=_yes_no(assigned_candidate.client_number_exact),
            client_score=assigned_candidate.client_score_percent,
            distributeur_score=assigned_candidate.distributeur_score_percent,
            verify_fields=verify_fields,
            review_note="",
            diagnostic_reason="",
        )

    best_document = best_candidate.document if best_candidate is not None else None
    status, reason = status_and_reason or (
        STATUS_MISSING_PDF,
        "Aucun PDF candidat disponible",
    )
    return ReconciliationRow(
        source_row=row.row_number,
        manual="non",
        status=status,
        validation_error="",
        pdf_name="",
        suggested_pdf_name=best_document.file_name
        if best_candidate is not None
        else "",
        detected_pdf_name=best_document.file_name if best_candidate is not None else "",
        start_page=best_document.start_page if best_document is not None else None,
        end_page=best_document.end_page if best_document is not None else None,
        page_count=best_document.page_count if best_document is not None else None,
        commande=row.commande,
        client_number=row.client_number,
        distributeur=row.distributeur,
        client=row.client,
        cote=row.cote,
        caisse=row.caisse,
        match_type=best_candidate.match_type if best_candidate is not None else "none",
        global_score=best_candidate.global_score_percent
        if best_candidate is not None
        else None,
        commande_exact=_yes_no(best_candidate.commande_exact)
        if best_candidate is not None
        else "",
        client_number_exact=_yes_no(best_candidate.client_number_exact)
        if best_candidate is not None
        else "",
        client_score=best_candidate.client_score_percent
        if best_candidate is not None
        else None,
        distributeur_score=best_candidate.distributeur_score_percent
        if best_candidate is not None
        else None,
        verify_fields=reason if status == STATUS_AMBIGUOUS else "",
        review_note="",
        diagnostic_reason=reason,
    )


def _build_document_diagnostic(
    *,
    document: ReconciliationDocumentInput,
    assigned_candidate: ReconciliationCandidate | None,
    best_candidate: ReconciliationCandidate | None,
    status_and_reason: tuple[str, str] | None,
) -> ReconciliationDocumentDiagnostic:
    if assigned_candidate is not None:
        status = (
            DOC_STATUS_ASSIGNED
            if not assigned_candidate.verify_fields
            else DOC_STATUS_REVIEW
        )
        reason = (
            "Affecté automatiquement"
            if status == DOC_STATUS_ASSIGNED
            else "Affecté automatiquement avec contrôle requis"
        )
        return ReconciliationDocumentDiagnostic(
            pdf_name=document.file_name,
            status=status,
            start_page=document.start_page,
            end_page=document.end_page,
            page_count=document.page_count,
            best_source_row=assigned_candidate.row.row_number,
            global_score=assigned_candidate.global_score_percent,
            commande_exact=_yes_no(assigned_candidate.commande_exact),
            client_number_exact=_yes_no(assigned_candidate.client_number_exact),
            client_score=assigned_candidate.client_score_percent,
            distributeur_score=assigned_candidate.distributeur_score_percent,
            best_commande=assigned_candidate.row.commande,
            best_client_number=assigned_candidate.row.client_number,
            best_distributeur=assigned_candidate.row.distributeur,
            best_client=assigned_candidate.row.client,
            best_cote=assigned_candidate.row.cote,
            best_caisse=assigned_candidate.row.caisse,
            reason=reason,
        )

    status, reason = status_and_reason or (
        DOC_STATUS_UNMATCHED,
        "Ce PDF n'est rattaché à aucune ligne CSV",
    )
    return ReconciliationDocumentDiagnostic(
        pdf_name=document.file_name,
        status=status,
        start_page=document.start_page,
        end_page=document.end_page,
        page_count=document.page_count,
        best_source_row=best_candidate.row.row_number
        if best_candidate is not None
        else None,
        global_score=best_candidate.global_score_percent
        if best_candidate is not None
        else None,
        commande_exact=_yes_no(best_candidate.commande_exact)
        if best_candidate is not None
        else "",
        client_number_exact=_yes_no(best_candidate.client_number_exact)
        if best_candidate is not None
        else "",
        client_score=best_candidate.client_score_percent
        if best_candidate is not None
        else None,
        distributeur_score=best_candidate.distributeur_score_percent
        if best_candidate is not None
        else None,
        best_commande=best_candidate.row.commande if best_candidate is not None else "",
        best_client_number=best_candidate.row.client_number
        if best_candidate is not None
        else "",
        best_distributeur=best_candidate.row.distributeur
        if best_candidate is not None
        else "",
        best_client=best_candidate.row.client if best_candidate is not None else "",
        best_cote=best_candidate.row.cote if best_candidate is not None else "",
        best_caisse=best_candidate.row.caisse if best_candidate is not None else "",
        reason=reason,
    )


def _build_verify_fields(
    *,
    commande_exact: bool,
    client_number_exact: bool,
    client_score: float,
    distributeur_score: float,
) -> tuple[str, ...]:
    fields: list[str] = []
    if not commande_exact:
        fields.append("Commande")
    if not client_number_exact:
        fields.append("N° Client")
    if client_score < 0.90:
        fields.append(f"Client ({_to_percent(client_score)})")
    if distributeur_score < 0.70:
        fields.append(f"Distributeur ({_to_percent(distributeur_score)})")
    return tuple(fields)


def _find_duplicate_rows(csv_rows: list[LotCsvRow]) -> set[int]:
    grouped: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for row in csv_rows:
        grouped[_row_duplicate_key(row)].append(row.row_number)

    return {
        row_number
        for row_numbers in grouped.values()
        if len(row_numbers) > 1
        for row_number in row_numbers
    }


def _row_duplicate_key(row: LotCsvRow) -> tuple[str, ...]:
    return (
        compact_lot_digits(row.commande),
        compact_lot_digits(row.client_number),
        compact_lot_text(row.distributeur),
        compact_lot_text(row.client),
        compact_lot_text(row.cote),
        compact_lot_text(row.caisse),
    )


def _build_ambiguity_reason(
    candidates: list[ReconciliationCandidate],
    *,
    duplicate_rows: set[int],
    exact_conflict: bool,
) -> str:
    if any(candidate.row.row_number in duplicate_rows for candidate in candidates):
        return REASON_DUPLICATE
    if exact_conflict:
        return REASON_MULTIPLE_EXACT
    if len(candidates) > 1:
        return REASON_SCORE_TIE
    return REASON_UNDECIDABLE


def _commande_variants(value: str) -> list[str]:
    digits = compact_lot_digits(value)
    variants: list[str] = []
    if digits:
        variants.append(digits)
    if value.startswith("0") and digits:
        variants.append(compact_lot_text(f"F-{value[1:]}"))
    return list(dict.fromkeys(variant for variant in variants if variant))


def _best_fuzzy_occurrence(expected_compact: str, page_compact: str) -> float:
    if not expected_compact or not page_compact:
        return 0.0

    if expected_compact in page_compact:
        return 1.0

    target_length = len(expected_compact)
    if len(page_compact) <= target_length:
        return round(
            difflib.SequenceMatcher(None, expected_compact, page_compact).ratio(), 6
        )

    best_score = 0.0
    limit = len(page_compact) - target_length + 1
    for start in range(limit):
        candidate = page_compact[start : start + target_length]
        score = difflib.SequenceMatcher(None, expected_compact, candidate).ratio()
        if score > best_score:
            best_score = score
            if score >= 0.999:
                break
    return round(best_score, 6)


def _to_percent(value: float) -> int:
    return max(0, min(100, round(value * 100)))


def _yes_no(value: bool) -> str:
    return "oui" if value else "non"
