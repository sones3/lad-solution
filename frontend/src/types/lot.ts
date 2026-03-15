export interface LotCsvRow {
  rowNumber: number
  commande: string
  clientNumber: string
  distributeur: string
  client: string
  statut: string
}

export interface LotSeparationPage {
  pageNumber: number
  separationMethod: string
  foundCount: number
  foundKeywords: string[]
  missingKeywords: string[]
  excludedPhraseFound: boolean
  isNewDocument: boolean
  binarizer: string
  psm: number
  fallbackUsed: boolean
  ocrTextRaw: string
  ocrTextNormalized: string
  ocrTextCompact: string
  score?: number | null
  inlierRatio?: number | null
  matchesUsed?: number | null
  warnings: string[]
}

export interface LotIssue {
  code: string
  message: string
  severity?: string
  documentIndex?: number | null
  pageNumber?: number | null
  rowNumber?: number | null
}

export interface LotMatchFieldResult {
  field: string
  matched: boolean
  expected: string
  normalized: string
  score?: number | null
  occurrence?: string | null
}

export interface LotMatchCandidate {
  row: LotCsvRow
  qualifies: boolean
  score: number
  commandeExact: boolean
  clientNumberExact: boolean
  distributeurScore: number
  clientScore: number
  fieldResults: LotMatchFieldResult[]
}

export interface LotDocument {
  index: number
  startPage: number
  endPage: number
  pageCount: number
  firstPageOcrRaw: string
  firstPageOcrNormalized: string
  firstPageOcrCompact: string
  acceptedCandidateCount: number
  candidates: LotMatchCandidate[]
  assignedRow?: LotCsvRow | null
  blockedReason?: string | null
}

export interface LotSummary {
  totalPages: number
  csvRowCount: number
  detectedDocumentCount: number
  matchedDocumentCount: number
  validationBlocked: boolean
}

export interface LotAnalysisResponse {
  summary: LotSummary
  csvRows: LotCsvRow[]
  pages: LotSeparationPage[]
  startPages: number[]
  documents: LotDocument[]
  issues: LotIssue[]
}

export interface LotAnalyzeConfig {
  separationMethod: 'ocr' | 'paper'
  templateId?: string
  paperThreshold: number
  dpi: number
  binarizer: 'auto' | 'wolf' | 'otsu'
  lang: string
  psm: number
  oem: number
  timeout: number
  minKeywords: number
  workers: number
}

export interface LotStartedEvent {
  type: 'started'
  csvRowCount: number
  config: LotAnalyzeConfig
}

export interface LotPageEvent {
  type: 'page'
  page: LotSeparationPage
}

export interface LotDocumentEvent {
  type: 'document'
  document: LotDocument
}

export interface LotCompleteEvent {
  type: 'complete'
  result: LotAnalysisResponse
}

export interface LotErrorEvent {
  type: 'error'
  error: string
}

export type LotStreamEvent = LotStartedEvent | LotPageEvent | LotDocumentEvent | LotCompleteEvent | LotErrorEvent
