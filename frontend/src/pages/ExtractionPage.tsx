import { useMemo, useState } from 'react'
import { buildApiUrl } from '../api/client'
import type {
  ExtractResponse,
  LogicalSeparationPageMatch,
  LogicalSeparationResponse,
  LogicalSeparationStreamEvent,
  SeparationMethod,
  TemplateSummary,
} from '../types/template'

type ProcessingMode = 'extract' | 'separate'

interface ExtractionPageProps {
  templates: TemplateSummary[]
  onExtract: (
    templateId: string,
    file: File,
    ocrEngine: 'tesseract' | 'paddleocr',
  ) => Promise<ExtractResponse>
  onSeparateLogically: (
    templateId: string,
    file: File,
    method: SeparationMethod,
    threshold: number,
    onEvent?: (event: LogicalSeparationStreamEvent) => void,
  ) => Promise<LogicalSeparationResponse>
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

function formatSeparationMethod(method: SeparationMethod): string {
  if (method === 'orb') {
    return 'ORB alignment'
  }
  if (method === 'hybrid') {
    return 'Recommended hybrid'
  }
  return 'Paper method (stable ORB)'
}

function getDefaultThreshold(method: SeparationMethod): number {
  return method === 'hybrid' ? 0.55 : 0.35
}

export function ExtractionPage({
  templates,
  onExtract,
  onSeparateLogically,
}: ExtractionPageProps) {
  const [mode, setMode] = useState<ProcessingMode>('extract')
  const [templateId, setTemplateId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [separationMethod, setSeparationMethod] = useState<SeparationMethod>('paper')
  const [separationThreshold, setSeparationThreshold] = useState<number>(getDefaultThreshold('paper'))
  const [extractResult, setExtractResult] = useState<ExtractResponse | null>(null)
  const [separationResult, setSeparationResult] = useState<LogicalSeparationResponse | null>(null)
  const [streamPageMatches, setStreamPageMatches] = useState<LogicalSeparationPageMatch[]>([])
  const [templateBinarized, setTemplateBinarized] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [comparePosition, setComparePosition] = useState(50)
  const [ocrEngine, setOcrEngine] = useState<'tesseract' | 'paddleocr'>('tesseract')

  const canRun = useMemo(() => templateId !== '' && file !== null, [file, templateId])

  const clearResults = () => {
    setExtractResult(null)
    setSeparationResult(null)
    setStreamPageMatches([])
    setTemplateBinarized(null)
    setError('')
    setComparePosition(50)
  }

  const handleRun = async () => {
    if (!file || !templateId) {
      return
    }

    setLoading(true)
    clearResults()
    try {
      if (mode === 'extract') {
        const extraction = await onExtract(templateId, file, ocrEngine)
        setExtractResult(extraction)
      } else {
        const separation = await onSeparateLogically(
          templateId,
          file,
          separationMethod,
          separationThreshold,
          (event) => {
            if (event.type === 'started') {
              setTemplateBinarized(event.templateBinarized)
            }
            if (event.type === 'page') {
              setStreamPageMatches((current) => [...current, event.pageMatch])
            }
          },
        )
        setSeparationResult(separation)
        setStreamPageMatches(separation.pageMatches)
      }
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Processing failed')
    } finally {
      setLoading(false)
    }
  }

  const result = extractResult
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

  const displayedPageMatches = separationResult?.pageMatches ?? streamPageMatches
  const displayedMatchedStartPages =
    separationResult?.matchedStartPages ??
    displayedPageMatches.filter((page) => page.matched).map((page) => page.pageNumber)
  const showSeparationPanel =
    mode === 'separate' &&
    (loading || separationResult !== null || displayedPageMatches.length > 0 || templateBinarized !== null)

  return (
    <main className="panel">
      <h2>Process a document</h2>
      <p>
        Choose a saved template, then either extract fields from a document image or analyze a PDF to
        find logical document starts.
      </p>

      <div className="mode-switch" role="tablist" aria-label="Processing mode">
        <button
          type="button"
          className={mode === 'extract' ? 'tab active' : 'tab'}
          onClick={() => {
            setMode('extract')
            setFile(null)
            clearResults()
          }}
        >
          Extraction
        </button>
        <button
          type="button"
          className={mode === 'separate' ? 'tab active' : 'tab'}
          onClick={() => {
            setMode('separate')
            setFile(null)
            clearResults()
          }}
        >
          Logical separation
        </button>
      </div>

      <div className="extract-form">
        <label>
          Template
          <select
            value={templateId}
            onChange={(event) => {
              setTemplateId(event.target.value)
              clearResults()
            }}
          >
            <option value="">Select template</option>
            {templates.map((template) => (
              <option value={template.id} key={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>

        {mode === 'extract' ? (
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
        ) : null}

        {mode === 'separate' ? (
          <label>
            Detection method
            <select
              value={separationMethod}
              onChange={(event) => {
                const nextMethod = event.target.value as SeparationMethod
                setSeparationMethod(nextMethod)
                setSeparationThreshold(getDefaultThreshold(nextMethod))
                clearResults()
              }}
            >
              <option value="orb">ORB alignment</option>
              <option value="hybrid">Recommended hybrid</option>
              <option value="paper">Paper method (stable ORB)</option>
            </select>
          </label>
        ) : null}

        {mode === 'separate' ? (
          <label>
            Threshold
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={separationThreshold}
              onChange={(event) => {
                setSeparationThreshold(Number(event.target.value))
                clearResults()
              }}
            />
          </label>
        ) : null}

        <label>
          {mode === 'extract' ? 'Document image' : 'PDF document'}
          <input
            key={mode}
            type="file"
            accept={mode === 'extract' ? 'image/png,image/jpeg' : 'application/pdf'}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null)
              clearResults()
            }}
          />
        </label>

        <button type="button" disabled={!canRun || loading} onClick={handleRun}>
          {loading
            ? mode === 'extract'
              ? 'Extracting...'
              : 'Analyzing...'
            : mode === 'extract'
              ? 'Run extraction'
              : 'Analyze PDF'}
        </button>
      </div>

      {error ? <p className="message">{error}</p> : null}

      {showSeparationPanel ? (
        <section className="results-panel">
          <section className="summary-panel">
            <div className="compare-head">
              <h3>Logical separation result</h3>
              <p>
                {loading
                  ? `Processing pages... ${displayedPageMatches.length} page${displayedPageMatches.length === 1 ? '' : 's'} analyzed so far.`
                  : 'Each matched template page is treated as the start of a document.'}
              </p>
            </div>
            <div className="summary-grid">
              <article>
                <span>{separationResult ? 'Total pages' : 'Pages processed'}</span>
                <strong>{separationResult ? separationResult.totalPages : displayedPageMatches.length}</strong>
              </article>
              <article>
                <span>Detected documents</span>
                <strong>
                  {separationResult ? separationResult.documents.length : displayedMatchedStartPages.length}
                </strong>
              </article>
              <article>
                <span>Matched start pages</span>
                <strong>
                  {displayedMatchedStartPages.length > 0
                    ? displayedMatchedStartPages.join(', ')
                    : 'none'}
                </strong>
              </article>
              <article>
                <span>Detection method</span>
                <strong>{formatSeparationMethod(separationResult?.method ?? separationMethod)}</strong>
              </article>
              <article>
                <span>Threshold</span>
                <strong>{(separationResult?.threshold ?? separationThreshold).toFixed(2)}</strong>
              </article>
              <article>
                <span>Template binarized</span>
                <strong>
                  {templateBinarized === null ? 'pending' : templateBinarized ? 'yes' : 'no'}
                </strong>
              </article>
            </div>
          </section>

          <section className="ocr-debug-panel">
            <h3>Logical documents</h3>
            {separationResult && separationResult.documents.length > 0 ? (
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Start page</th>
                    <th>End page</th>
                    <th>Page count</th>
                  </tr>
                </thead>
                <tbody>
                  {separationResult.documents.map((document) => (
                    <tr key={document.index}>
                      <td>{document.index}</td>
                      <td>{document.startPage}</td>
                      <td>{document.endPage}</td>
                      <td>{document.pageCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : loading ? (
              <p>Document ranges will appear once all pages are processed.</p>
            ) : (
              <p>No logical documents detected for this template.</p>
            )}
          </section>

          {separationResult && separationResult.warnings.length > 0 ? (
            <section className="ocr-debug-panel">
              <h3>Warnings</h3>
              <ul>
                {separationResult.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {separationResult && separationResult.errors.length > 0 ? (
            <section className="ocr-debug-panel">
              <h3>Errors</h3>
              <ul>
                {separationResult.errors.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="ocr-debug-panel">
            <h3>Page diagnostics</h3>
            <table>
              <thead>
                <tr>
                  <th>Page</th>
                  <th>Matched</th>
                  <th>Binarized</th>
                  <th>Score</th>
                  <th>Matches</th>
                  <th>Inlier ratio</th>
                  <th>Visual</th>
                  <th>ORB confirm</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {displayedPageMatches.map((page) => (
                  <tr key={page.pageNumber}>
                    <td>{page.pageNumber}</td>
                    <td>{page.matched ? 'yes' : 'no'}</td>
                    <td>{page.binarized ? 'yes' : 'no'}</td>
                    <td>{page.score.toFixed(3)}</td>
                    <td>{page.matchesUsed ?? '-'}</td>
                    <td>{page.inlierRatio != null ? page.inlierRatio.toFixed(3) : '-'}</td>
                    <td>{page.visualScore != null ? page.visualScore.toFixed(3) : '-'}</td>
                    <td>{page.orbScore != null ? page.orbScore.toFixed(3) : '-'}</td>
                    <td>
                      {[...(page.error ? [page.error] : []), ...page.warnings].join(' | ') || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </section>
      ) : null}

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
