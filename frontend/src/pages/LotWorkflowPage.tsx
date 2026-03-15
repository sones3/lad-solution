import { useEffect, useMemo, useRef, useState } from 'react'
import type { TemplateSummary } from '../types/template'
import type {
  LotAnalysisResponse,
  LotAnalyzeConfig,
  LotDocument,
  LotMatchCandidate,
  LotMatchFieldResult,
  LotSeparationPage,
  LotStreamEvent,
} from '../types/lot'

interface LotWorkflowPageProps {
  templates: TemplateSummary[]
  onAnalyze: (
    pdf: File,
    csv: File,
    config: LotAnalyzeConfig,
    onEvent?: (event: LotStreamEvent) => void,
  ) => Promise<LotAnalysisResponse>
}

const DEFAULT_CONFIG: LotAnalyzeConfig = {
  separationMethod: 'ocr',
  templateId: undefined,
  paperThreshold: 0.35,
  dpi: 150,
  binarizer: 'otsu',
  lang: 'fra',
  psm: 6,
  oem: 1,
  timeout: 12,
  minKeywords: 3,
  workers: 6,
}

const DEFAULT_RECONCILIATION_WIDTHS = [68, 84, 90, 320, 126, 110, 120, 120, 180, 180]

function upsertPage(current: LotSeparationPage[], next: LotSeparationPage): LotSeparationPage[] {
  const existingIndex = current.findIndex((page) => page.pageNumber === next.pageNumber)
  if (existingIndex === -1) {
    return [...current, next].sort((left, right) => left.pageNumber - right.pageNumber)
  }

  const updated = [...current]
  updated[existingIndex] = next
  return updated.sort((left, right) => left.pageNumber - right.pageNumber)
}

function upsertDocument(current: LotDocument[], next: LotDocument): LotDocument[] {
  const existingIndex = current.findIndex((document) => document.startPage === next.startPage)
  if (existingIndex === -1) {
    return [...current, next].sort((left, right) => left.startPage - right.startPage)
  }

  const updated = [...current]
  updated[existingIndex] = next
  return updated.sort((left, right) => left.startPage - right.startPage)
}

function getBestCandidate(document: LotDocument): LotMatchCandidate | null {
  return document.candidates[0] ?? null
}

function getFieldResult(candidate: LotMatchCandidate | null, field: string): LotMatchFieldResult | null {
  if (!candidate) {
    return null
  }
  return candidate.fieldResults.find((result) => result.field === field) ?? null
}

function isDirectMatch(document: LotDocument, selectedRowNumber: string, selectedCandidate: LotMatchCandidate | null): boolean {
  return Boolean(
    document.assignedRow &&
      selectedRowNumber &&
      selectedRowNumber === String(document.assignedRow.rowNumber) &&
      selectedCandidate?.qualifies,
  )
}

function csvEscape(value: string | number | null | undefined): string {
  const stringValue = String(value ?? '')
  if (stringValue.includes(';') || stringValue.includes('"') || stringValue.includes('\n')) {
    return `"${stringValue.replaceAll('"', '""')}"`
  }
  return stringValue
}

export function LotWorkflowPage({ templates, onAnalyze }: LotWorkflowPageProps) {
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [config, setConfig] = useState<LotAnalyzeConfig>(DEFAULT_CONFIG)
  const [startedConfig, setStartedConfig] = useState<LotAnalyzeConfig | null>(null)
  const [csvRowCount, setCsvRowCount] = useState(0)
  const [pages, setPages] = useState<LotSeparationPage[]>([])
  const [documents, setDocuments] = useState<LotDocument[]>([])
  const [result, setResult] = useState<LotAnalysisResponse | null>(null)
  const [manualSelections, setManualSelections] = useState<Record<number, string>>({})
  const [requireVerification, setRequireVerification] = useState<Record<number, boolean>>({})
  const [columnWidths, setColumnWidths] = useState<number[]>(DEFAULT_RECONCILIATION_WIDTHS)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const resizeState = useRef<{ index: number; startX: number; startWidth: number } | null>(null)

  const canRun = useMemo(
    () => pdfFile !== null && csvFile !== null && (config.separationMethod !== 'paper' || Boolean(config.templateId)),
    [config.separationMethod, config.templateId, csvFile, pdfFile],
  )

  const resetResults = () => {
    setStartedConfig(null)
    setCsvRowCount(0)
    setPages([])
    setDocuments([])
    setResult(null)
    setManualSelections({})
    setRequireVerification({})
    setError('')
  }

  useEffect(() => {
    setManualSelections((current) => {
      const next = { ...current }
      for (const document of documents) {
        if (next[document.startPage]) {
          continue
        }
        const bestCandidate = getBestCandidate(document)
        const defaultRowNumber = document.assignedRow?.rowNumber ??
          (bestCandidate?.commandeExact && bestCandidate.clientNumberExact ? bestCandidate.row.rowNumber : undefined)
        if (defaultRowNumber !== undefined) {
          next[document.startPage] = String(defaultRowNumber)
        }
      }
      return next
    })

    setRequireVerification((current) => {
      const next = { ...current }
      for (const document of documents) {
        if (Object.prototype.hasOwnProperty.call(next, document.startPage)) {
          continue
        }
        next[document.startPage] = !Boolean(document.assignedRow)
      }
      return next
    })
  }, [documents])

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeState.current) {
        return
      }
      const { index, startX, startWidth } = resizeState.current
      const nextWidth = Math.max(72, startWidth + event.clientX - startX)
      setColumnWidths((current) => {
        const next = [...current]
        next[index] = nextWidth
        return next
      })
    }

    const handleMouseUp = () => {
      resizeState.current = null
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  const handleAnalyze = async () => {
    if (!pdfFile || !csvFile) {
      return
    }

    setLoading(true)
    resetResults()

    try {
      const analysis = await onAnalyze(pdfFile, csvFile, config, (event) => {
        if (event.type === 'started') {
          setStartedConfig(event.config)
          setCsvRowCount(event.csvRowCount)
        }
        if (event.type === 'page') {
          setPages((current) => upsertPage(current, event.page))
        }
        if (event.type === 'document') {
          setDocuments((current) => upsertDocument(current, event.document))
        }
      })
      setResult(analysis)
      setPages(analysis.pages)
      setDocuments(analysis.documents)
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Lot analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const displayedPages = result?.pages ?? pages
  const displayedDocuments = result?.documents ?? documents
  const summary = result?.summary
  const csvRows = result?.csvRows ?? []

  const duplicateSelections = useMemo(() => {
    const rowsBySelection = new Map<string, number[]>()
    for (const document of displayedDocuments) {
      const selectedRow = manualSelections[document.startPage]
      if (!selectedRow) {
        continue
      }
      rowsBySelection.set(selectedRow, [...(rowsBySelection.get(selectedRow) ?? []), document.startPage])
    }
    return new Set(
      [...rowsBySelection.entries()]
        .filter(([, documentStarts]) => documentStarts.length > 1)
        .map(([rowNumber]) => rowNumber),
    )
  }, [displayedDocuments, manualSelections])

  const selectionCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const document of displayedDocuments) {
      const selectedRow = manualSelections[document.startPage]
      if (!selectedRow) {
        continue
      }
      counts.set(selectedRow, (counts.get(selectedRow) ?? 0) + 1)
    }
    return counts
  }, [displayedDocuments, manualSelections])

  const unmatchedDocuments = useMemo(
    () =>
      displayedDocuments.filter((document) => {
        const selectedRow = manualSelections[document.startPage]
        return !selectedRow || duplicateSelections.has(selectedRow)
      }),
    [displayedDocuments, duplicateSelections, manualSelections],
  )

  const unmatchedCsvRows = useMemo(
    () => csvRows.filter((row) => (selectionCounts.get(String(row.rowNumber)) ?? 0) !== 1),
    [csvRows, selectionCounts],
  )

  const canExport = Boolean(
    result &&
      displayedDocuments.length > 0 &&
      displayedDocuments.every((document) => manualSelections[document.startPage]) &&
      duplicateSelections.size === 0,
  )

  const handleExport = () => {
    if (!result) {
      return
    }

    const header = [
      'Document',
      'Start Page',
      'End Page',
      'Selected Row',
      'CSV Commande',
      'Extracted Commande',
      'CSV Client Number',
      'Extracted Client Number',
      'CSV Distributeur',
      'Extracted Distributeur',
      'CSV Client',
      'Extracted Client',
      'Best Match Score',
      'Qualification',
      'Require Verification',
    ]

    const lines = [header.join(';')]
    for (const document of displayedDocuments) {
      const selectedRowNumber = manualSelections[document.startPage]
      const selectedRow = csvRows.find((row) => String(row.rowNumber) === selectedRowNumber) ?? null
      const selectedCandidate = document.candidates.find(
        (candidate) => String(candidate.row.rowNumber) === selectedRowNumber,
      ) ?? getBestCandidate(document)

      const directMatch = isDirectMatch(document, selectedRowNumber ?? '', selectedCandidate)

      const commande = getFieldResult(selectedCandidate, 'commande')
      const clientNumber = getFieldResult(selectedCandidate, 'client_number')
      const distributeur = getFieldResult(selectedCandidate, 'distributeur')
      const client = getFieldResult(selectedCandidate, 'client')

      lines.push(
        [
          document.index,
          document.startPage,
          document.endPage,
          selectedRow?.rowNumber ?? '',
          selectedRow?.commande ?? '',
          commande?.occurrence ?? '',
          selectedRow?.clientNumber ?? '',
          clientNumber?.occurrence ?? '',
          selectedRow?.distributeur ?? '',
          distributeur?.occurrence ?? '',
          selectedRow?.client ?? '',
          client?.occurrence ?? '',
          selectedCandidate?.score?.toFixed(3) ?? '',
          directMatch ? 'direct' : 'manual',
          requireVerification[document.startPage] ? 'yes' : 'no',
        ]
          .map(csvEscape)
          .join(';'),
      )
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'lot-reconciliation.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const beginResize = (index: number, clientX: number) => {
    resizeState.current = {
      index,
      startX: clientX,
      startWidth: columnWidths[index] ?? DEFAULT_RECONCILIATION_WIDTHS[index] ?? 120,
    }
  }

  return (
    <main className="panel lot-panel">
      <h2>Analyze a lot</h2>
      <p>Upload one PDF and one CSV to separate the lot into documents and reconcile each first page with a CSV row.</p>

      <div className="extract-form">
        <label>
          Lot PDF
          <input
            type="file"
            accept="application/pdf"
            onChange={(event) => {
              setPdfFile(event.target.files?.[0] ?? null)
              resetResults()
            }}
          />
        </label>

        <label>
          Lot CSV
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              setCsvFile(event.target.files?.[0] ?? null)
              resetResults()
            }}
          />
        </label>

        <label>
          Separation method
          <select
            value={config.separationMethod}
            onChange={(event) => {
              const nextMethod = event.target.value as LotAnalyzeConfig['separationMethod']
              setConfig((current) => ({
                ...current,
                separationMethod: nextMethod,
                templateId: nextMethod === 'paper' ? current.templateId ?? templates[0]?.id : undefined,
              }))
              resetResults()
            }}
          >
            <option value="ocr">OCR keyword start-page detection</option>
            <option value="paper">Paper method template matching</option>
          </select>
        </label>

        {config.separationMethod === 'paper' ? (
          <label>
            Template
            <select
              value={config.templateId ?? ''}
              onChange={(event) => {
                setConfig((current) => ({ ...current, templateId: event.target.value || undefined }))
                resetResults()
              }}
            >
              <option value="">Select template</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {config.separationMethod === 'paper' ? (
          <label>
            Paper threshold
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={config.paperThreshold}
              onChange={(event) => {
                setConfig((current) => ({ ...current, paperThreshold: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
        ) : null}

        <label>
          Min keywords
          <input
            type="number"
            min="1"
            max="4"
            value={config.minKeywords}
            onChange={(event) => {
              setConfig((current) => ({ ...current, minKeywords: Number(event.target.value) }))
              resetResults()
            }}
          />
        </label>

        <button type="button" disabled={!canRun || loading} onClick={handleAnalyze}>
          {loading ? 'Analyzing lot...' : 'Analyze lot'}
        </button>
        <button type="button" className="ghost" disabled={!canExport} onClick={handleExport}>
          Export CSV
        </button>
      </div>

      <details>
        <summary>Advanced OCR settings</summary>
        <div className="extract-form">
          <label>
            DPI
            <input
              type="number"
              min="72"
              value={config.dpi}
              onChange={(event) => {
                setConfig((current) => ({ ...current, dpi: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
          <label>
            PSM
            <input
              type="number"
              min="1"
              value={config.psm}
              onChange={(event) => {
                setConfig((current) => ({ ...current, psm: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
          <label>
            OEM
            <input
              type="number"
              min="0"
              value={config.oem}
              onChange={(event) => {
                setConfig((current) => ({ ...current, oem: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
          <label>
            Timeout
            <input
              type="number"
              min="1"
              value={config.timeout}
              onChange={(event) => {
                setConfig((current) => ({ ...current, timeout: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
          <label>
            Workers
            <input
              type="number"
              min="1"
              value={config.workers}
              onChange={(event) => {
                setConfig((current) => ({ ...current, workers: Number(event.target.value) }))
                resetResults()
              }}
            />
          </label>
        </div>
      </details>

      {error ? <p className="message">{error}</p> : null}

      {loading || result ? (
        <section className="results-panel">
          <section className="summary-panel">
            <div className="compare-head">
              <h3>Lot summary</h3>
              <p>
                {loading
                  ? `Processed ${displayedPages.length} pages and ${displayedDocuments.length} documents so far.`
                  : summary?.validationBlocked
                    ? 'Validation is blocked until every document has one unique CSV row.'
                    : 'All documents have been reconciled successfully.'}
              </p>
            </div>
            <div className="summary-grid">
              <article>
                <span>CSV rows</span>
                <strong>{summary?.csvRowCount ?? csvRowCount}</strong>
              </article>
              <article>
                <span>Pages processed</span>
                <strong>{summary?.totalPages ?? displayedPages.length}</strong>
              </article>
              <article>
                <span>Detected documents</span>
                <strong>{summary?.detectedDocumentCount ?? displayedDocuments.length}</strong>
              </article>
              <article>
                <span>Matched documents</span>
                <strong>{summary?.matchedDocumentCount ?? displayedDocuments.filter((item) => item.assignedRow).length}</strong>
              </article>
              <article>
                <span>Status</span>
                <strong>{summary ? (summary.validationBlocked ? 'blocked' : 'ready') : 'running'}</strong>
              </article>
              <article>
                <span>Method details</span>
                <strong>
                  {(startedConfig?.separationMethod ?? config.separationMethod) === 'paper'
                    ? `paper / threshold ${(startedConfig?.paperThreshold ?? config.paperThreshold).toFixed(2)} / ${(startedConfig?.templateId ?? config.templateId) || 'no template'}`
                    : `${startedConfig?.binarizer ?? config.binarizer} / ${startedConfig?.lang ?? config.lang} / ${startedConfig?.minKeywords ?? config.minKeywords} / ${startedConfig?.workers ?? config.workers}w`}
                </strong>
              </article>
            </div>
          </section>

          <section className="ocr-debug-panel">
            <h3>Live reconciliation status</h3>
            <p>
              Unmatched documents: <strong>{unmatchedDocuments.length}</strong> | Unmatched CSV rows: <strong>{unmatchedCsvRows.length}</strong>
            </p>
            {unmatchedDocuments.length > 0 ? (
              <p>Unmatched document start pages: {unmatchedDocuments.map((item) => item.startPage).join(', ')}</p>
            ) : null}
            {unmatchedCsvRows.length > 0 ? (
              <p>Unmatched CSV rows: {unmatchedCsvRows.map((item) => item.rowNumber).join(', ')}</p>
            ) : null}

            <h3>Issues and warnings</h3>
            {duplicateSelections.size > 0 ? (
              <p>Manual reconciliation still has duplicate CSV rows selected.</p>
            ) : null}
            {result && result.issues.length > 0 ? (
              <ul>
                {result.issues.map((issue, index) => (
                  <li key={`${issue.code}-${index}`}>
                    {issue.severity === 'warning' ? 'Warning: ' : ''}
                    {issue.message}
                  </li>
                ))}
              </ul>
            ) : loading ? (
              <p>Waiting for reconciliation results...</p>
            ) : (
              <p>No blocking issues detected.</p>
            )}
          </section>

          <section className="ocr-debug-panel">
            <h3>Separation pages</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Page</th>
                    <th>Method</th>
                    <th>Start</th>
                    <th>Keywords / score</th>
                    <th>Binarizer</th>
                    <th>Fallback</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedPages.map((page) => (
                    <tr key={page.pageNumber}>
                        <td>{page.pageNumber}</td>
                      <td>{page.separationMethod}</td>
                      <td>{page.isNewDocument ? 'yes' : 'no'}</td>
                      <td>{page.separationMethod === 'paper' ? (page.score?.toFixed(3) ?? '-') : page.foundKeywords.join(', ') || '-'}</td>
                      <td>{page.binarizer}</td>
                      <td>{page.fallbackUsed ? 'yes' : 'no'}</td>
                      <td>
                        {page.warnings.length > 0
                          ? page.warnings.join('; ')
                          : page.excludedPhraseFound
                          ? 'Excluded phrase found'
                          : page.missingKeywords.length > 0
                            ? `Missing: ${page.missingKeywords.join(', ')}`
                            : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="ocr-debug-panel">
            <h3>Reconciliation table</h3>
            <div className="table-scroll table-scroll-tall">
              <table className="reconcile-table">
                <colgroup>
                  {columnWidths.map((width, index) => (
                    <col key={index} style={{ width }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {[
                      'Document',
                      'Start page',
                      'Best row',
                      'CSV line',
                      'Status',
                      'Verify',
                      'Bon de commande',
                      'Client #',
                      'Distributeur',
                      'Client',
                    ].map((label, index) => (
                      <th key={label}>
                        <div className="resizable-head">
                          <span>{label}</span>
                          <button
                            type="button"
                            className="col-resizer"
                            aria-label={`Resize ${label} column`}
                            onMouseDown={(event) => beginResize(index, event.clientX)}
                          />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayedDocuments.map((document) => {
                    const bestCandidate = getBestCandidate(document)
                    const selectedRowNumber = manualSelections[document.startPage] ?? ''
                    const selectedRow = csvRows.find((row) => String(row.rowNumber) === selectedRowNumber) ?? null
                    const displayRow = selectedRow ?? bestCandidate?.row ?? null
                    const selectedCandidate = document.candidates.find(
                      (candidate) => String(candidate.row.rowNumber) === selectedRowNumber,
                    ) ?? bestCandidate
                    const commande = getFieldResult(selectedCandidate, 'commande')
                    const clientNumber = getFieldResult(selectedCandidate, 'client_number')
                    const distributeur = getFieldResult(selectedCandidate, 'distributeur')
                    const client = getFieldResult(selectedCandidate, 'client')
                    const isDuplicate = duplicateSelections.has(selectedRowNumber)
                    const directMatch = isDirectMatch(document, selectedRowNumber, selectedCandidate)

                    return (
                      <tr key={document.startPage}>
                        <td>{document.index}</td>
                        <td>{document.startPage}</td>
                        <td>{bestCandidate?.row.rowNumber ?? '-'}</td>
                        <td>
                          <select
                            value={selectedRowNumber}
                            onChange={(event) => {
                              const value = event.target.value
                              setManualSelections((current) => ({ ...current, [document.startPage]: value }))
                              const nextCandidate =
                                document.candidates.find((candidate) => String(candidate.row.rowNumber) === value) ??
                                bestCandidate
                              const isDirect = isDirectMatch(document, value, nextCandidate)
                              setRequireVerification((current) => ({
                                ...current,
                                [document.startPage]: isDirect ? current[document.startPage] ?? false : true,
                              }))
                            }}
                            disabled={!result}
                          >
                            <option value="">Choose row</option>
                            {csvRows.map((row) => (
                              <option key={row.rowNumber} value={row.rowNumber}>
                                {row.rowNumber} | {row.commande} | {row.clientNumber} | {row.distributeur} | {row.client}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          {isDuplicate
                            ? 'duplicate row'
                            : selectedCandidate?.qualifies
                              ? 'qualified'
                              : selectedRowNumber
                                ? 'manual'
                                : document.blockedReason ?? 'pending'}
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={requireVerification[document.startPage] ?? !directMatch}
                            onChange={(event) => {
                              const checked = event.target.checked
                              setRequireVerification((current) => ({ ...current, [document.startPage]: checked }))
                            }}
                            disabled={!result}
                          />
                        </td>
                        <td>
                          {commande?.matched ? commande.occurrence ?? displayRow?.commande ?? '-' : '-'}
                        </td>
                        <td>{clientNumber?.matched ? clientNumber.occurrence ?? displayRow?.clientNumber ?? '-' : '-'}</td>
                        <td>
                          {displayRow?.distributeur
                            ? `${displayRow.distributeur} (${(distributeur?.score ?? 0).toFixed(3)})`
                            : '-'}
                        </td>
                        <td>
                          {displayRow?.client
                            ? `${displayRow.client} (${(client?.score ?? 0).toFixed(3)})`
                            : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      ) : null}
    </main>
  )
}
