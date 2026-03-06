const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

interface RequestOptions {
  method?: HttpMethod
  body?: BodyInit | null
  headers?: Record<string, string>
}

export const buildApiUrl = (path: string): string => {
  return `${API_BASE_URL}${path}`
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: options.method ?? 'GET',
    body: options.body,
    headers: options.headers,
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

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
