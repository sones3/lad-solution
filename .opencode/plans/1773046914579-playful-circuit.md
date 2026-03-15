# Lot workflow plan

## Goal

Add a new lot workflow where the user uploads one PDF and one CSV, the app separates the PDF into logical documents using the OCR-keyword method from `context/ocr_separate_documents.py`, then matches each separated document to exactly one CSV row using first-page OCR and strict reconciliation rules.

User-confirmed rules:
- separation method for lots: OCR-keyword only,
- matching OCR scope: first page only,
- reconciliation: strict,
- automatic match rule: both numeric identifiers must match exactly, and both text fields must match fuzzily with score `> 0.90`.

## Recommended approach

1. Add a dedicated lot analysis backend instead of extending template extraction.
   - Create a new route module such as `backend/app/api/lots.py`.
   - Add a streamed analysis route such as `POST /lots/analyze/stream` that accepts `pdf`, `csv`, and optional OCR tuning fields.
   - Keep the current extraction/template routes untouched.

2. Port the two scripts into importable backend services.
   - Extract shared text helpers from `context/ocr_separate_documents.py` and `context/match_lot67_metadata.py` into reusable backend code instead of shelling out.
   - Reuse existing app infrastructure where it already exists:
     - `backend/app/services/pdf_render.py` for PDF rendering,
     - `backend/app/services/binarization.py` for Wolf/Otsu binarization,
     - `backend/app/services/ocr_service.py` for Tesseract/Paddle plumbing where useful.
   - Create focused lot services, for example:
     - `backend/app/services/lot_separator.py`
     - `backend/app/services/lot_matcher.py`
     - `backend/app/services/lot_csv.py`

3. Implement OCR-keyword separation as a typed service.
   - Port the keyword logic from `context/ocr_separate_documents.py`:
     - normalize OCR text,
     - detect start pages with `bon de commande`, `du`, `vendeur`, `distributeur`,
     - exclude `fiche complement`,
     - support Wolf/Otsu fallback behavior.
   - Return page-level evidence and `startPages`, then infer document ranges from those starts.
   - Keep page numbering 1-based everywhere.

4. Implement CSV parsing and first-page matching as a strict reconciliation pipeline.
   - Parse semicolon CSV with BOM-tolerant loading and validate required columns:
     - `N° Commande`, `N° Client`, `Distributeur`, `Client`, `Statut`.
   - For each separated document, OCR only its first page.
   - Match against CSV rows using:
     - exact normalized digit match for `N° Commande`,
     - exact normalized digit match for `N° Client`,
     - fuzzy score `> 0.90` for `Distributeur`,
     - fuzzy score `> 0.90` for `Client`.
   - Auto-assign a row only when exactly one candidate satisfies the full rule and no row is claimed by multiple documents.
   - Treat every other case as blocking.

5. Model reconciliation issues explicitly.
   - Add lot-specific response models in a new file such as `backend/app/models/lot_models.py`.
   - Response should include:
     - lot summary,
     - parsed CSV rows,
     - page-level separation diagnostics,
     - documents with first-page OCR evidence,
     - candidate matches per document,
     - chosen match when unique,
     - blocking issues,
     - `validationBlocked`.
   - Include issue types such as:
     - `document_count_mismatch`,
     - `csv_parse_error`,
     - `no_start_pages`,
     - `no_match`,
     - `ambiguous_match`,
     - `duplicate_row_assignment`,
     - `missing_first_page_ocr`.

6. Add a separate frontend lot screen.
   - Add a new page like `frontend/src/pages/LotWorkflowPage.tsx` and a new tab/view in `frontend/src/App.tsx`.
   - Inputs: one PDF and one CSV only.
   - Stream progress by stages: CSV parsed, pages processed, documents built, matching complete.
   - Show four main panels:
     - lot summary,
     - separation results,
     - document-to-row matching table,
     - blocking issues panel.
   - Make the workflow read-only for v1: users can inspect results, but any blocking issue prevents final validation.

7. Keep matching diagnostics rich enough to debug OCR failures.
   - For each document, include the first-page OCR raw/normalized/compact text.
   - For each candidate row, include:
     - exact numeric match flags,
     - fuzzy text scores,
     - why it passed or failed.
   - This is important because the acceptance rule is strict and OCR-sensitive.

## Critical files to modify

- `backend/app/main.py`
- `backend/app/api/lots.py`
- `backend/app/models/lot_models.py`
- `backend/app/services/lot_separator.py`
- `backend/app/services/lot_matcher.py`
- `backend/app/services/lot_csv.py`
- `backend/app/services/pdf_render.py`
- `backend/app/services/binarization.py`
- `backend/app/services/ocr_service.py`
- `backend/requirements.txt`
- `frontend/src/App.tsx`
- `frontend/src/api/` (new lot client module)
- `frontend/src/pages/LotWorkflowPage.tsx`
- `frontend/src/types/` (new lot types if kept separate)
- `README.md`

## Implementation notes

- Do not invoke the scripts in `context/`; port their business rules into backend services.
- Keep the lot flow separate from template extraction and template-based separation.
- Use first-page OCR only for matching, even if other pages are available.
- Reconciliation must be deterministic and strict; do not silently accept partial matches.
- Preserve enough diagnostics to explain every blocked result.
- Accept the legacy script behavior as the starting rule set, but implement it with typed models and API responses instead of loose dicts/JSON files.

## Verification

1. Backend verification
   - Upload a known PDF + CSV lot where counts match and confirm the response returns:
     - correct `startPages`,
     - correct document ranges,
     - one unique match per document,
     - `validationBlocked = false`.
   - Test a lot where PDF document count and CSV row count differ and confirm:
     - `validationBlocked = true`,
     - a `document_count_mismatch` issue is returned.
   - Test a lot where one document has correct numeric identifiers but weak text OCR and confirm it remains unresolved.
   - Test duplicate/ambiguous candidates and confirm no auto-assignment is made.

2. Frontend verification
   - Run the new lot screen and upload one PDF + one CSV.
   - Confirm streamed progress updates while separation and matching run.
   - Confirm the UI clearly shows:
     - separated documents,
     - candidate matches,
     - chosen matches,
     - blocking issues,
     - final blocked/unblocked state.

3. Targeted tests
   - Unit tests for normalization, compact digits, fuzzy scoring, keyword detection, and exclusion logic.
   - Unit tests for CSV parsing with BOM, missing headers, blank fields, and duplicate identifiers.
   - Service tests for happy path, count mismatch, no start pages, ambiguous match, duplicate row claim, and OCR-empty first page.
   - Frontend tests for blocked vs successful lot analysis states if a test setup exists; otherwise verify manually.
