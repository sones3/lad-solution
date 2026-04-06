import { buildApiUrl, request } from './client'
import type { LotFolder, LotProcessEvent, LotProcessSummary } from '../types/lot'

export function listLotFolders(): Promise<LotFolder[]> {
  return request<LotFolder[]>('/lots/folders')
}

export async function processLotFolder(
  lotName: string,
  payload: {
    templateId: string
    paperThreshold: number
    confirmRegenerate: boolean
  },
  onEvent?: (event: LotProcessEvent) => void,
): Promise<LotProcessSummary> {
  const response = await fetch(buildApiUrl(`/lots/folders/${encodeURIComponent(lotName)}/process/stream`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
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
  let finalSummary: LotProcessSummary | null = null

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.trim()) {
        continue
      }

      const event = JSON.parse(line) as LotProcessEvent
      onEvent?.(event)
      if (event.type === 'error') {
        throw new Error(event.error)
      }
      if (event.type === 'complete') {
        finalSummary = event.summary
      }
    }

    if (done) {
      break
    }
  }

  if (!finalSummary) {
    throw new Error('Lot processing stream ended before completion')
  }

  return finalSummary
}
