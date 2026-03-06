import { useEffect, useRef, useState, type MouseEvent } from 'react'
import type { Zone } from '../types/template'

type DragAction =
  | { mode: 'draw'; zoneId: string; startX: number; startY: number }
  | { mode: 'move'; zoneId: string; offsetX: number; offsetY: number; width: number; height: number }
  | { mode: 'resize'; zoneId: string }

interface ImageCanvasProps {
  imageUrl: string | null
  zones: Zone[]
  selectedZoneId: string | null
  onSelectZone: (id: string | null) => void
  onChangeZones: (zones: Zone[]) => void
}

const MIN_SIZE = 12

export function ImageCanvas({
  imageUrl,
  zones,
  selectedZoneId,
  onSelectZone,
  onChangeZones,
}: ImageCanvasProps) {
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

  const updateZone = (id: string, updater: (zone: Zone) => Zone) => {
    onChangeZones(
      zones.map((zone) => {
        if (zone.id !== id) {
          return zone
        }
        const updated = updater(zone)
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
    const newZone: Zone = {
      id: crypto.randomUUID(),
      name: `field_${zones.length + 1}`,
      type: 'text',
      required: false,
      x: point.x,
      y: point.y,
      width: MIN_SIZE,
      height: MIN_SIZE,
    }

    onChangeZones([...zones, newZone])
    onSelectZone(newZone.id)
    actionRef.current = { mode: 'draw', zoneId: newZone.id, startX: point.x, startY: point.y }
  }

  const handlePointerMove = (event: MouseEvent<HTMLDivElement>) => {
    const action = actionRef.current
    if (!action) {
      return
    }

    const point = pointerToImageSpace(event.clientX, event.clientY)

    if (action.mode === 'draw') {
      updateZone(action.zoneId, (zone) => ({
        ...zone,
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
      updateZone(action.zoneId, (zone) => ({
        ...zone,
        x: Math.max(0, Math.min(nextX, naturalSize.width - action.width)),
        y: Math.max(0, Math.min(nextY, naturalSize.height - action.height)),
      }))
      return
    }

    updateZone(action.zoneId, (zone) => ({
      ...zone,
      width: Math.max(MIN_SIZE, point.x - zone.x),
      height: Math.max(MIN_SIZE, point.y - zone.y),
    }))
  }

  const stopAction = () => {
    actionRef.current = null
  }

  return (
    <section className="canvas-panel">
      <h2>Template canvas</h2>
      <p>Draw zones by dragging on the image. Drag existing boxes to move and use corner handle to resize.</p>

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
              {zones.map((zone) => {
                const displayX = naturalSize.width > 0 ? (zone.x / naturalSize.width) * displaySize.width : 0
                const displayY =
                  naturalSize.height > 0 ? (zone.y / naturalSize.height) * displaySize.height : 0
                const displayWidth =
                  naturalSize.width > 0 ? (zone.width / naturalSize.width) * displaySize.width : 0
                const displayHeight =
                  naturalSize.height > 0 ? (zone.height / naturalSize.height) * displaySize.height : 0

                return (
                  <div
                    key={zone.id}
                    className={selectedZoneId === zone.id ? 'zone active' : 'zone'}
                    style={{
                      left: `${displayX}px`,
                      top: `${displayY}px`,
                      width: `${displayWidth}px`,
                      height: `${displayHeight}px`,
                    }}
                    onMouseDown={(event) => {
                      event.stopPropagation()
                      const point = pointerToImageSpace(event.clientX, event.clientY)
                      actionRef.current = {
                        mode: 'move',
                        zoneId: zone.id,
                        offsetX: point.x - zone.x,
                        offsetY: point.y - zone.y,
                        width: zone.width,
                        height: zone.height,
                      }
                      onSelectZone(zone.id)
                    }}
                  >
                    <span>{zone.name || 'unnamed'}</span>
                    <button
                      type="button"
                      className="resize-handle"
                      aria-label={`Resize ${zone.name || 'zone'}`}
                      onMouseDown={(event) => {
                        event.stopPropagation()
                        actionRef.current = {
                          mode: 'resize',
                          zoneId: zone.id,
                        }
                        onSelectZone(zone.id)
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </>
        ) : (
          <div className="canvas-empty">Upload a template image to start defining zones.</div>
        )}
      </div>
    </section>
  )
}
