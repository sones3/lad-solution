import { useEffect, useMemo, useState } from 'react'
import { buildApiUrl } from '../api/client'
import { IgnoreRegionCanvas } from '../components/IgnoreRegionCanvas'
import { IgnoreRegionList } from '../components/IgnoreRegionList'
import { ImageCanvas } from '../components/ImageCanvas'
import { ZoneList } from '../components/ZoneList'
import type { IgnoreRegion, Template, Zone } from '../types/template'

type EditorMode = 'zones' | 'paperIgnoreRegions'

interface TemplateEditorPageProps {
  loading: boolean
  initialTemplate: Template | null
  onSave: (payload: {
    id?: string
    name: string
    imageFile: File | null
    zones: Zone[]
    paperIgnoreRegions: IgnoreRegion[]
    useWolfBinarization: boolean
  }) => Promise<void>
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
  const [paperIgnoreRegions, setPaperIgnoreRegions] = useState<IgnoreRegion[]>(
    initialTemplate?.paperIgnoreRegions ?? [],
  )
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null)
  const [selectedIgnoreRegionId, setSelectedIgnoreRegionId] = useState<string | null>(null)
  const [localMessage, setLocalMessage] = useState('')
  const [editorMode, setEditorMode] = useState<EditorMode>('zones')
  const [useWolfBinarization, setUseWolfBinarization] = useState(
    initialTemplate?.useWolfBinarization ?? false,
  )
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
  const saveMessage = loading
    ? 'Saving template and rebuilding paper features. Check backend logs for percentage progress.'
    : ''

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

    const usedIgnoreRegionNames = new Set<string>()
    for (const region of paperIgnoreRegions) {
      const regionName = region.name.trim()
      if (!regionName) {
        setLocalMessage('Every paper ignore region must have a name')
        return
      }
      if (usedIgnoreRegionNames.has(regionName)) {
        setLocalMessage(`Duplicate paper ignore region name: ${regionName}`)
        return
      }
      usedIgnoreRegionNames.add(regionName)
    }

    setLocalMessage('')
    await onSave({
      id: initialTemplate?.id,
      name: trimmedName,
      imageFile,
      zones: zones.map((zone) => ({ ...zone, name: zone.name.trim() })),
      paperIgnoreRegions: paperIgnoreRegions.map((region) => ({ ...region, name: region.name.trim() })),
      useWolfBinarization,
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

        <button
          type="button"
          className={useWolfBinarization ? '' : 'ghost'}
          onClick={() => setUseWolfBinarization((value) => !value)}
        >
          Wolf binarization: {useWolfBinarization ? 'Enabled' : 'Disabled'}
        </button>

        <div className="mode-switch" role="tablist" aria-label="Template editor mode">
          <button
            type="button"
            className={editorMode === 'zones' ? 'tab active' : 'tab'}
            onClick={() => setEditorMode('zones')}
          >
            Extraction zones
          </button>
          <button
            type="button"
            className={editorMode === 'paperIgnoreRegions' ? 'tab active' : 'tab'}
            onClick={() => setEditorMode('paperIgnoreRegions')}
          >
            Paper ignore regions
          </button>
        </div>

        <div className="toolbar-actions">
          <button type="button" onClick={handleSave} disabled={loading}>
            {loading ? 'Saving...' : 'Save template'}
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>

        {localMessage ? <p className="message">{localMessage}</p> : null}
        {saveMessage ? <p className="message">{saveMessage}</p> : null}
      </section>

      {editorMode === 'zones' ? (
        <>
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
        </>
      ) : (
        <>
          <IgnoreRegionCanvas
            imageUrl={imageUrl}
            regions={paperIgnoreRegions}
            selectedRegionId={selectedIgnoreRegionId}
            onSelectRegion={setSelectedIgnoreRegionId}
            onChangeRegions={setPaperIgnoreRegions}
          />

          <IgnoreRegionList
            regions={paperIgnoreRegions}
            selectedRegionId={selectedIgnoreRegionId}
            onSelect={(id) => setSelectedIgnoreRegionId(id)}
            onChange={setPaperIgnoreRegions}
          />
        </>
      )}
    </main>
  )
}
