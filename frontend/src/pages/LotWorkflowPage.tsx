import { useEffect, useMemo, useState } from 'react'
import { listLotFolders, processLotFolder } from '../api/lots'
import type { TemplateSummary } from '../types/template'
import type { LotFolder, LotProcessEvent, LotProcessSummary } from '../types/lot'

interface LotWorkflowPageProps {
  templates: TemplateSummary[]
}

interface LotDraft {
  templateId: string
  paperThreshold: number
}

const DEFAULT_THRESHOLD = 0.1

function getDefaultDraft(lot: LotFolder | undefined): LotDraft {
  return {
    templateId: lot?.config.templateId ?? '',
    paperThreshold: lot?.config.paperThreshold ?? DEFAULT_THRESHOLD,
  }
}

function describeEvent(event: LotProcessEvent): string {
  if (event.type === 'started') {
    return `Started ${event.lotName} with threshold ${event.paperThreshold.toFixed(2)}`
  }
  if (event.type === 'step') {
    return event.message
  }
  if (event.type === 'complete') {
    return 'Processing finished'
  }
  return event.error
}

export function LotWorkflowPage({ templates }: LotWorkflowPageProps) {
  const [lots, setLots] = useState<LotFolder[]>([])
  const [drafts, setDrafts] = useState<Record<string, LotDraft>>({})
  const [selectedLotName, setSelectedLotName] = useState('')
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [events, setEvents] = useState<LotProcessEvent[]>([])
  const [summary, setSummary] = useState<LotProcessSummary | null>(null)
  const [error, setError] = useState('')

  const selectedLot = useMemo(
    () => lots.find((lot) => lot.name === selectedLotName) ?? null,
    [lots, selectedLotName],
  )

  const selectedDraft = selectedLot ? drafts[selectedLot.name] ?? getDefaultDraft(selectedLot) : null
  const canLaunch = Boolean(selectedLot && selectedLot.status === 'ready' && selectedDraft?.templateId && !processing)

  const refreshLots = async () => {
    setLoading(true)
    setError('')
    try {
      const nextLots = await listLotFolders()
      setLots(nextLots)
      setDrafts((current) => {
        const next = { ...current }
        for (const lot of nextLots) {
          if (!next[lot.name]) {
            next[lot.name] = getDefaultDraft(lot)
          }
        }
        return next
      })
      setSelectedLotName((current) => {
        if (current && nextLots.some((lot) => lot.name === current)) {
          return current
        }
        return nextLots[0]?.name ?? ''
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load lots')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshLots()
  }, [])

  const updateSelectedDraft = (patch: Partial<LotDraft>) => {
    if (!selectedLot) {
      return
    }
    setDrafts((current) => ({
      ...current,
      [selectedLot.name]: {
        ...(current[selectedLot.name] ?? getDefaultDraft(selectedLot)),
        ...patch,
      },
    }))
  }

  const handleLaunch = async () => {
    if (!selectedLot || !selectedDraft?.templateId) {
      return
    }

    const needsConfirmation = selectedLot.sepPresent || selectedLot.workbookPresent
    if (
      needsConfirmation &&
      !window.confirm(
        'This will archive the current sep/ folder and reconciliation workbook, then rebuild the lot from the source PDF and CSV. Continue?',
      )
    ) {
      return
    }

    setProcessing(true)
    setEvents([])
    setSummary(null)
    setError('')
    try {
      const nextSummary = await processLotFolder(
        selectedLot.name,
        {
          templateId: selectedDraft.templateId,
          paperThreshold: selectedDraft.paperThreshold,
          confirmRegenerate: needsConfirmation,
        },
        (event) => {
          setEvents((current) => [...current, event])
        },
      )
      setSummary(nextSummary)
      await refreshLots()
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Lot processing failed')
    } finally {
      setProcessing(false)
    }
  }

  return (
    <main className="panel lot-workspace-panel">
      <div className="panel-title-row">
        <div>
          <h2>Lot workspace</h2>
          <p>Scan direct children of `/home/sones/lad-sep-stell`, then generate `sep/` and the reconciliation workbook one lot at a time.</p>
        </div>
        <button type="button" className="ghost" onClick={() => void refreshLots()} disabled={loading || processing}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div className="lot-workspace-grid">
        <section className="lot-list-panel">
          <h3>Detected lots</h3>
          {lots.length === 0 ? <p>No `VN LOT X` folders detected.</p> : null}
          <div className="lot-list">
            {lots.map((lot) => (
              <button
                key={lot.name}
                type="button"
                className={lot.name === selectedLotName ? 'lot-card active' : 'lot-card'}
                onClick={() => setSelectedLotName(lot.name)}
              >
                <strong>{lot.name}</strong>
                <span>{lot.status}</span>
                <small>
                  PDF {lot.pdfPresent ? 'yes' : 'no'} | CSV {lot.csvPresent ? 'yes' : 'no'} | sep {lot.sepPresent ? 'yes' : 'no'} | workbook {lot.workbookPresent ? 'yes' : 'no'}
                </small>
                <small>Updated {new Date(lot.lastModified).toLocaleString()}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="lot-detail-panel">
          {!selectedLot ? <p>Select a lot to inspect it.</p> : null}

          {selectedLot ? (
            <>
              <div className="compare-head">
                <h3>{selectedLot.name}</h3>
                <p>
                  Status <strong>{selectedLot.status}</strong>
                </p>
              </div>

              {selectedLot.errors.length > 0 ? (
                <div className="ocr-debug-panel">
                  <h3>Lot issues</h3>
                  <ul>
                    {selectedLot.errors.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="extract-form">
                <label>
                  Template
                  <select
                    value={selectedDraft?.templateId ?? ''}
                    onChange={(event) => updateSelectedDraft({ templateId: event.target.value })}
                    disabled={processing}
                  >
                    <option value="">Select template</option>
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Paper threshold
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={selectedDraft?.paperThreshold ?? DEFAULT_THRESHOLD}
                    onChange={(event) => updateSelectedDraft({ paperThreshold: Number(event.target.value) })}
                    disabled={processing}
                  />
                </label>

                <button type="button" onClick={() => void handleLaunch()} disabled={!canLaunch || loading}>
                  {processing ? 'Processing lot...' : 'Generate workbook'}
                </button>
              </div>

              {summary ? (
                <section className="summary-panel">
                  <div className="compare-head">
                    <h3>Latest result</h3>
                    <p>Generation completed for the selected lot.</p>
                  </div>
                  <div className="summary-grid">
                    <article>
                      <span>Generated PDFs</span>
                      <strong>{summary.generatedPdfCount}</strong>
                    </article>
                    <article>
                      <span>CSV rows</span>
                      <strong>{summary.csvRowCount}</strong>
                    </article>
                    <article>
                      <span>Auto-assigned</span>
                      <strong>{summary.autoAssignedCount}</strong>
                    </article>
                    <article>
                      <span>Needs verification</span>
                      <strong>{summary.needsVerificationCount}</strong>
                    </article>
                    <article>
                      <span>Ambiguous</span>
                      <strong>{summary.ambiguousCount}</strong>
                    </article>
                    <article>
                      <span>Without PDF</span>
                      <strong>{summary.missingPdfCount}</strong>
                    </article>
                  </div>
                </section>
              ) : null}

              <section className="ocr-debug-panel">
                <h3>Live processing log</h3>
                {events.length === 0 && !processing ? <p>No process launched yet for this selection.</p> : null}
                <div className="lot-log">
                  {events.map((event, index) => (
                    <article key={`${event.type}-${index}`} className="lot-log-entry">
                      <strong>{event.type}</strong>
                      <p>{describeEvent(event)}</p>
                    </article>
                  ))}
                </div>
                {error ? <p className="message">{error}</p> : null}
              </section>
            </>
          ) : null}
        </section>
      </div>
    </main>
  )
}
