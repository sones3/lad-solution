import { useEffect, useRef, useState, type MouseEvent } from 'react'
import type { IgnoreRegion } from '../types/template'

type DragAction =
  | { mode: 'draw'; regionId: string; startX: number; startY: number }
  | { mode: 'move'; regionId: string; offsetX: number; offsetY: number; width: number; height: number }
  | { mode: 'resize'; regionId: string }

interface IgnoreRegionCanvasProps {
  imageUrl: string | null
  regions: IgnoreRegion[]
  selectedRegionId: string | null
  onSelectRegion: (id: string | null) => void
  onChangeRegions: (regions: IgnoreRegion[]) => void
}

const MIN_SIZE = 12

export function IgnoreRegionCanvas({
  imageUrl,
  regions,
  selectedRegionId,
  onSelectRegion,
  onChangeRegions,
}: IgnoreRegionCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 })
  const [displaySize, setDisplaySize] = useState({ width: 0, height: 0 })
  const actionRef = useRef<DragAction | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) {
        return
      }
      setDisplaySize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const pointerToImageSpace = (clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || naturalSize.width === 0 || naturalSize.height === 0) {
      return { x: 0, y: 0 }
    }

    const clampedX = Math.max(0, Math.min(clientX - rect.left, rect.width))
    const clampedY = Math.max(0, Math.min(clientY - rect.top, rect.height))
    const ratioX = naturalSize.width / rect.width
    const ratioY = naturalSize.height / rect.height

    return {
      x: Math.round(clampedX * ratioX),
      y: Math.round(clampedY * ratioY),
    }
  }

  const updateRegion = (id: string, updater: (region: IgnoreRegion) => IgnoreRegion) => {
    onChangeRegions(
      regions.map((region) => {
        if (region.id !== id) {
          return region
        }
        const updated = updater(region)
        return {
          ...updated,
          width: Math.max(MIN_SIZE, updated.width),
          height: Math.max(MIN_SIZE, updated.height),
          x: Math.max(0, Math.min(updated.x, naturalSize.width - MIN_SIZE)),
          y: Math.max(0, Math.min(updated.y, naturalSize.height - MIN_SIZE)),
        }
      }),
    )
  }

  const handlePointerDown = (event: MouseEvent<HTMLDivElement>) => {
    if (!imageUrl || naturalSize.width === 0 || naturalSize.height === 0 || event.button !== 0) {
      return
    }

    const point = pointerToImageSpace(event.clientX, event.clientY)
    const newRegion: IgnoreRegion = {
      id: crypto.randomUUID(),
      name: `ignore_${regions.length + 1}`,
      x: point.x,
      y: point.y,
      width: MIN_SIZE,
      height: MIN_SIZE,
    }

    onChangeRegions([...regions, newRegion])
    onSelectRegion(newRegion.id)
    actionRef.current = { mode: 'draw', regionId: newRegion.id, startX: point.x, startY: point.y }
  }

  const handlePointerMove = (event: MouseEvent<HTMLDivElement>) => {
    const action = actionRef.current
    if (!action) {
      return
    }

    const point = pointerToImageSpace(event.clientX, event.clientY)

    if (action.mode === 'draw') {
      updateRegion(action.regionId, (region) => ({
        ...region,
        x: Math.min(action.startX, point.x),
        y: Math.min(action.startY, point.y),
        width: Math.abs(point.x - action.startX),
        height: Math.abs(point.y - action.startY),
      }))
      return
    }

    if (action.mode === 'move') {
      const nextX = point.x - action.offsetX
      const nextY = point.y - action.offsetY
      updateRegion(action.regionId, (region) => ({
        ...region,
        x: Math.max(0, Math.min(nextX, naturalSize.width - action.width)),
        y: Math.max(0, Math.min(nextY, naturalSize.height - action.height)),
      }))
      return
    }

    updateRegion(action.regionId, (region) => ({
      ...region,
      width: Math.max(MIN_SIZE, point.x - region.x),
      height: Math.max(MIN_SIZE, point.y - region.y),
    }))
  }

  const stopAction = () => {
    actionRef.current = null
  }

  return (
    <section className="canvas-panel">
      <h2>Paper ignore regions</h2>
      <p>Draw varying-field masks on the image. These areas are excluded from paper-method keypoint selection.</p>

      <div
        className="canvas"
        ref={containerRef}
        onMouseDown={handlePointerDown}
        onMouseMove={handlePointerMove}
        onMouseUp={stopAction}
        onMouseLeave={stopAction}
      >
        {imageUrl ? (
          <>
            <img
              src={imageUrl}
              alt="Template"
              onLoad={(event) => {
                setNaturalSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
                setDisplaySize({
                  width: event.currentTarget.clientWidth,
                  height: event.currentTarget.clientHeight,
                })
              }}
            />

            <div className="overlay">
              {regions.map((region) => {
                const displayX = naturalSize.width > 0 ? (region.x / naturalSize.width) * displaySize.width : 0
                const displayY =
                  naturalSize.height > 0 ? (region.y / naturalSize.height) * displaySize.height : 0
                const displayWidth =
                  naturalSize.width > 0 ? (region.width / naturalSize.width) * displaySize.width : 0
                const displayHeight =
                  naturalSize.height > 0 ? (region.height / naturalSize.height) * displaySize.height : 0

                return (
                  <div
                    key={region.id}
                    className={selectedRegionId === region.id ? 'zone active' : 'zone'}
                    style={{
                      left: `${displayX}px`,
                      top: `${displayY}px`,
                      width: `${displayWidth}px`,
                      height: `${displayHeight}px`,
                      borderColor: '#d44f3a',
                      background: 'rgba(212, 79, 58, 0.16)',
                    }}
                    onMouseDown={(event) => {
                      event.stopPropagation()
                      const point = pointerToImageSpace(event.clientX, event.clientY)
                      actionRef.current = {
                        mode: 'move',
                        regionId: region.id,
                        offsetX: point.x - region.x,
                        offsetY: point.y - region.y,
                        width: region.width,
                        height: region.height,
                      }
                      onSelectRegion(region.id)
                    }}
                  >
                    <span>{region.name || 'unnamed'}</span>
                    <button
                      type="button"
                      className="resize-handle"
                      aria-label={`Resize ${region.name || 'ignore region'}`}
                      onMouseDown={(event) => {
                        event.stopPropagation()
                        actionRef.current = {
                          mode: 'resize',
                          regionId: region.id,
                        }
                        onSelectRegion(region.id)
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </>
        ) : (
          <div className="canvas-empty">Upload a template image to start defining ignore regions.</div>
        )}
      </div>
    </section>
  )
}
