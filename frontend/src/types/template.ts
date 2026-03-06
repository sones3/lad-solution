export type ZoneType = 'text' | 'number' | 'date' | 'alphanumeric'

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
  createdAt: string
  updatedAt: string
  version: number
}

export interface CreateTemplatePayload {
  name: string
  image: File
  zones: Zone[]
}

export interface UpdateTemplatePayload {
  name: string
  zones: Zone[]
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
  }
  debug: {
    imageWidth: number
    imageHeight: number
    ocrWords: OCRWordBox[]
  }
  fields: ExtractField[]
  errors: string[]
}
