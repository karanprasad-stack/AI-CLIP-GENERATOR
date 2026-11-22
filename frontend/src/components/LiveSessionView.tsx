import React, { useState, useEffect } from 'react'
import {
  Radio,
  Play,
  Pause,
  Square,
  RotateCw,
  Clock,
  Layers,
  Sparkles,
  CheckCircle2,
  HardDrive,
  Sliders,
  Scissors,
} from 'lucide-react'
import type { ProjectDetail, LiveActivityEvent, Candidate } from '../types'
import {
  startLiveSession,
  stopLiveSession,
  pauseLiveSession,
  resumeLiveSession,
  fetchLiveStatus,
  fetchLiveCandidates,
} from '../api/client'

interface LiveSessionViewProps {
  project: ProjectDetail
  onOpenTimelineEditor: (candidateId: number) => void
  onRefreshProject: () => void
}

function formatElapsed(seconds: number): string {
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const remS = s % 60
  if (h > 0) {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${remS.toString().padStart(2, '0')}`
  }
  return `${m.toString().padStart(2, '0')}:${remS.toString().padStart(2, '0')}`
}

export const LiveSessionView: React.FC<LiveSessionViewProps> = ({
  project,
  onOpenTimelineEditor,
  onRefreshProject,
}) => {
  const [sessionData, setSessionData] = useState<any>(null)
  const [activityEvents, setActivityEvents] = useState<LiveActivityEvent[]>([])
  const [liveCandidates, setLiveCandidates] = useState<Candidate[]>(project.candidates || [])
  const [elapsedSec, setElapsedSec] = useState(0)
  const [actionLoading, setActionLoading] = useState(false)

  const liveStatus = sessionData?.status || project.live_session_info?.status || project.status
  const isStreaming = liveStatus === 'live' || liveStatus === 'connecting' || liveStatus === 'reconnecting'
  const isPaused = liveStatus === 'paused'

  // Polling telemetry & activity
  const refreshTelemetry = async () => {
    try {
      const statusRes = await fetchLiveStatus(project.id)
      setSessionData(statusRes.session)
      if (statusRes.activity_recent) {
        setActivityEvents(statusRes.activity_recent)
      }

      const cands = await fetchLiveCandidates(project.id)
      if (cands && cands.length > 0) {
        setLiveCandidates(cands)
      }
    } catch {
      // transient poll error
    }
  }

  useEffect(() => {
    refreshTelemetry()
    const interval = setInterval(refreshTelemetry, 3000)
    return () => clearInterval(interval)
  }, [project.id])

  // Elapsed timer while active
  useEffect(() => {
    if (!isStreaming) return
    const timer = setInterval(() => {
      setElapsedSec((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [isStreaming])

  const handleStartResume = async () => {
    setActionLoading(true)
    try {
      if (isPaused) {
        await resumeLiveSession(project.id)
      } else {
        await startLiveSession(project.id)
      }
      await refreshTelemetry()
      onRefreshProject()
    } catch (err: any) {
      alert(err.message || 'Failed to start live stream')
    } finally {
      setActionLoading(false)
    }
  }

  const handlePause = async () => {
    setActionLoading(true)
    try {
      await pauseLiveSession(project.id)
      await refreshTelemetry()
      onRefreshProject()
    } catch (err: any) {
      alert(err.message || 'Failed to pause live stream')
    } finally {
      setActionLoading(false)
    }
  }

  const handleStop = async () => {
    if (!window.confirm('Are you sure you want to stop this live capture session?')) return
    setActionLoading(true)
    try {
      await stopLiveSession(project.id)
      await refreshTelemetry()
      onRefreshProject()
    } catch (err: any) {
      alert(err.message || 'Failed to stop live stream')
    } finally {
      setActionLoading(false)
    }
  }

  const getStatusBadge = () => {
    switch (liveStatus) {
      case 'live':
        return (
          <span className="badge badge-red" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
            <span className="live-dot-pulse" style={{ background: '#ef4444' }} />
            LIVE
          </span>
        )
      case 'connecting':
        return <span className="badge badge-yellow">CONNECTING</span>
      case 'reconnecting':
        return <span className="badge badge-yellow">RECONNECTING</span>
      case 'paused':
        return <span className="badge badge-cyan">PAUSED</span>
      case 'ended':
        return <span className="badge badge-green">ENDED</span>
      default:
        return <span className="badge badge-cyan">{liveStatus.toUpperCase()}</span>
    }
  }

  const segmentsProcessed = sessionData?.segments_processed ?? project.live_session_info?.segments_processed ?? 0
  const candidatesDetected = liveCandidates.length
  const publishReadyCount = liveCandidates.filter((c) => c.status === 'publish_ready' || c.publishability?.recommendation === 'publish').length
  const storageMb = ((sessionData?.storage_used || 0) / (1024 * 1024)).toFixed(1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1100, margin: '0 auto' }}>
      {/* Header Banner */}
      <div className="card" style={{ padding: '24px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              {getStatusBadge()}
              <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Clock size={14} />
                Elapsed: <strong className="font-mono tabular-nums">{formatElapsed(elapsedSec)}</strong>
              </span>
            </div>
            <h2 style={{ fontSize: '1.45rem', fontWeight: 800, margin: 0 }}>
              {project.title}
            </h2>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Channel: <span style={{ color: 'var(--text-main)' }}>{project.uploader}</span> • Rolling Window: 90s (30s overlap)
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {isStreaming ? (
              <>
                <button
                  className="btn btn-secondary"
                  onClick={handlePause}
                  disabled={actionLoading}
                  style={{ gap: 6 }}
                >
                  <Pause size={16} />
                  <span>Pause</span>
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleStop}
                  disabled={actionLoading}
                  style={{ gap: 6 }}
                >
                  <Square size={16} />
                  <span>Stop Capture</span>
                </button>
              </>
            ) : isPaused ? (
              <>
                <button
                  className="btn btn-primary"
                  onClick={handleStartResume}
                  disabled={actionLoading}
                  style={{ gap: 6 }}
                >
                  <Play size={16} />
                  <span>Resume Capture</span>
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleStop}
                  disabled={actionLoading}
                  style={{ gap: 6 }}
                >
                  <Square size={16} />
                  <span>Stop</span>
                </button>
              </>
            ) : (
              <button
                className="btn btn-primary"
                onClick={handleStartResume}
                disabled={actionLoading}
                style={{ gap: 6 }}
              >
                <Play size={16} />
                <span>Start Live Capture</span>
              </button>
            )}

            <button
              className="btn btn-secondary"
              onClick={refreshTelemetry}
              title="Refresh status"
              style={{ padding: '8px 10px' }}
            >
              <RotateCw size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Telemetry Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px' }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: 'rgba(0, 242, 254, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-cyan)',
          }}>
            <Layers size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Segments Processed
            </div>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.4rem', fontWeight: 800 }}>
              {segmentsProcessed}
            </div>
          </div>
        </div>

        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '18px 20px' }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: 'rgba(168, 85, 247, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-purple)',
          }}>
            <Sparkles size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Candidates Detected
            </div>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.4rem', fontWeight: 800 }}>
              {candidatesDetected}
            </div>
          </div>
        </div>

        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '18px 20px' }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: 'rgba(0, 255, 136, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-green)',
          }}>
            <CheckCircle2 size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Publish-Ready Shorts
            </div>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--accent-green)' }}>
              {publishReadyCount}
            </div>
          </div>
        </div>

        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '18px 20px' }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: 'rgba(255, 170, 0, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffaa00',
          }}>
            <HardDrive size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Live Storage Used
            </div>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.4rem', fontWeight: 800 }}>
              {storageMb} MB
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Activity Feed & Detected Candidates */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(300px,360px)_1fr] gap-5">
        {/* Live Activity Feed */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', maxHeight: 600 }}>
          <div style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Radio size={16} color="var(--accent-red)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Live Activity Feed</span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              {activityEvents.length} events
            </span>
          </div>

          <div style={{
            padding: '16px 20px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            flex: 1,
          }}>
            {activityEvents.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '30px 0', fontSize: '0.85rem' }}>
                Waiting for live stream events...
              </div>
            ) : (
              [...activityEvents].reverse().map((evt) => (
                <div key={evt.id} style={{
                  fontSize: '0.8rem',
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                  padding: '8px 10px',
                  borderRadius: 6,
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderLeft: evt.event_type.includes('merged')
                    ? '3px solid var(--accent-purple)'
                    : evt.event_type.includes('detected')
                    ? '3px solid var(--accent-green)'
                    : '3px solid var(--accent-cyan)',
                }}>
                  <span className="font-mono tabular-nums" style={{ color: 'var(--text-dim)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                    {evt.time_str}
                  </span>
                  <div style={{ color: 'var(--text-main)', lineHeight: 1.35 }}>
                    {evt.message}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Live Candidate Pool */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', maxHeight: 600 }}>
          <div style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Scissors size={16} color="var(--accent-cyan)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Detected Candidates Pool</span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              {liveCandidates.length} detected
            </span>
          </div>

          <div style={{
            padding: '16px 20px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            flex: 1,
          }}>
            {liveCandidates.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '50px 0', fontSize: '0.9rem' }}>
                No gaming candidates detected yet. Segments are being analyzed continuously...
              </div>
            ) : (
              liveCandidates.map((cand) => {
                const rec = cand.publishability?.recommendation || 'review'
                const isReady = cand.status === 'publish_ready' || rec === 'publish'
                const isReview = cand.status === 'review' || rec === 'review'

                return (
                  <div
                    key={cand.candidate_id}
                    style={{
                      padding: 16,
                      borderRadius: 10,
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: isReady ? '1px solid rgba(0, 255, 136, 0.3)' : '1px solid var(--border-color)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontWeight: 800, fontSize: '1rem', color: 'var(--text-main)' }}>
                          Short #{cand.candidate_id}
                        </span>
                        <span className={`badge ${isReady ? 'badge-green' : isReview ? 'badge-yellow' : 'badge-red'}`}>
                          {rec.toUpperCase()}
                        </span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                          Duration: <strong className="font-mono tabular-nums">{cand.duration.toFixed(1)}s</strong>
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="font-mono tabular-nums" style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                          Score: {cand.final_score.toFixed(1)}
                        </span>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', display: 'flex', gap: 14 }}>
                      <span>
                        Global Window: <strong className="font-mono tabular-nums">{cand.source_position_str || `${cand.start.toFixed(1)}s → ${cand.end.toFixed(1)}s`}</strong>
                      </span>
                      {cand.gameplay_event && (
                        <span>
                          Event: <strong style={{ color: 'var(--accent-purple)' }}>{cand.gameplay_event}</strong>
                        </span>
                      )}
                      {cand.strongest_reaction && (
                        <span>
                          Reaction: <strong style={{ color: '#ffaa00' }}>{cand.strongest_reaction}</strong>
                        </span>
                      )}
                    </div>

                    {/* Action button to open Phase 8 Timeline Editor */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                      <button
                        className="btn btn-secondary"
                        onClick={() => onOpenTimelineEditor(cand.candidate_id)}
                        style={{ fontSize: '0.8rem', padding: '6px 12px', gap: 6 }}
                      >
                        <Sliders size={13} />
                        <span>Edit Short #{cand.candidate_id} Timeline</span>
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
