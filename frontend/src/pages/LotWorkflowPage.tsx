import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
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

interface LotLogEntry {
  lotName: string
  label: string
  message: string
}

interface QueueResult {
  lotName: string
  status: 'success' | 'error'
  summary?: LotProcessSummary
  error?: string
}

interface LotProgressState {
  lotName: string
  stage: string
  current: number
  total: number
  message: string
}

const DEFAULT_THRESHOLD = 0.1

function getDefaultDraft(lot: LotFolder | undefined): LotDraft {
  return {
    templateId: lot?.config.templateId ?? '',
    paperThreshold: lot?.config.paperThreshold ?? DEFAULT_THRESHOLD,
  }
}

function buildLogEntry(event: LotProcessEvent, lotName: string): LotLogEntry {
  if (event.type === 'started') {
    return {
      lotName,
      label: 'started',
      message: `Started ${event.lotName} with threshold ${event.paperThreshold.toFixed(2)}`,
    }
  }
  if (event.type === 'step') {
    return {
      lotName,
      label: event.step,
      message: event.message,
    }
  }
  if (event.type === 'progress') {
    return {
      lotName,
      label: event.stage,
      message: event.message,
    }
  }
  if (event.type === 'complete') {
    return {
      lotName,
      label: 'complete',
      message: 'Processing finished',
    }
  }
  return {
    lotName,
    label: 'error',
    message: event.error,
  }
}

function handleCardKeyDown(event: KeyboardEvent<HTMLElement>, onActivate: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return
  }
  event.preventDefault()
  onActivate()
}

export function LotWorkflowPage({ templates }: LotWorkflowPageProps) {
  const [lots, setLots] = useState<LotFolder[]>([])
  const [drafts, setDrafts] = useState<Record<string, LotDraft>>({})
  const [selectedLotName, setSelectedLotName] = useState('')
  const [queuedLotNames, setQueuedLotNames] = useState<string[]>([])
  const [activeQueueLotNames, setActiveQueueLotNames] = useState<string[]>([])
  const [queueCurrentLotName, setQueueCurrentLotName] = useState('')
  const [queueResults, setQueueResults] = useState<QueueResult[]>([])
  const [loading, setLoading] = useState(false)
  const [runMode, setRunMode] = useState<'idle' | 'single' | 'queue'>('idle')
  const [logEntries, setLogEntries] = useState<LotLogEntry[]>([])
  const [currentProgress, setCurrentProgress] = useState<LotProgressState | null>(null)
  const [summary, setSummary] = useState<LotProcessSummary | null>(null)
  const [error, setError] = useState('')

  const processing = runMode !== 'idle'
  const queueProcessing = runMode === 'queue'

  const selectedLot = useMemo(
    () => lots.find((lot) => lot.name === selectedLotName) ?? null,
    [lots, selectedLotName],
  )

  const selectedDraft = selectedLot ? drafts[selectedLot.name] ?? getDefaultDraft(selectedLot) : null
  const queuedLots = useMemo(
    () => lots.filter((lot) => queuedLotNames.includes(lot.name)),
    [lots, queuedLotNames],
  )
  const queueReadyLots = useMemo(
    () => queuedLots.filter((lot) => lot.status === 'ready' && (drafts[lot.name] ?? getDefaultDraft(lot)).templateId),
    [drafts, queuedLots],
  )

  const canLaunchSingle = Boolean(selectedLot && selectedLot.status === 'ready' && selectedDraft?.templateId && !processing)
  const canLaunchQueue = Boolean(queueReadyLots.length > 0 && queueReadyLots.length === queuedLots.length && !processing)

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
      setQueuedLotNames((current) => current.filter((name) => nextLots.some((lot) => lot.name === name)))
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

  const appendLog = (entry: LotLogEntry) => {
    setLogEntries((current) => [...current, entry])
  }

  const runLot = async (lot: LotFolder) => {
    const draft = drafts[lot.name] ?? getDefaultDraft(lot)
    const summaryResult = await processLotFolder(
      lot.name,
      {
        templateId: draft.templateId,
        paperThreshold: draft.paperThreshold,
        confirmRegenerate: lot.sepPresent || lot.workbookPresent,
      },
      (event) => {
        if (event.type === 'progress') {
          setCurrentProgress({
            lotName: lot.name,
            stage: event.stage,
            current: event.current,
            total: event.total,
            message: event.message,
          })
        }
        if (event.type === 'complete' || event.type === 'error') {
          setCurrentProgress(null)
        }
        appendLog(buildLogEntry(event, lot.name))
      },
    )
    setSummary(summaryResult)
    return summaryResult
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

    setRunMode('single')
    setLogEntries([])
    setCurrentProgress(null)
    setQueueResults([])
    setActiveQueueLotNames([])
    setQueueCurrentLotName(selectedLot.name)
    setSummary(null)
    setError('')
    try {
      await runLot(selectedLot)
      await refreshLots()
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Lot processing failed')
    } finally {
      setQueueCurrentLotName('')
      setRunMode('idle')
    }
  }

  const handleQueueLaunch = async () => {
    if (!canLaunchQueue) {
      return
    }

    const queueLots = [...queueReadyLots].sort((left, right) => left.lotNumber - right.lotNumber)
    const regenerateCount = queueLots.filter((lot) => lot.sepPresent || lot.workbookPresent).length
    if (
      regenerateCount > 0 &&
      !window.confirm(
        `Queue ${queueLots.length} lots? ${regenerateCount} lot(s) already have outputs and will be archived before regeneration.`,
      )
    ) {
      return
    }

    setRunMode('queue')
    setLogEntries([])
    setCurrentProgress(null)
    setQueueResults([])
    setActiveQueueLotNames(queueLots.map((lot) => lot.name))
    setSummary(null)
    setError('')

    const nextResults: QueueResult[] = []
    for (const lot of queueLots) {
      setSelectedLotName(lot.name)
      setQueueCurrentLotName(lot.name)
      appendLog({ lotName: lot.name, label: 'queue', message: 'Queued lot started' })
      try {
        const nextSummary = await runLot(lot)
        nextResults.push({ lotName: lot.name, status: 'success', summary: nextSummary })
        setQueueResults([...nextResults])
      } catch (runError) {
        const message = runError instanceof Error ? runError.message : 'Lot processing failed'
        nextResults.push({ lotName: lot.name, status: 'error', error: message })
        setQueueResults([...nextResults])
        appendLog({ lotName: lot.name, label: 'error', message })
      }
      await refreshLots()
    }

    const failureCount = nextResults.filter((result) => result.status === 'error').length
    if (failureCount > 0) {
      setError(`${failureCount} lot(s) failed during queue processing`)
    }
    setQueueCurrentLotName('')
    setRunMode('idle')
  }

  const toggleQueuedLot = (lotName: string) => {
    setQueuedLotNames((current) =>
      current.includes(lotName) ? current.filter((name) => name !== lotName) : [...current, lotName],
    )
  }

  const selectAllReadyLots = () => {
    setQueuedLotNames(lots.filter((lot) => lot.status === 'ready').map((lot) => lot.name))
  }

  const clearQueuedLots = () => {
    setQueuedLotNames([])
  }

  const queueSuccessCount = queueResults.filter((result) => result.status === 'success').length
  const queueFailureCount = queueResults.filter((result) => result.status === 'error').length

  return (
    <main className="panel lot-workspace-panel">
      <div className="panel-title-row">
        <div>
          <h2>Lot workspace</h2>
          <p>Scan direct children of `/home/sones/lad-sep-stell`, then generate `sep/` and the reconciliation workbook.</p>
        </div>
        <button type="button" className="ghost" onClick={() => void refreshLots()} disabled={loading || processing}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div className="lot-workspace-grid">
        <section className="lot-list-panel">
          <div className="lot-list-head">
            <div>
              <h3>Detected lots</h3>
              <p>{queuedLots.length} lot(s) selected for queue</p>
            </div>
            <div className="lot-list-actions">
              <button type="button" className="ghost" onClick={selectAllReadyLots} disabled={processing || lots.length === 0}>
                Select ready
              </button>
              <button type="button" className="ghost" onClick={clearQueuedLots} disabled={processing || queuedLotNames.length === 0}>
                Clear queue
              </button>
              <button type="button" onClick={() => void handleQueueLaunch()} disabled={!canLaunchQueue || loading}>
                {queueProcessing ? 'Processing queue...' : `Process queue (${queuedLots.length})`}
              </button>
            </div>
          </div>

          {lots.length === 0 ? <p>No `VN LOT X` folders detected.</p> : null}
          {queuedLots.length > 0 && !canLaunchQueue ? (
            <p className="message">Every queued lot must be ready and have a selected template.</p>
          ) : null}

          <div className="lot-list">
            {lots.map((lot) => {
              const isQueued = queuedLotNames.includes(lot.name)
              return (
                <article
                  key={lot.name}
                  className={lot.name === selectedLotName ? 'lot-card active' : 'lot-card'}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedLotName(lot.name)}
                  onKeyDown={(event) => handleCardKeyDown(event, () => setSelectedLotName(lot.name))}
                >
                  <div className="lot-card-head">
                    <strong>{lot.name}</strong>
                    <label className="lot-queue-toggle" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isQueued}
                        onChange={() => toggleQueuedLot(lot.name)}
                        disabled={processing}
                      />
                      <span>Queue</span>
                    </label>
                  </div>

                  <span>{lot.status}</span>
                  <small>
                    PDF {lot.pdfPresent ? 'yes' : 'no'} | CSV {lot.csvPresent ? 'yes' : 'no'} | sep {lot.sepPresent ? 'yes' : 'no'} | workbook {lot.workbookPresent ? 'yes' : 'no'}
                  </small>
                  <small>Updated {new Date(lot.lastModified).toLocaleString()}</small>
                </article>
              )
            })}
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

                <button type="button" onClick={() => void handleLaunch()} disabled={!canLaunchSingle || loading}>
                  {runMode === 'single' ? 'Processing lot...' : 'Generate workbook'}
                </button>
              </div>

              {summary ? (
                <section className="summary-panel">
                  <div className="compare-head">
                    <h3>Latest result</h3>
                    <p>Generation completed for the latest processed lot.</p>
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

              {currentProgress ? (
                <section className="summary-panel">
                  <div className="compare-head">
                    <h3>Current progress</h3>
                    <p>
                      {currentProgress.lotName} · {currentProgress.current}/{currentProgress.total}
                    </p>
                  </div>
                  <div className="progress-panel">
                    <div className="progress-bar" aria-hidden="true">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${Math.max(0, Math.min(100, (currentProgress.current / currentProgress.total) * 100))}%` }}
                      />
                    </div>
                    <p>{currentProgress.message}</p>
                  </div>
                </section>
              ) : null}

              {activeQueueLotNames.length > 0 || queueResults.length > 0 ? (
                <section className="summary-panel">
                  <div className="compare-head">
                    <h3>Queue progress</h3>
                    <p>
                      {queueProcessing
                        ? `Running ${queueCurrentLotName} (${queueResults.length + 1}/${activeQueueLotNames.length})`
                        : `Finished ${queueSuccessCount} success / ${queueFailureCount} failed`}
                    </p>
                  </div>
                  <div className="queue-results">
                    {queueResults.map((result) => (
                      <article key={result.lotName} className={result.status === 'success' ? 'queue-result success' : 'queue-result error'}>
                        <strong>{result.lotName}</strong>
                        <span>{result.status === 'success' ? 'Done' : 'Failed'}</span>
                        {result.error ? <small>{result.error}</small> : null}
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <section className="ocr-debug-panel">
                <h3>Live processing log</h3>
                {logEntries.length === 0 && !processing ? <p>No process launched yet for this selection.</p> : null}
                <div className="lot-log">
                  {logEntries.map((entry, index) => (
                    <article key={`${entry.lotName}-${entry.label}-${index}`} className="lot-log-entry">
                      <strong>
                        {entry.lotName} · {entry.label}
                      </strong>
                      <p>{entry.message}</p>
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
