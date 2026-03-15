import type { IgnoreRegion } from '../types/template'

interface IgnoreRegionListProps {
  regions: IgnoreRegion[]
  selectedRegionId: string | null
  onSelect: (id: string) => void
  onChange: (regions: IgnoreRegion[]) => void
}

export function IgnoreRegionList({
  regions,
  selectedRegionId,
  onSelect,
  onChange,
}: IgnoreRegionListProps) {
  const setRegion = (id: string, updater: (region: IgnoreRegion) => IgnoreRegion) => {
    onChange(
      regions.map((region) => {
        if (region.id !== id) {
          return region
        }
        return updater(region)
      }),
    )
  }

  const removeRegion = (id: string) => {
    onChange(regions.filter((region) => region.id !== id))
  }

  return (
    <section className="zones-panel">
      <h2>Paper ignore regions</h2>
      {regions.length === 0 ? <p>No ignore regions yet. Draw on the canvas to create one.</p> : null}

      <div className="zones-list">
        {regions.map((region) => (
          <article
            key={region.id}
            className={selectedRegionId === region.id ? 'zone-item active' : 'zone-item'}
            onClick={() => onSelect(region.id)}
          >
            <label>
              Name
              <input
                value={region.name}
                onChange={(event) => {
                  setRegion(region.id, (current) => ({ ...current, name: event.target.value }))
                }}
                placeholder="e.g. holder_name"
              />
            </label>

            <p className="zone-meta">
              x:{region.x} y:{region.y} w:{region.width} h:{region.height}
            </p>

            <button
              type="button"
              className="danger-link"
              onClick={(event) => {
                event.stopPropagation()
                removeRegion(region.id)
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
