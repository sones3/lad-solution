import { useEffect, useMemo, useState } from 'react'
import { createTemplate, deleteTemplate, getTemplate, listTemplates, updateTemplate } from './api/templates'
import { extractFromTemplate, separatePdfLogically } from './api/extraction'
import type {
  ExtractResponse,
  LogicalSeparationResponse,
  LogicalSeparationStreamEvent,
  SeparationMethod,
  Template,
  TemplateSummary,
  Zone,
  IgnoreRegion,
} from './types/template'
import { ExtractionPage } from './pages/ExtractionPage'
import { LotWorkflowPage } from './pages/LotWorkflowPage'
import { TemplateEditorPage } from './pages/TemplateEditorPage'
import { TemplatesPage } from './pages/TemplatesPage'

type View = 'templates' | 'editor' | 'extract' | 'lots'

function App() {
  const [view, setView] = useState<View>('templates')
  const [templates, setTemplates] = useState<TemplateSummary[]>([])
  const [activeTemplate, setActiveTemplate] = useState<Template | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const title = useMemo(() => {
    if (view === 'editor') {
      return activeTemplate ? 'Edit template' : 'Create template'
    }
    if (view === 'extract') {
      return 'Process documents'
    }
    if (view === 'lots') {
      return 'Analyze lots'
    }
    return 'Template library'
  }, [activeTemplate, view])

  const refreshTemplates = async () => {
    setLoading(true)
    setMessage('')
    try {
      const data = await listTemplates()
      setTemplates(data)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Failed to fetch templates')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshTemplates()
  }, [])

  const handleCreate = () => {
    setActiveTemplate(null)
    setView('editor')
  }

  const handleEdit = async (id: string) => {
    setLoading(true)
    setMessage('')
    try {
      const tpl = await getTemplate(id)
      setActiveTemplate(tpl)
      setView('editor')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load template')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    setLoading(true)
    setMessage('')
    try {
      await deleteTemplate(id)
      await refreshTemplates()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to delete template')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveTemplate = async (payload: {
    id?: string
    name: string
    imageFile: File | null
    zones: Zone[]
    paperIgnoreRegions: IgnoreRegion[]
    useWolfBinarization: boolean
  }) => {
    setLoading(true)
    setMessage('')
    try {
      if (payload.id) {
        await updateTemplate(payload.id, {
          name: payload.name,
          zones: payload.zones,
          paperIgnoreRegions: payload.paperIgnoreRegions,
          useWolfBinarization: payload.useWolfBinarization,
        })
      } else {
        if (!payload.imageFile) {
          throw new Error('Template image is required for new templates')
        }
        await createTemplate({
          name: payload.name,
          image: payload.imageFile,
          zones: payload.zones,
          paperIgnoreRegions: payload.paperIgnoreRegions,
          useWolfBinarization: payload.useWolfBinarization,
        })
      }
      setActiveTemplate(null)
      setView('templates')
      await refreshTemplates()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to save template')
    } finally {
      setLoading(false)
    }
  }

  const handleExtract = async (
    templateId: string,
    file: File,
    ocrEngine: 'tesseract' | 'paddleocr',
  ): Promise<ExtractResponse> => {
    return extractFromTemplate(templateId, file, ocrEngine)
  }

  const handleSeparateLogically = async (
    templateId: string,
    file: File,
    method: SeparationMethod,
    threshold: number,
    onEvent?: (event: LogicalSeparationStreamEvent) => void,
  ): Promise<LogicalSeparationResponse> => {
    return separatePdfLogically(templateId, file, method, threshold, onEvent)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Document Index Extractor</p>
          <h1>{title}</h1>
        </div>
        <nav className="tabs" aria-label="Main views">
          <button
            type="button"
            className={view === 'templates' ? 'tab active' : 'tab'}
            onClick={() => setView('templates')}
          >
            Templates
          </button>
          <button
            type="button"
            className={view === 'editor' ? 'tab active' : 'tab'}
            onClick={handleCreate}
          >
            New template
          </button>
          <button
            type="button"
            className={view === 'extract' ? 'tab active' : 'tab'}
            onClick={() => setView('extract')}
          >
            Process
          </button>
          <button
            type="button"
            className={view === 'lots' ? 'tab active' : 'tab'}
            onClick={() => setView('lots')}
          >
            Lots
          </button>
        </nav>
      </header>

      {message ? <p className="message">{message}</p> : null}

      {view === 'templates' ? (
        <TemplatesPage
          loading={loading}
          templates={templates}
          onCreate={handleCreate}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />
      ) : null}

      {view === 'editor' ? (
        <TemplateEditorPage
          key={activeTemplate?.id ?? 'new-template'}
          loading={loading}
          initialTemplate={activeTemplate}
          onSave={handleSaveTemplate}
          onCancel={() => {
            setActiveTemplate(null)
            setView('templates')
          }}
        />
      ) : null}

      {view === 'extract' ? (
        <ExtractionPage
          templates={templates}
          onExtract={handleExtract}
          onSeparateLogically={handleSeparateLogically}
        />
      ) : null}

      {view === 'lots' ? <LotWorkflowPage templates={templates} /> : null}
    </div>
  )
}

export default App
