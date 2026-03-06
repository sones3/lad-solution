import { request } from './client'
import type { ExtractResponse } from '../types/template'

export async function extractFromTemplate(templateId: string, image: File): Promise<ExtractResponse> {
  const formData = new FormData()
  formData.append('templateId', templateId)
  formData.append('image', image)

  return request<ExtractResponse>('/extract', {
    method: 'POST',
    body: formData,
  })
}
