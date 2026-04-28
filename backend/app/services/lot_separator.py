from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import repeat
import re
import unicodedata

import cv2
import numpy as np

from app.models.lot_models import LotSeparationPageModel
from app.models.template_models import TemplateModel
from app.services.paper_align import align_document_with_paper_features
from app.services.binarization import to_bgr, wolf_binarize
from app.services.ocr_service import OCRTextConfig, run_text_ocr
from app.services.pdf_render import get_pdf_page_count, render_pdf_page
from app.services.template_feature_store import PaperTemplateFeatures

KEYWORDS = ("bon de commande", "du", "vendeur", "distributeur")
EXCLUSION_PHRASE = "fiche complement"


@dataclass(frozen=True)
class LotSeparatorConfig:
    separation_method: str = "ocr"
    template_id: str | None = None
    paper_threshold: float = 0.35
    dpi: int = 150
    binarizer: str = "otsu"
    lang: str = "fra"
    psm: int = 6
    oem: int = 1
    timeout: int = 12
    min_keywords: int = 3
    workers: int = 6


@dataclass(frozen=True)
class KeywordMatchResult:
    found_count: int
    found_keywords: list[str]
    missing_keywords: list[str]
    excluded_phrase_found: bool
    is_new_document: bool


def normalize_lot_text(text: str) -> str:
    lowered = text.casefold()
    lowered = re.sub(r"[\u00E8\u00E9\u00EA\u00EB]", "e", lowered)
    decomposed = unicodedata.normalize("NFKD", lowered)
    no_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9\s]", " ", no_accents)
    return re.sub(r"\s+", " ", normalized).strip()


def compact_lot_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_lot_text(text))


def compact_lot_digits(text: str) -> str:
    return re.sub(r"\D+", "", text)


def analyze_lot_pdf(
    pdf_bytes: bytes,
    *,
    config: LotSeparatorConfig,
) -> tuple[list[LotSeparationPageModel], list[int]]:
    page_results: list[LotSeparationPageModel] = list(
        iter_lot_pdf_pages(pdf_bytes, config=config)
    )

    start_pages = [page.pageNumber for page in page_results if page.isNewDocument]
    return page_results, start_pages


def iter_lot_pdf_pages(
    pdf_bytes: bytes,
    *,
    config: LotSeparatorConfig,
) -> Iterator[LotSeparationPageModel]:
    if config.separation_method == "paper":
        raise ValueError("Paper lot separation requires a template-aware iterator")

    workers = max(1, config.workers)
    total_pages = get_pdf_page_count(pdf_bytes)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Future[LotSeparationPageModel], int] = {}
        for page_number in range(1, total_pages + 1):
            futures[
                executor.submit(
                    _process_pdf_page,
                    pdf_bytes=pdf_bytes,
                    page_number=page_number,
                    config=config,
                )
            ] = page_number

        for future in as_completed(futures):
            yield future.result()


def _process_pdf_page(
    *, pdf_bytes: bytes, page_number: int, config: LotSeparatorConfig
) -> LotSeparationPageModel:
    page_image = render_pdf_page(pdf_bytes, page_number=page_number, dpi=config.dpi)
    return ocr_lot_page(page_number=page_number, image=page_image, config=config)


def iter_lot_pdf_pages_with_paper(
    pdf_bytes: bytes,
    *,
    config: LotSeparatorConfig,
    template: TemplateModel,
    template_image: np.ndarray,
    template_features: PaperTemplateFeatures,
) -> Iterator[LotSeparationPageModel]:
    if template.paperFeatureArtifact is None:
        raise ValueError("Template is missing paper feature metadata")

    build_width = template.paperFeatureArtifact.buildWidth
    build_height = template.paperFeatureArtifact.buildHeight
    resized_template = cv2.resize(
        template_image, (build_width, build_height), interpolation=cv2.INTER_AREA
    )
    total_pages = get_pdf_page_count(pdf_bytes)
    if total_pages <= 0:
        return

    workers = max(1, min(config.workers, total_pages))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(
            _process_pdf_page_with_paper,
            range(1, total_pages + 1),
            repeat(pdf_bytes),
            repeat(config),
            repeat(resized_template),
            repeat(template_features),
            repeat(build_width),
            repeat(build_height),
        )


def _process_pdf_page_with_paper(
    page_number: int,
    pdf_bytes: bytes,
    config: LotSeparatorConfig,
    resized_template: np.ndarray,
    template_features: PaperTemplateFeatures,
    build_width: int,
    build_height: int,
) -> LotSeparationPageModel:
    page_image = render_pdf_page(pdf_bytes, page_number=page_number, dpi=config.dpi)
    resized_page = cv2.resize(
        page_image, (build_width, build_height), interpolation=cv2.INTER_AREA
    )
    alignment_result = align_document_with_paper_features(
        template_image=resized_template,
        template_features=template_features,
        input_image=resized_page,
        warp=False,
    )
    score = alignment_result.inlier_ratio if alignment_result.success else 0.0
    matched = alignment_result.success and score >= config.paper_threshold
    if matched:
        ocr_page = ocr_lot_page(
            page_number=page_number, image=page_image, config=config
        )
        return LotSeparationPageModel(
            pageNumber=page_number,
            separationMethod="paper",
            foundCount=ocr_page.foundCount,
            foundKeywords=ocr_page.foundKeywords,
            missingKeywords=ocr_page.missingKeywords,
            excludedPhraseFound=ocr_page.excludedPhraseFound,
            isNewDocument=True,
            binarizer=ocr_page.binarizer,
            psm=ocr_page.psm,
            fallbackUsed=ocr_page.fallbackUsed,
            ocrTextRaw=ocr_page.ocrTextRaw,
            ocrTextNormalized=ocr_page.ocrTextNormalized,
            ocrTextCompact=ocr_page.ocrTextCompact,
            score=score,
            inlierRatio=alignment_result.inlier_ratio,
            matchesUsed=alignment_result.matches_used,
            warnings=list(alignment_result.warnings),
        )

    return LotSeparationPageModel(
        pageNumber=page_number,
        separationMethod="paper",
        foundCount=0,
        foundKeywords=[],
        missingKeywords=[],
        excludedPhraseFound=False,
        isNewDocument=False,
        binarizer="none",
        psm=config.psm,
        fallbackUsed=False,
        ocrTextRaw="",
        ocrTextNormalized="",
        ocrTextCompact="",
        score=score,
        inlierRatio=alignment_result.inlier_ratio,
        matchesUsed=alignment_result.matches_used,
        warnings=list(alignment_result.warnings),
    )


def ocr_lot_page(
    *, page_number: int, image: np.ndarray, config: LotSeparatorConfig
) -> LotSeparationPageModel:
    top_half = image[: max(1, image.shape[0] // 2), :]
    gray = cv2.cvtColor(top_half, cv2.COLOR_BGR2GRAY)
    methods = ["otsu"]

    raw_text = ""
    normalized_text = ""
    used_method = methods[0]
    used_psm = config.psm
    fallback_used = False

    for attempt, method in enumerate(methods):
        binary = _binarize(gray, method)
        text, error = run_text_ocr(
            to_bgr(binary),
            config=OCRTextConfig(
                lang=config.lang,
                psm=config.psm if attempt == 0 else 11,
                oem=config.oem,
                timeout=config.timeout,
            ),
        )
        raw_text = text
        used_method = method
        used_psm = config.psm if attempt == 0 else 11
        normalized_text = normalize_lot_text(text)

        if error is None and len(normalized_text) >= 15:
            break
        if attempt + 1 < len(methods):
            fallback_used = True

    match = match_lot_keywords(normalized_text, min_keywords=config.min_keywords)
    return LotSeparationPageModel(
        pageNumber=page_number,
        separationMethod="ocr",
        foundCount=match.found_count,
        foundKeywords=match.found_keywords,
        missingKeywords=match.missing_keywords,
        excludedPhraseFound=match.excluded_phrase_found,
        isNewDocument=match.is_new_document,
        binarizer=used_method,
        psm=used_psm,
        fallbackUsed=fallback_used,
        ocrTextRaw=raw_text,
        ocrTextNormalized=normalized_text,
        ocrTextCompact=compact_lot_text(normalized_text),
        warnings=[],
    )


def match_lot_keywords(text: str, *, min_keywords: int) -> KeywordMatchResult:
    patterns = {
        "bon de commande": re.compile(r"\bbon\s+de\s+commande\b"),
        "du": re.compile(r"\bdu\b"),
        "vendeur": re.compile(r"\bvendeur\b"),
        "distributeur": re.compile(r"\bdistributeur\b"),
    }
    found_keywords = [keyword for keyword in KEYWORDS if patterns[keyword].search(text)]
    found_set = set(found_keywords)
    missing_keywords = [keyword for keyword in KEYWORDS if keyword not in found_set]
    excluded_phrase_found = re.search(r"\bfiche\s+complement\b", text) is not None
    found_count = len(found_keywords)
    return KeywordMatchResult(
        found_count=found_count,
        found_keywords=found_keywords,
        missing_keywords=missing_keywords,
        excluded_phrase_found=excluded_phrase_found,
        is_new_document=found_count >= min_keywords and not excluded_phrase_found,
    )


def build_lot_documents(
    start_pages: list[int], total_pages: int
) -> list[tuple[int, int, int, int]]:
    documents: list[tuple[int, int, int, int]] = []
    for index, start_page in enumerate(start_pages, start=1):
        next_start = start_pages[index] if index < len(start_pages) else None
        end_page = total_pages if next_start is None else next_start - 1
        documents.append((index, start_page, end_page, (end_page - start_page) + 1))
    return documents


def _binarize(gray: np.ndarray, method: str) -> np.ndarray:
    if method == "wolf":
        try:
            return wolf_binarize(to_bgr(gray))
        except RuntimeError:
            return _otsu(gray)
    if method == "otsu":
        return _otsu(gray)
    try:
        return wolf_binarize(to_bgr(gray))
    except RuntimeError:
        return _otsu(gray)


def _otsu(gray: np.ndarray) -> np.ndarray:
    _, binary = cv2.threshold(
        np.ascontiguousarray(gray.astype(np.uint8)),
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    return binary
