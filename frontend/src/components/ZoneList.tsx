import type { Zone, ZoneType } from '../types/template'

interface ZoneListProps {
  zones: Zone[]
  selectedZoneId: string | null
  onSelect: (id: string) => void
  onChange: (zones: Zone[]) => void
}

const zoneTypes: ZoneType[] = ['text', 'number', 'date', 'alphanumeric']

export function ZoneList({ zones, selectedZoneId, onSelect, onChange }: ZoneListProps) {
  const setZone = (id: string, updater: (zone: Zone) => Zone) => {
    onChange(
      zones.map((zone) => {
        if (zone.id !== id) {
          return zone
        }
        return updater(zone)
      }),
    )
  }

  const removeZone = (id: string) => {
    onChange(zones.filter((zone) => zone.id !== id))
  }

  return (
    <section className="zones-panel">
      <h2>Zones</h2>
      {zones.length === 0 ? <p>No zones yet. Draw on the canvas to create one.</p> : null}

      <div className="zones-list">
        {zones.map((zone) => (
          <article
            key={zone.id}
            className={selectedZoneId === zone.id ? 'zone-item active' : 'zone-item'}
            onClick={() => onSelect(zone.id)}
          >
            <label>
              Name
              <input
                value={zone.name}
                onChange={(event) => {
                  setZone(zone.id, (current) => ({ ...current, name: event.target.value }))
                }}
                placeholder="e.g. invoice_number"
              />
            </label>

            <label>
              Type
              <select
                value={zone.type}
                onChange={(event) => {
                  setZone(zone.id, (current) => ({
                    ...current,
                    type: event.target.value as ZoneType,
                  }))
                }}
              >
                {zoneTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>

            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={zone.required}
                onChange={(event) => {
                  setZone(zone.id, (current) => ({ ...current, required: event.target.checked }))
                }}
              />
              Required
            </label>

            <p className="zone-meta">
              x:{zone.x} y:{zone.y} w:{zone.width} h:{zone.height}
            </p>

            <button
              type="button"
              className="danger-link"
              onClick={(event) => {
                event.stopPropagation()
                removeZone(zone.id)
              }}
            >
              Remove
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}
