import { useMemo, useState } from 'react'
import { buildApiUrl } from '../api/client'
import type { ExtractResponse, TemplateSummary } from '../types/template'

interface ExtractionPageProps {
  templates: TemplateSummary[]
  onExtract: (
    templateId: string,
    file: File,
    ocrEngine: 'tesseract' | 'paddleocr',
  ) => Promise<ExtractResponse>
}

function getBoxStyle(
  bbox: { x: number; y: number; width: number; height: number },
  imageWidth: number,
  imageHeight: number,
) {
  return {
    left: `${(bbox.x / imageWidth) * 100}%`,
    top: `${(bbox.y / imageHeight) * 100}%`,
    width: `${(bbox.width / imageWidth) * 100}%`,
    height: `${(bbox.height / imageHeight) * 100}%`,
  }
}

export function ExtractionPage({ templates, onExtract }: ExtractionPageProps) {
  const [templateId, setTemplateId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ExtractResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [comparePosition, setComparePosition] = useState(50)
  const [ocrEngine, setOcrEngine] = useState<'tesseract' | 'paddleocr'>('tesseract')

  const canRun = useMemo(() => templateId !== '' && file !== null, [file, templateId])

  const handleRun = async () => {
    if (!file || !templateId) {
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    setComparePosition(50)
    try {
      const extraction = await onExtract(templateId, file, ocrEngine)
      setResult(extraction)
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Extraction failed')
    } finally {
      setLoading(false)
    }
  }

  const comparisonTargetPath = result?.preview.alignedPath ?? result?.preview.uploadedPath ?? null
  const annotatedImagePath = result?.preview.alignedPath ?? null
  const templateBinarizedPath = result?.preview.templateBinarizedPath ?? null
  const uploadedBinarizedPath = result?.preview.uploadedBinarizedPath ?? null
  const debugImageWidth = result?.debug.imageWidth ?? 0
  const debugImageHeight = result?.debug.imageHeight ?? 0
  const canDrawOverlays =
    Boolean(annotatedImagePath) && debugImageWidth > 0 && debugImageHeight > 0

  const matchedWordsByField = useMemo(() => {
    if (!result) {
      return new Map<string, string>()
    }

    const wordsById = new Map(result.debug.ocrWords.map((word) => [word.id, word]))
    const data = new Map<string, string>()
    for (const field of result.fields) {
      const text = field.matchedWordIds
        .map((wordId) => wordsById.get(wordId)?.text)
        .filter((value): value is string => Boolean(value))
        .join(' ')
      data.set(field.zoneName, text)
    }
    return data
  }, [result])

  const fullPageOcrText = useMemo(() => {
    if (!result) {
      return ''
    }
    return result.debug.ocrWords.map((word) => word.text).join(' ')
  }, [result])

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
          OCR engine
          <select
            value={ocrEngine}
            onChange={(event) => setOcrEngine(event.target.value as 'tesseract' | 'paddleocr')}
          >
            <option value="tesseract">Tesseract</option>
            <option value="paddleocr">PaddleOCR v5 mobile (fr)</option>
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
          <p>
            OCR engine: <strong>{result.ocrEngine}</strong>
          </p>
          {result.alignment.warnings.length > 0 ? (
            <ul>
              {result.alignment.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          {comparisonTargetPath ? (
            <section className="compare-panel">
              <div className="compare-head">
                <h3>Before / after alignment</h3>
                <p>Slide to compare template and uploaded (aligned) document.</p>
              </div>
              <div className="compare-stage">
                <div className="compare-layer">
                  <img src={buildApiUrl(result.preview.templatePath)} alt="Template" />
                </div>
                <div
                  className="compare-layer compare-layer-top"
                  style={{ clipPath: `inset(0 ${100 - comparePosition}% 0 0)` }}
                >
                  <img src={buildApiUrl(comparisonTargetPath)} alt="Uploaded aligned" />
                </div>
                <div className="compare-divider" style={{ left: `${comparePosition}%` }} />
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={comparePosition}
                onChange={(event) => setComparePosition(Number(event.target.value))}
              />
            </section>
          ) : null}

          {templateBinarizedPath && uploadedBinarizedPath ? (
            <section className="binarized-panel">
              <div className="compare-head">
                <h3>Wolf binarized previews</h3>
                <p>Binarization applied on both template and uploaded images before alignment.</p>
              </div>
              <div className="binarized-grid">
                <figure>
                  <img src={buildApiUrl(templateBinarizedPath)} alt="Binarized template" />
                  <figcaption>Template (Wolf)</figcaption>
                </figure>
                <figure>
                  <img src={buildApiUrl(uploadedBinarizedPath)} alt="Binarized uploaded" />
                  <figcaption>Uploaded (Wolf)</figcaption>
                </figure>
              </div>
            </section>
          ) : null}

          <section className="annotated-panel">
            <div className="compare-head">
              <h3>Uploaded image with overlays</h3>
              <p>
                Cyan: OCR word boxes | Orange: extraction rectangles
                {canDrawOverlays ? '' : ' (shown once alignment succeeds)'}
              </p>
            </div>
            {annotatedImagePath ? (
              <div
                className="annotated-stage"
                style={{
                  aspectRatio: canDrawOverlays
                    ? `${result.debug.imageWidth} / ${result.debug.imageHeight}`
                    : undefined,
                }}
              >
                <img src={buildApiUrl(annotatedImagePath)} alt="Aligned uploaded document" />

                {canDrawOverlays ? (
                  <div className="annotated-overlay">
                    {result.debug.ocrWords.map((word) => (
                      <div
                        key={word.id}
                        className={word.matched ? 'ocr-word matched' : 'ocr-word'}
                        style={getBoxStyle(word.bbox, result.debug.imageWidth, result.debug.imageHeight)}
                        title={`${word.text} (${(word.confidence * 100).toFixed(1)}%)`}
                      />
                    ))}

                    {result.fields.map((field) => (
                      <div
                        key={field.zoneName}
                        className="zone-box"
                        style={getBoxStyle(field.bbox, result.debug.imageWidth, result.debug.imageHeight)}
                        title={field.zoneName}
                      >
                        <span>{field.zoneName}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p>No aligned preview available.</p>
            )}
          </section>

          <section className="ocr-debug-panel">
            <h3>OCR text (full page)</h3>
            <p className="ocr-transcript">{fullPageOcrText || '(no OCR words detected)'}</p>
            <details>
              <summary>Show OCR word list</summary>
              <table className="ocr-words-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Text</th>
                    <th>Confidence</th>
                    <th>Matched</th>
                  </tr>
                </thead>
                <tbody>
                  {result.debug.ocrWords.map((word) => (
                    <tr key={word.id}>
                      <td>{word.id}</td>
                      <td>{word.text}</td>
                      <td>{(word.confidence * 100).toFixed(1)}%</td>
                      <td>{word.matched ? 'yes' : 'no'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>

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
                <th>Matched OCR text</th>
                <th>Confidence</th>
                <th>Words</th>
                <th>Warning</th>
              </tr>
            </thead>
            <tbody>
              {result.fields.map((field) => (
                <tr key={field.zoneName}>
                  <td>{field.zoneName}</td>
                  <td>{field.text || <em>(empty)</em>}</td>
                  <td>{matchedWordsByField.get(field.zoneName) || <em>(none)</em>}</td>
                  <td>{field.confidence.toFixed(2)}</td>
                  <td>{field.matchedWordIds.length}</td>
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
