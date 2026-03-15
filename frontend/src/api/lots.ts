import { buildApiUrl } from './client'
import type { LotAnalysisResponse, LotAnalyzeConfig, LotStreamEvent } from '../types/lot'

export async function analyzeLot(
  pdf: File,
  csv: File,
  config: LotAnalyzeConfig,
  onEvent?: (event: LotStreamEvent) => void,
): Promise<LotAnalysisResponse> {
  const formData = new FormData()
  formData.append('pdf', pdf)
  formData.append('csv', csv)
  formData.append('separationMethod', config.separationMethod)
  if (config.templateId) {
    formData.append('templateId', config.templateId)
  }
  formData.append('paperThreshold', String(config.paperThreshold))
  formData.append('dpi', String(config.dpi))
  formData.append('binarizer', config.binarizer)
  formData.append('lang', config.lang)
  formData.append('psm', String(config.psm))
  formData.append('oem', String(config.oem))
  formData.append('timeout', String(config.timeout))
  formData.append('minKeywords', String(config.minKeywords))
  formData.append('workers', String(config.workers))

  const response = await fetch(buildApiUrl('/lots/analyze/stream'), {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const json = (await response.json()) as { detail?: string }
      if (json.detail) {
        detail = json.detail
      }
    } catch {
      // Keep fallback message for non-JSON responses.
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('Streaming response body is unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: LotAnalysisResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.trim()) {
        continue
      }

      const event = JSON.parse(line) as LotStreamEvent
      onEvent?.(event)
      if (event.type === 'error') {
        throw new Error(event.error)
      }
      if (event.type === 'complete') {
        finalResult = event.result
      }
    }

    if (done) {
      break
    }
  }

  if (!finalResult) {
    throw new Error('Lot analysis stream ended before completion')
  }

  return finalResult
}
