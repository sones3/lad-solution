from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LotCsvRowModel(BaseModel):
    rowNumber: int
    commande: str
    clientNumber: str
    distributeur: str
    client: str
    statut: str
    cote: str = ""
    caisse: str = ""


class LotSeparationPageModel(BaseModel):
    pageNumber: int
    separationMethod: str = "ocr"
    foundCount: int
    foundKeywords: list[str]
    missingKeywords: list[str]
    excludedPhraseFound: bool
    isNewDocument: bool
    binarizer: str
    psm: int
    fallbackUsed: bool
    ocrTextRaw: str
    ocrTextNormalized: str
    ocrTextCompact: str
    score: float | None = None
    inlierRatio: float | None = None
    matchesUsed: int | None = None
    warnings: list[str] = Field(default_factory=list)


class LotIssueModel(BaseModel):
    code: str
    message: str
    severity: str = "error"
    documentIndex: int | None = None
    pageNumber: int | None = None
    rowNumber: int | None = None


class LotMatchFieldResultModel(BaseModel):
    field: str
    matched: bool
    expected: str
    normalized: str
    score: float | None = None
    occurrence: str | None = None


class LotMatchCandidateModel(BaseModel):
    row: LotCsvRowModel
    qualifies: bool
    score: float
    commandeExact: bool
    clientNumberExact: bool
    distributeurScore: float
    clientScore: float
    fieldResults: list[LotMatchFieldResultModel]


class LotDocumentModel(BaseModel):
    index: int
    startPage: int
    endPage: int
    pageCount: int
    firstPageOcrRaw: str
    firstPageOcrNormalized: str
    firstPageOcrCompact: str
    acceptedCandidateCount: int
    candidates: list[LotMatchCandidateModel]
    assignedRow: LotCsvRowModel | None = None
    blockedReason: str | None = None


class LotSummaryModel(BaseModel):
    totalPages: int
    csvRowCount: int
    detectedDocumentCount: int
    matchedDocumentCount: int
    validationBlocked: bool


class LotAnalysisResponseModel(BaseModel):
    summary: LotSummaryModel
    csvRows: list[LotCsvRowModel]
    pages: list[LotSeparationPageModel]
    startPages: list[int]
    documents: list[LotDocumentModel]
    issues: list[LotIssueModel]


class LotFolderConfigModel(BaseModel):
    templateId: str | None = None
    paperThreshold: float | None = None


class LotFolderModel(BaseModel):
    name: str
    lotNumber: int
    status: Literal["ready", "incomplete"]
    pdfPresent: bool
    csvPresent: bool
    sepPresent: bool
    workbookPresent: bool
    lastModified: str
    errors: list[str] = Field(default_factory=list)
    config: LotFolderConfigModel = Field(default_factory=LotFolderConfigModel)


class LotFolderProcessRequestModel(BaseModel):
    templateId: str
    paperThreshold: float = 0.1
    confirmRegenerate: bool = False


class LotProcessSummaryModel(BaseModel):
    generatedPdfCount: int
    csvRowCount: int
    autoAssignedCount: int
    needsVerificationCount: int
    ambiguousCount: int
    missingPdfCount: int
