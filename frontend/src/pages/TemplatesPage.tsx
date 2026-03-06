import { buildApiUrl } from '../api/client'
import type { TemplateSummary } from '../types/template'

interface TemplatesPageProps {
  loading: boolean
  templates: TemplateSummary[]
  onCreate: () => void
  onEdit: (id: string) => void
  onDelete: (id: string) => void
}

export function TemplatesPage({ loading, templates, onCreate, onEdit, onDelete }: TemplatesPageProps) {
  return (
    <main className="panel">
      <div className="panel-title-row">
        <h2>Saved templates</h2>
        <button type="button" onClick={onCreate}>
          Create template
        </button>
      </div>

      {loading ? <p>Loading templates...</p> : null}

      {!loading && templates.length === 0 ? (
        <p>No templates yet. Create your first template to start extracting indexes.</p>
      ) : null}

      <div className="template-grid">
        {templates.map((template) => (
          <article key={template.id} className="template-card">
            <img src={buildApiUrl(template.thumbnailPath)} alt={template.name} />
            <div>
              <h3>{template.name}</h3>
              <p>{template.zoneCount} zones</p>
              <p>Updated {new Date(template.updatedAt).toLocaleString()}</p>
            </div>
            <div className="card-actions">
              <button type="button" onClick={() => onEdit(template.id)}>
                Edit zones
              </button>
              <button type="button" className="danger-link" onClick={() => onDelete(template.id)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
    </main>
  )
}
