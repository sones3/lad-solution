import { useEffect, useMemo, useState } from 'react'
import { buildApiUrl } from '../api/client'
import { ImageCanvas } from '../components/ImageCanvas'
import { ZoneList } from '../components/ZoneList'
import type { Template, Zone } from '../types/template'

interface TemplateEditorPageProps {
  loading: boolean
  initialTemplate: Template | null
  onSave: (payload: { id?: string; name: string; imageFile: File | null; zones: Zone[] }) => Promise<void>
  onCancel: () => void
}

export function TemplateEditorPage({
  loading,
  initialTemplate,
  onSave,
  onCancel,
}: TemplateEditorPageProps) {
  const [name, setName] = useState(initialTemplate?.name ?? '')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [zones, setZones] = useState<Zone[]>(initialTemplate?.zones ?? [])
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null)
  const [localMessage, setLocalMessage] = useState('')
  const objectUrl = useMemo(() => {
    if (!imageFile) {
      return null
    }
    return URL.createObjectURL(imageFile)
  }, [imageFile])

  useEffect(() => {
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [objectUrl])

  const imageUrl = objectUrl ?? (initialTemplate?.imagePath ? buildApiUrl(initialTemplate.imagePath) : null)

  const handleSave = async () => {
    const trimmedName = name.trim()
    if (!trimmedName) {
      setLocalMessage('Template name is required')
      return
    }
    if (!imageUrl) {
      setLocalMessage('Template image is required')
      return
    }
    if (zones.length === 0) {
      setLocalMessage('At least one zone is required')
      return
    }

    const usedNames = new Set<string>()
    for (const zone of zones) {
      const zoneName = zone.name.trim()
      if (!zoneName) {
        setLocalMessage('Every zone must have a name')
        return
      }
      if (usedNames.has(zoneName)) {
        setLocalMessage(`Duplicate zone name: ${zoneName}`)
        return
      }
      usedNames.add(zoneName)
    }

    setLocalMessage('')
    await onSave({
      id: initialTemplate?.id,
      name: trimmedName,
      imageFile,
      zones: zones.map((zone) => ({ ...zone, name: zone.name.trim() })),
    })
  }

  return (
    <main className="editor-layout">
      <section className="panel editor-toolbar">
        <label>
          Template name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Invoice v1"
          />
        </label>

        <label>
          Template image (PNG/JPG)
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null
              setImageFile(file)
            }}
          />
        </label>

        <div className="toolbar-actions">
          <button type="button" onClick={handleSave} disabled={loading}>
            {loading ? 'Saving...' : 'Save template'}
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>

        {localMessage ? <p className="message">{localMessage}</p> : null}
      </section>

      <ImageCanvas
        imageUrl={imageUrl}
        zones={zones}
        selectedZoneId={selectedZoneId}
        onSelectZone={setSelectedZoneId}
        onChangeZones={setZones}
      />

      <ZoneList
        zones={zones}
        selectedZoneId={selectedZoneId}
        onSelect={(id) => setSelectedZoneId(id)}
        onChange={setZones}
      />
    </main>
  )
}
