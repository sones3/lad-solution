import { useMemo, useState } from 'react'
import { buildApiUrl } from '../api/client'
import type { ExtractResponse, TemplateSummary } from '../types/template'

interface ExtractionPageProps {
  templates: TemplateSummary[]
  onExtract: (templateId: string, file: File) => Promise<ExtractResponse>
}

export function ExtractionPage({ templates, onExtract }: ExtractionPageProps) {
  const [templateId, setTemplateId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ExtractResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const canRun = useMemo(() => templateId !== '' && file !== null, [file, templateId])

  const handleRun = async () => {
    if (!file || !templateId) {
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    try {
      const extraction = await onExtract(templateId, file)
      setResult(extraction)
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Extraction failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="panel">
      <h2>Extract from new document</h2>
      <p>Pick a saved template, upload a similar document image, and run ORB alignment + OCR extraction.</p>

      <div className="extract-form">
        <label>
          Template
          <select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
            <option value="">Select template</option>
            {templates.map((template) => (
              <option value={template.id} key={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Document image
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>

        <button type="button" disabled={!canRun || loading} onClick={handleRun}>
          {loading ? 'Extracting...' : 'Run extraction'}
        </button>
      </div>

      {error ? <p className="message">{error}</p> : null}

      {result ? (
        <section className="results-panel">
          <h3>Alignment</h3>
          <p>
            Success: <strong>{result.alignment.success ? 'yes' : 'no'}</strong> | Matches:{' '}
            {result.alignment.matchesUsed} | Inlier ratio: {result.alignment.inlierRatio.toFixed(3)}
          </p>
          {result.alignment.warnings.length > 0 ? (
            <ul>
              {result.alignment.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          <div className="alignment-grid">
            <figure>
              <img src={buildApiUrl(result.preview.templatePath)} alt="Template reference" />
              <figcaption>Template</figcaption>
            </figure>
            <figure>
              <img src={buildApiUrl(result.preview.uploadedPath)} alt="Uploaded document" />
              <figcaption>Uploaded</figcaption>
            </figure>
            {result.preview.alignedPath ? (
              <figure>
                <img src={buildApiUrl(result.preview.alignedPath)} alt="Aligned uploaded document" />
                <figcaption>Aligned to template</figcaption>
              </figure>
            ) : null}
            {result.preview.overlayPath ? (
              <figure>
                <img src={buildApiUrl(result.preview.overlayPath)} alt="Template and aligned overlay" />
                <figcaption>Overlay check</figcaption>
              </figure>
            ) : null}
          </div>

          {result.errors.length > 0 ? (
            <>
              <h3>Errors</h3>
              <ul>
                {result.errors.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </>
          ) : null}

          <h3>Extracted fields</h3>
          <table>
            <thead>
              <tr>
                <th>Zone</th>
                <th>Text</th>
                <th>Confidence</th>
                <th>Warning</th>
              </tr>
            </thead>
            <tbody>
              {result.fields.map((field) => (
                <tr key={field.zoneName}>
                  <td>{field.zoneName}</td>
                  <td>{field.text || <em>(empty)</em>}</td>
                  <td>{field.confidence.toFixed(2)}</td>
                  <td>{field.warning ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  )
}
