export type ZoneType = 'text' | 'number' | 'date' | 'alphanumeric'
export type SeparationMethod = 'orb' | 'hybrid' | 'paper'

export interface Zone {
  id: string
  name: string
  type: ZoneType
  x: number
  y: number
  width: number
  height: number
  required: boolean
}

export interface IgnoreRegion {
  id: string
  name: string
  x: number
  y: number
  width: number
  height: number
}

export interface PaperFeatureArtifact {
  detector: 'orb' | 'surf'
  artifactPath: string
  maxKeypoints: number
  epsilon: number
  synthesizedImageCount: number
  buildWidth: number
  buildHeight: number
  createdAt: string
  version: number
}

export interface TemplateSummary {
  id: string
  name: string
  zoneCount: number
  updatedAt: string
  thumbnailPath: string
}

export interface Template {
  id: string
  name: string
  imagePath: string
  imageWidth: number
  imageHeight: number
  zones: Zone[]
  paperIgnoreRegions: IgnoreRegion[]
  paperFeatureArtifact?: PaperFeatureArtifact | null
  useWolfBinarization: boolean
  createdAt: string
  updatedAt: string
  version: number
}

export interface CreateTemplatePayload {
  name: string
  image: File
  zones: Zone[]
  paperIgnoreRegions: IgnoreRegion[]
  useWolfBinarization: boolean
}

export interface UpdateTemplatePayload {
  name: string
  zones: Zone[]
  paperIgnoreRegions: IgnoreRegion[]
  useWolfBinarization: boolean
}

export interface ExtractField {
  zoneName: string
  text: string
  confidence: number
  bbox: {
    x: number
    y: number
    width: number
    height: number
  }
  warning?: string
  matchedWordIds: number[]
}

export interface OCRWordBox {
  id: number
  text: string
  confidence: number
  matched: boolean
  bbox: {
    x: number
    y: number
    width: number
    height: number
  }
}

export interface ExtractResponse {
  templateId: string
  ocrEngine: string
  alignment: {
    success: boolean
    inlierRatio: number
    matchesUsed: number
    warnings: string[]
  }
  preview: {
    templatePath: string
    uploadedPath: string
    alignedPath?: string | null
    overlayPath?: string | null
    templateBinarizedPath?: string | null
    uploadedBinarizedPath?: string | null
  }
  debug: {
    imageWidth: number
    imageHeight: number
    ocrWords: OCRWordBox[]
  }
  fields: ExtractField[]
  errors: string[]
}

export interface LogicalSeparationPageMatch {
  pageNumber: number
  matched: boolean
  method: string
  binarized: boolean
  score: number
  inlierRatio?: number | null
  matchesUsed?: number | null
  visualScore?: number | null
  orbScore?: number | null
  warnings: string[]
  error?: string | null
}

export interface LogicalDocumentRange {
  index: number
  startPage: number
  endPage: number
  pageCount: number
}

export interface LogicalSeparationResponse {
  templateId: string
  method: SeparationMethod
  threshold: number
  totalPages: number
  matchedStartPages: number[]
  documents: LogicalDocumentRange[]
  pageMatches: LogicalSeparationPageMatch[]
  warnings: string[]
  errors: string[]
}

export interface LogicalSeparationStartedEvent {
  type: 'started'
  templateId: string
  method: SeparationMethod
  threshold: number
  templateBinarized: boolean
}

export interface LogicalSeparationPageEvent {
  type: 'page'
  pageMatch: LogicalSeparationPageMatch
}

export interface LogicalSeparationCompleteEvent {
  type: 'complete'
  result: LogicalSeparationResponse
}

export interface LogicalSeparationErrorEvent {
  type: 'error'
  error: string
}

export type LogicalSeparationStreamEvent =
  | LogicalSeparationStartedEvent
  | LogicalSeparationPageEvent
  | LogicalSeparationCompleteEvent
  | LogicalSeparationErrorEvent
