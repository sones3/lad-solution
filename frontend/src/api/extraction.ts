import { request } from './client'
import type { ExtractResponse } from '../types/template'

export async function extractFromTemplate(
  templateId: string,
  image: File,
  ocrEngine: 'tesseract' | 'paddleocr',
): Promise<ExtractResponse> {
  const formData = new FormData()
  formData.append('templateId', templateId)
  formData.append('image', image)
  formData.append('ocrEngine', ocrEngine)

  return request<ExtractResponse>('/extract', {
    method: 'POST',
    body: formData,
  })
}
