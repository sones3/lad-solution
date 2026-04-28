export interface LotFolderConfig {
  templateId?: string | null
  paperThreshold?: number | null
}

export interface LotFolder {
  name: string
  lotNumber: number
  status: 'ready' | 'incomplete'
  pdfPresent: boolean
  csvPresent: boolean
  sepPresent: boolean
  workbookPresent: boolean
  lastModified: string
  errors: string[]
  config: LotFolderConfig
}

export interface LotProcessSummary {
  generatedPdfCount: number
  csvRowCount: number
  autoAssignedCount: number
  needsVerificationCount: number
  ambiguousCount: number
  missingPdfCount: number
}

export interface LotProcessStartedEvent {
  type: 'started'
  lotName: string
  templateId: string
  paperThreshold: number
}

export interface LotProcessStepEvent {
  type: 'step'
  step: 'archive_previous_outputs' | 'split_source_pdf' | 'run_matching' | 'generate_workbook'
  message: string
}

export interface LotProcessProgressEvent {
  type: 'progress'
  stage: 'analyze_source_pdf' | 'ocr_split_documents'
  current: number
  total: number
  message: string
}

export interface LotProcessCompleteEvent {
  type: 'complete'
  summary: LotProcessSummary
}

export interface LotProcessErrorEvent {
  type: 'error'
  error: string
}

export type LotProcessEvent =
  | LotProcessStartedEvent
  | LotProcessStepEvent
  | LotProcessProgressEvent
  | LotProcessCompleteEvent
  | LotProcessErrorEvent
