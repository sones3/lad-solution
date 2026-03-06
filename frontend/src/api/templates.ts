import { request } from './client'
import type {
  CreateTemplatePayload,
  Template,
  TemplateSummary,
  UpdateTemplatePayload,
} from '../types/template'

export async function listTemplates(): Promise<TemplateSummary[]> {
  return request<TemplateSummary[]>('/templates')
}

export async function getTemplate(id: string): Promise<Template> {
  return request<Template>(`/templates/${id}`)
}

export async function createTemplate(payload: CreateTemplatePayload): Promise<Template> {
  const formData = new FormData()
  formData.append('name', payload.name)
  formData.append('image', payload.image)
  formData.append('zones', JSON.stringify(payload.zones))
  formData.append('useWolfBinarization', String(payload.useWolfBinarization))

  return request<Template>('/templates', {
    method: 'POST',
    body: formData,
  })
}

export async function updateTemplate(id: string, payload: UpdateTemplatePayload): Promise<Template> {
  return request<Template>(`/templates/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}

export async function deleteTemplate(id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/templates/${id}`, {
    method: 'DELETE',
  })
}
