import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Play,
  Pause,
  Save,
  RotateCcw,
  RotateCw,
  Film,
  ZoomIn,
  ZoomOut,
  X,
  Type,
  Smile,
  Sparkles,
  Volume2,
  Mic,
  Sliders,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react'
import type { TimelineEDL, ProjectDetail } from '../../types'
import { fetchTimeline, saveTimeline, renderTimeline, getFileUrl } from '../../api/client'
import { TimelineInspector, type SelectedTimelineItem } from './TimelineInspector'

interface TimelineEditorProps {
  project: ProjectDetail
  candidateId: number
  onClose: () => void
  onRenderSuccess?: () => void
}

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.floor((seconds % 1) * 10)
  return `${m}:${s < 10 ? '0' : ''}${s}.${ms}`
}

export const TimelineEditor: React.FC<TimelineEditorProps> = ({
  project,
  candidateId,
  onClose,
  onRenderSuccess,
}) => {
  const [timeline, setTimeline] = useState<TimelineEDL | null>(null)
  const [history, setHistory] = useState<TimelineEDL[]>([])
  const [historyIdx, setHistoryIdx] = useState(-1)
  const [loading, setLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'unsaved' | 'saving' | 'failed'>('saved')
  const [isRendering, setIsRendering] = useState(false)
  const [renderMessage, setRenderMessage] = useState<string | null>(null)

  // Playhead & UI states
  const [currentTime, setCurrentTime] = useState(0.0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [zoom, setZoom] = useState(1.0) // 1.0 = normal, 2.0 = 2x width
  const [selection, setSelection] = useState<SelectedTimelineItem>(null)

  const videoRef = useRef<HTMLVideoElement>(null)
  const timelineRulerRef = useRef<HTMLDivElement>(null)

  // Load initial TimelineEDL from backend
  useEffect(() => {
    let isMounted = true
    setLoading(true)
    fetchTimeline(project.id, candidateId)
      .then((data: TimelineEDL) => {
        if (!isMounted) return
        setTimeline(data)
        setHistory([data])
        setHistoryIdx(0)
        setLoading(false)
      })
      .catch((err) => {
        if (!isMounted) return
        console.error('Failed to load timeline:', err)
        setLoading(false)
      })
    return () => {
      isMounted = false
    }
  }, [project.id, candidateId])

  // Synchronize playback clock with HTML5 video
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime)
    }
  }

  const togglePlay = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
      setIsPlaying(false)
    } else {
      videoRef.current.play()
      setIsPlaying(true)
    }
  }

  const seekTo = (seconds: number) => {
    const clamped = Math.max(0, Math.min(timeline?.duration || 60, seconds))
    setCurrentTime(clamped)
    if (videoRef.current) {
      videoRef.current.currentTime = clamped
    }
  }

  // Record modification to timeline with undo/redo stack
  const commitTimelineChange = useCallback((newTimeline: TimelineEDL, dirtyTrackName?: string) => {
    if (dirtyTrackName && !newTimeline.metadata.dirty_tracks.includes(dirtyTrackName)) {
      newTimeline.metadata.dirty_tracks.push(dirtyTrackName)
    }
    setTimeline(newTimeline)
    setSaveStatus('unsaved')

    setHistory((prev) => {
      const upToCurrent = prev.slice(0, historyIdx + 1)
      return [...upToCurrent, newTimeline]
    })
    setHistoryIdx((prev) => prev + 1)
  }, [historyIdx])

  // Undo / Redo
  const handleUndo = useCallback(() => {
    if (historyIdx > 0) {
      const newIdx = historyIdx - 1
      setHistoryIdx(newIdx)
      setTimeline(history[newIdx])
      setSaveStatus('unsaved')
    }
  }, [historyIdx, history])

  const handleRedo = useCallback(() => {
    if (historyIdx < history.length - 1) {
      const newIdx = historyIdx + 1
      setHistoryIdx(newIdx)
      setTimeline(history[newIdx])
      setSaveStatus('unsaved')
    }
  }, [historyIdx, history])

  // Keyboard shortcuts (Ctrl+Z, Ctrl+Y, Space)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }
      if (e.ctrlKey && e.key === 'z') {
        e.preventDefault()
        handleUndo()
      } else if (e.ctrlKey && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) {
        e.preventDefault()
        handleRedo()
      } else if (e.code === 'Space') {
        e.preventDefault()
        togglePlay()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleUndo, handleRedo, isPlaying])

  // Save Timeline to backend
  const handleSave = async () => {
    if (!timeline) return
    setSaveStatus('saving')
    try {
      const res = await saveTimeline(project.id, candidateId, timeline)
      if (res.timeline) {
        setTimeline(res.timeline)
      }
      setSaveStatus('saved')
    } catch {
      setSaveStatus('failed')
    }
  }

  // Trigger Re-render
  const handleRender = async () => {
    if (!timeline) return
    setIsRendering(true)
    setRenderMessage('Rendering Short from updated timeline...')
    try {
      // Auto-save first
      await handleSave()
      const res = await renderTimeline(project.id, candidateId)
      setRenderMessage(`Render completed in ${res?.result?.render_time_sec || 0}s! Final Short refreshed.`)
      setTimeout(() => {
        setIsRendering(false)
        setRenderMessage(null)
        if (onRenderSuccess) onRenderSuccess()
      }, 2500)
    } catch (err: any) {
      setIsRendering(false)
      setRenderMessage(`Render failed: ${err.message || 'Unknown error'}`)
    }
  }

  // Update item from inspector
  const handleInspectorUpdate = (updatedSelection: SelectedTimelineItem) => {
    if (!timeline || !updatedSelection) return
    setSelection(updatedSelection)

    const tlCopy = { ...timeline }
    if (updatedSelection.type === 'subtitle') {
      tlCopy.subtitles_track = tlCopy.subtitles_track.map((s) =>
        s.id === updatedSelection.item.id ? updatedSelection.item : s
      )
      commitTimelineChange(tlCopy, 'subtitles')
    } else if (updatedSelection.type === 'emoji') {
      tlCopy.emoji_track = tlCopy.emoji_track.map((e) =>
        e.id === updatedSelection.item.id ? updatedSelection.item : e
      )
      commitTimelineChange(tlCopy, 'emojis')
    } else if (updatedSelection.type === 'effect') {
      tlCopy.effects_track = tlCopy.effects_track.map((eff) =>
        eff.id === updatedSelection.item.id ? updatedSelection.item : eff
      )
      commitTimelineChange(tlCopy, 'effects')
    } else if (updatedSelection.type === 'sfx') {
      tlCopy.sfx_track = tlCopy.sfx_track.map((sfx) =>
        sfx.id === updatedSelection.item.id ? updatedSelection.item : sfx
      )
      commitTimelineChange(tlCopy, 'sfx')
    } else if (updatedSelection.type === 'ducking') {
      tlCopy.ducking_track = tlCopy.ducking_track.map((d) =>
        d.id === updatedSelection.item.id ? updatedSelection.item : d
      )
      commitTimelineChange(tlCopy, 'ducking')
    } else if (updatedSelection.type === 'boundaries') {
      tlCopy.boundaries = updatedSelection.item
      tlCopy.duration = updatedSelection.item.duration
      commitTimelineChange(tlCopy, 'boundaries')
    }
  }

  const handleInspectorDelete = (toDelete: SelectedTimelineItem) => {
    if (!timeline || !toDelete) return
    const tlCopy = { ...timeline }
    if (toDelete.type === 'subtitle') {
      tlCopy.subtitles_track = tlCopy.subtitles_track.filter((s) => s.id !== toDelete.item.id)
      commitTimelineChange(tlCopy, 'subtitles')
    } else if (toDelete.type === 'emoji') {
      tlCopy.emoji_track = tlCopy.emoji_track.filter((e) => e.id !== toDelete.item.id)
      commitTimelineChange(tlCopy, 'emojis')
    } else if (toDelete.type === 'effect') {
      tlCopy.effects_track = tlCopy.effects_track.filter((eff) => eff.id !== toDelete.item.id)
      commitTimelineChange(tlCopy, 'effects')
    } else if (toDelete.type === 'sfx') {
      tlCopy.sfx_track = tlCopy.sfx_track.filter((sfx) => sfx.id !== toDelete.item.id)
      commitTimelineChange(tlCopy, 'sfx')
    } else if (toDelete.type === 'ducking') {
      tlCopy.ducking_track = tlCopy.ducking_track.filter((d) => d.id !== toDelete.item.id)
      commitTimelineChange(tlCopy, 'ducking')
    }
    setSelection(null)
  }

  if (loading || !timeline) {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(5, 8, 15, 0.95)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <RefreshCw size={24} className="spin" color="var(--accent-cyan)" />
          <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>Loading Multi-Track Timeline...</span>
        </div>
      </div>
    )
  }

  const duration = Math.max(1.0, timeline.duration)
  const pxPerSec = 40 * zoom
  const timelineWidth = Math.max(800, duration * pxPerSec)

  const videoUrl = getFileUrl(project.id, `publishing/candidate_${candidateId.toString().padStart(2, '0')}/final.mp4`)

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 1000,
      background: '#090d16',
      display: 'flex',
      flexDirection: 'column',
      color: 'var(--text-main)',
      overflow: 'hidden',
    }}>
      {/* 1. Editor Top Navigation & Action Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 20px',
        borderBottom: '1px solid var(--border-color)',
        background: '#0f172a',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span className="badge badge-purple" style={{ fontSize: '0.85rem' }}>
            SHORT #{candidateId} TIMELINE EDL
          </span>
          <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>
            v{timeline.version}
          </span>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)' }}>
            Duration: <strong style={{ color: 'var(--text-main)' }}>{duration.toFixed(2)}s</strong>
          </span>

          {/* Dirty Track Badges */}
          {timeline.metadata.dirty_tracks.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-amber)', fontWeight: 600 }}>Edited:</span>
              {timeline.metadata.dirty_tracks.map((dt) => (
                <span key={dt} className="badge badge-amber" style={{ fontSize: '0.7rem', padding: '1px 6px' }}>
                  {dt}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Center: Save Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem' }}>
          {saveStatus === 'saved' && (
            <span style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <CheckCircle size={14} /> Saved
            </span>
          )}
          {saveStatus === 'unsaved' && (
            <span style={{ color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertTriangle size={14} /> Unsaved changes
            </span>
          )}
          {saveStatus === 'saving' && (
            <span style={{ color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <RefreshCw size={14} className="spin" /> Saving...
            </span>
          )}
          {saveStatus === 'failed' && (
            <span style={{ color: '#f87171' }}>Save failed</span>
          )}
        </div>

        {/* Right Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            className="btn btn-secondary"
            onClick={handleUndo}
            disabled={historyIdx <= 0}
            style={{ padding: '6px 10px', fontSize: '0.8rem' }}
            title="Undo (Ctrl+Z)"
          >
            <RotateCcw size={14} />
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleRedo}
            disabled={historyIdx >= history.length - 1}
            style={{ padding: '6px 10px', fontSize: '0.8rem' }}
            title="Redo (Ctrl+Y)"
          >
            <RotateCw size={14} />
          </button>

          <button
            className="btn btn-secondary"
            onClick={handleSave}
            disabled={saveStatus === 'saving'}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Save size={15} />
            <span>Save Timeline</span>
          </button>

          <button
            className="btn btn-primary"
            onClick={handleRender}
            disabled={isRendering}
            style={{ padding: '6px 18px', fontSize: '0.85rem', background: 'var(--gradient-primary)' }}
          >
            <Film size={15} />
            <span>{isRendering ? 'Rendering...' : 'Render Final Video'}</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={onClose}
            style={{ padding: '6px 10px' }}
            title="Close Timeline Editor"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Render Alert Notification */}
      {renderMessage && (
        <div style={{
          background: isRendering ? 'rgba(59, 130, 246, 0.2)' : 'rgba(16, 185, 129, 0.2)',
          borderBottom: '1px solid rgba(59, 130, 246, 0.4)',
          padding: '8px 20px',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          {isRendering ? <RefreshCw size={14} className="spin" color="var(--accent-cyan)" /> : <CheckCircle size={14} color="var(--accent-green)" />}
          <span>{renderMessage}</span>
        </div>
      )}

      {/* 2. Top Half Workspace: Video Preview Left, Inspector Right */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(280px, 420px) minmax(0, 1fr)',
        gap: 16,
        padding: '16px 20px',
        flex: '0 0 auto',
        maxHeight: '44vh',
        background: '#090d16',
      }}>
        {/* Left: 9:16 Video Player Card */}
        <div className="card" style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 10,
          background: '#000',
        }}>
          <div style={{
            position: 'relative',
            height: '100%',
            maxHeight: 280,
            aspectRatio: timeline?.video_track?.aspect_ratio === '1:1' ? '1 / 1' : '9 / 16',
            borderRadius: 6,
            overflow: 'hidden',
            background: '#000',
          }}>
            <video
              ref={videoRef}
              src={videoUrl}
              onTimeUpdate={handleTimeUpdate}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </div>

          {/* Transport Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
            <button
              className="btn btn-secondary"
              onClick={togglePlay}
              style={{ padding: '5px 12px', fontSize: '0.85rem' }}
            >
              {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <span style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
              {formatClock(currentTime)} / {formatClock(duration)}
            </span>
          </div>
        </div>

        {/* Right: Selected Item Property Inspector */}
        <div className="card" style={{ padding: 0, overflow: 'hidden', background: '#0e1524' }}>
          <TimelineInspector
            selection={selection}
            onUpdate={handleInspectorUpdate}
            onDelete={handleInspectorDelete}
            onSeek={seekTo}
          />
        </div>
      </div>

      {/* 3. Bottom Multi-Track Timeline */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        borderTop: '2px solid var(--border-color)',
        background: '#0b101c',
        overflow: 'hidden',
      }}>
        {/* Timeline Track Control Bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 16px',
          borderBottom: '1px solid var(--border-color)',
          background: '#0f172a',
          fontSize: '0.8rem',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>TRACKS (7)</span>
            <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>
              Click item to edit • Click ruler to seek • Space to play
            </span>
          </div>

          {/* Zoom Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>Zoom:</span>
            <button
              className="btn btn-secondary"
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
              style={{ padding: '2px 6px', fontSize: '0.75rem' }}
            >
              <ZoomOut size={12} />
            </button>
            <span style={{ fontSize: '0.75rem', minWidth: 32, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
            <button
              className="btn btn-secondary"
              onClick={() => setZoom((z) => Math.min(3.0, z + 0.25))}
              style={{ padding: '2px 6px', fontSize: '0.75rem' }}
            >
              <ZoomIn size={12} />
            </button>
          </div>
        </div>

        {/* Scrollable Timeline Grid */}
        <div
          ref={timelineRulerRef}
          style={{
            flex: 1,
            overflowX: 'auto',
            overflowY: 'auto',
            position: 'relative',
            background: '#070b13',
          }}
        >
          <div style={{ width: timelineWidth + 180, minHeight: '100%', position: 'relative' }}>
            {/* Playhead Red Needle */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: 140 + currentTime * pxPerSec,
                width: 2,
                background: '#ef4444',
                zIndex: 50,
                pointerEvents: 'none',
              }}
            >
              <div style={{
                position: 'absolute',
                top: 0,
                left: -5,
                width: 12,
                height: 12,
                background: '#ef4444',
                clipPath: 'polygon(0 0, 100% 0, 50% 100%)',
              }} />
            </div>

            {/* Time Ruler */}
            <div
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect()
                const clickX = e.clientX - rect.left - 140
                if (clickX >= 0) {
                  seekTo(clickX / pxPerSec)
                }
              }}
              style={{
                height: 32,
                borderBottom: '1px solid var(--border-color)',
                background: '#0d1322',
                display: 'flex',
                alignItems: 'center',
                position: 'relative',
                cursor: 'pointer',
              }}
            >
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-dim)' }}>
                TIMECODE
              </div>
              <div style={{ position: 'relative', flex: 1, height: '100%' }}>
                {Array.from({ length: Math.ceil(duration) + 1 }).map((_, sec) => (
                  <div
                    key={sec}
                    style={{
                      position: 'absolute',
                      left: sec * pxPerSec,
                      top: 0,
                      bottom: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      borderLeft: sec % 5 === 0 ? '1px solid #475569' : '1px solid #1e293b',
                      paddingLeft: 4,
                      fontSize: '0.65rem',
                      color: sec % 5 === 0 ? '#94a3b8' : '#475569',
                      pointerEvents: 'none',
                    }}
                  >
                    {sec % 5 === 0 ? formatClock(sec) : ''}
                  </div>
                ))}
              </div>
            </div>

            {/* Track 1: BOUNDARIES */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 38, alignItems: 'center' }}>
              <div
                onClick={() => setSelection({ type: 'boundaries', item: timeline.boundaries })}
                style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
              >
                <Sliders size={13} color="var(--text-main)" />
                <span>Boundaries</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 26, background: '#111827', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{
                  position: 'absolute',
                  left: 0,
                  width: duration * pxPerSec,
                  height: '100%',
                  background: 'rgba(59, 130, 246, 0.25)',
                  border: '1px solid rgba(59, 130, 246, 0.6)',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: 8,
                  fontSize: '0.7rem',
                  color: '#93c5fd',
                }}>
                  Source: {timeline.boundaries.source_in.toFixed(1)}s → {timeline.boundaries.source_out.toFixed(1)}s ({duration.toFixed(1)}s)
                </div>
              </div>
            </div>

            {/* Track 2: VIDEO */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 38, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Film size={13} color="var(--accent-cyan)" />
                <span>{timeline.video_track.aspect_ratio === '1:1' ? 'Video 1:1' : 'Video 9:16'}</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 26, background: '#111827', borderRadius: 4 }}>
                <div style={{
                  position: 'absolute',
                  left: 0,
                  width: duration * pxPerSec,
                  height: '100%',
                  background: 'rgba(0, 242, 254, 0.15)',
                  border: '1px solid rgba(0, 242, 254, 0.4)',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: 8,
                  paddingRight: 8,
                  fontSize: '0.7rem',
                  color: 'var(--accent-cyan)',
                  justifyContent: 'space-between',
                }}>
                  <span>{timeline.video_track.layout} • {timeline.video_track.resolution} • {timeline.video_track.fps}fps</span>
                  {timeline.video_track.aspect_ratio !== '1:1' && (
                    <button
                      type="button"
                      style={{
                        background: timeline.video_track.kill_feed_overlay ? 'rgba(0, 242, 254, 0.25)' : 'rgba(255, 255, 255, 0.08)',
                        border: timeline.video_track.kill_feed_overlay ? '1px solid var(--accent-cyan)' : '1px solid rgba(255, 255, 255, 0.2)',
                        color: timeline.video_track.kill_feed_overlay ? 'var(--accent-cyan)' : 'var(--text-dim)',
                        borderRadius: 3,
                        padding: '1px 6px',
                        fontSize: '0.65rem',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                      onClick={() => {
                        const updated = {
                          ...timeline,
                          video_track: {
                            ...timeline.video_track,
                            kill_feed_overlay: !timeline.video_track.kill_feed_overlay,
                          },
                        }
                        commitTimelineChange(updated, 'video')
                      }}
                      title="Toggle Kill-Feed PIP Overlay for 9:16 Shorts"
                    >
                      PIP {timeline.video_track.kill_feed_overlay ? 'ON' : 'OFF'}
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Track 3: SUBTITLES */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 46, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Type size={13} color="var(--accent-cyan)" />
                <span>Subtitles ({timeline.subtitles_track.length})</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 34 }}>
                {timeline.subtitles_track.map((sub) => {
                  const left = sub.start * pxPerSec
                  const width = Math.max(20, (sub.end - sub.start) * pxPerSec)
                  const isSelected = selection?.type === 'subtitle' && selection.item.id === sub.id

                  return (
                    <div
                      key={sub.id}
                      onClick={() => {
                        setSelection({ type: 'subtitle', item: sub })
                        seekTo(sub.start)
                      }}
                      style={{
                        position: 'absolute',
                        left,
                        width,
                        top: 4,
                        bottom: 4,
                        background: isSelected ? 'var(--accent-cyan)' : (sub.enabled ? '#1e293b' : '#334155'),
                        color: isSelected ? '#000' : (sub.enabled ? '#e2e8f0' : '#94a3b8'),
                        border: `1px solid ${isSelected ? '#fff' : (sub.edited ? 'var(--accent-green)' : '#475569')}`,
                        borderRadius: 4,
                        display: 'flex',
                        alignItems: 'center',
                        padding: '0 6px',
                        fontSize: '0.72rem',
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        textOverflow: 'ellipsis',
                        cursor: 'pointer',
                        opacity: sub.enabled ? 1.0 : 0.45,
                        transition: 'all 0.15s ease',
                      }}
                      title={`${sub.text} (${sub.start.toFixed(2)}s - ${sub.end.toFixed(2)}s)`}
                    >
                      {sub.text}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Track 4: EMOJIS */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 40, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Smile size={13} color="var(--accent-amber)" />
                <span>Emojis ({timeline.emoji_track.length})</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 30 }}>
                {timeline.emoji_track.map((emo) => {
                  const left = emo.timestamp * pxPerSec
                  const width = Math.max(24, emo.duration * pxPerSec)
                  const isSelected = selection?.type === 'emoji' && selection.item.id === emo.id

                  return (
                    <div
                      key={emo.id}
                      onClick={() => {
                        setSelection({ type: 'emoji', item: emo })
                        seekTo(emo.timestamp)
                      }}
                      style={{
                        position: 'absolute',
                        left,
                        width,
                        top: 2,
                        bottom: 2,
                        background: isSelected ? 'rgba(245, 158, 11, 0.4)' : 'rgba(245, 158, 11, 0.15)',
                        border: `1px solid ${isSelected ? 'var(--accent-amber)' : 'rgba(245, 158, 11, 0.4)'}`,
                        borderRadius: 4,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.95rem',
                        cursor: 'pointer',
                        opacity: emo.enabled ? 1.0 : 0.4,
                      }}
                      title={`Emoji: ${emo.emoji} @ ${emo.timestamp.toFixed(2)}s`}
                    >
                      {emo.emoji}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Track 5: VISUAL EFFECTS */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 42, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Sparkles size={13} color="var(--accent-purple)" />
                <span>Effects ({timeline.effects_track.length})</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 30 }}>
                {timeline.effects_track.map((eff) => {
                  const left = eff.start * pxPerSec
                  const width = Math.max(24, (eff.end - eff.start) * pxPerSec)
                  const isSelected = selection?.type === 'effect' && selection.item.id === eff.id

                  return (
                    <div
                      key={eff.id}
                      onClick={() => {
                        setSelection({ type: 'effect', item: eff })
                        seekTo(eff.start)
                      }}
                      style={{
                        position: 'absolute',
                        left,
                        width,
                        top: 2,
                        bottom: 2,
                        background: isSelected ? 'var(--accent-purple)' : 'rgba(168, 85, 247, 0.25)',
                        border: `1px solid ${isSelected ? '#fff' : 'var(--accent-purple)'}`,
                        borderRadius: 4,
                        display: 'flex',
                        alignItems: 'center',
                        padding: '0 4px',
                        fontSize: '0.7rem',
                        color: '#f3e8ff',
                        cursor: 'pointer',
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        opacity: eff.enabled ? 1.0 : 0.4,
                      }}
                      title={`${eff.type} (${eff.start.toFixed(2)}s - ${eff.end.toFixed(2)}s)`}
                    >
                      ▲ {eff.type.replace('_', ' ')}
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Track 6: SFX */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', minHeight: 42, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Volume2 size={13} color="var(--accent-green)" />
                <span>SFX ({timeline.sfx_track.length})</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 30 }}>
                {timeline.sfx_track.map((sfx) => {
                  const left = sfx.timestamp * pxPerSec
                  const isSelected = selection?.type === 'sfx' && selection.item.id === sfx.id

                  return (
                    <div
                      key={sfx.id}
                      onClick={() => {
                        setSelection({ type: 'sfx', item: sfx })
                        seekTo(sfx.timestamp)
                      }}
                      style={{
                        position: 'absolute',
                        left,
                        width: 80,
                        top: 2,
                        bottom: 2,
                        background: isSelected ? 'var(--accent-green)' : 'rgba(16, 185, 129, 0.25)',
                        color: isSelected ? '#000' : '#a7f3d0',
                        border: `1px solid ${isSelected ? '#fff' : 'var(--accent-green)'}`,
                        borderRadius: 4,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                        padding: '0 6px',
                        fontSize: '0.7rem',
                        cursor: 'pointer',
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        opacity: sfx.enabled ? 1.0 : 0.4,
                      }}
                      title={`${sfx.event_type} (${sfx.asset_name}) @ ${sfx.timestamp.toFixed(2)}s`}
                    >
                      <Volume2 size={11} />
                      <span>{sfx.event_type}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Track 7: DUCKING */}
            <div style={{ display: 'flex', minHeight: 40, alignItems: 'center' }}>
              <div style={{ width: 140, paddingLeft: 12, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Mic size={13} color="#38bdf8" />
                <span>Ducking ({timeline.ducking_track.length})</span>
              </div>
              <div style={{ position: 'relative', flex: 1, height: 26 }}>
                {timeline.ducking_track.map((duck) => {
                  const left = duck.start * pxPerSec
                  const width = Math.max(16, (duck.end - duck.start) * pxPerSec)
                  const isSelected = selection?.type === 'ducking' && selection.item.id === duck.id

                  return (
                    <div
                      key={duck.id}
                      onClick={() => {
                        setSelection({ type: 'ducking', item: duck })
                        seekTo(duck.start)
                      }}
                      style={{
                        position: 'absolute',
                        left,
                        width,
                        top: 2,
                        bottom: 2,
                        background: isSelected ? '#38bdf8' : 'rgba(56, 189, 248, 0.25)',
                        border: `1px solid ${isSelected ? '#fff' : '#38bdf8'}`,
                        borderRadius: 3,
                        cursor: 'pointer',
                        opacity: duck.enabled ? 1.0 : 0.4,
                      }}
                      title={`Speech Ducking: ${duck.attenuation_db.toFixed(1)}dB (${duck.start.toFixed(2)}s - ${duck.end.toFixed(2)}s)`}
                    />
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
