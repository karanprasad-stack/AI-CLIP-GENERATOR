import React, { useEffect, useRef, useState } from 'react'
import { Activity, Terminal, AlertTriangle, XCircle, ArrowRight, RotateCw, Clock, Film, Sparkles, CheckCircle2, Search, DownloadCloud } from 'lucide-react'
import type { ProjectDetail } from '../types'
import { ConfirmDialog } from './ui/ConfirmDialog'

interface LiveProgressProps {
  project: ProjectDetail
  onCancel: () => void
  onProceed: () => void
  onRetry: () => void
}

function formatDuration(sec: number): string {
  const s = Math.round(sec)
  const m = Math.floor(s / 60)
  const remS = s % 60
  const h = Math.floor(m / 60)
  const remM = m % 60
  if (h > 0) return `${h}h ${remM}m`
  return `${m}m ${remS}s`
}

export const LiveProgress: React.FC<LiveProgressProps> = ({
  project,
  onCancel,
  onProceed,
  onRetry,
}) => {
  const logContainerRef = useRef<HTMLDivElement>(null)
  const { progress, long_stream_info, status, error } = project
  const [elapsedSec, setElapsedSec] = useState(0)
  const [showCancelDialog, setShowCancelDialog] = useState(false)

  // Auto-scroll log box
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [progress.logs])

  const isRunning = status === 'analyzing' || status === 'rendering'
  const isCompleted = status === 'completed' || status === 'candidates_ready'
  const isFailed = status === 'failed'

  // Elapsed timer while running
  useEffect(() => {
    if (!isRunning) return
    const timer = setInterval(() => {
      setElapsedSec((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [isRunning])

  const getStageIcon = () => {
    const stage = progress.stage.toLowerCase()
    if (stage.includes('download') || stage.includes('acqui')) return <DownloadCloud size={20} color="var(--accent-cyan)" />
    if (stage.includes('transcri') || stage.includes('whisper')) return <Sparkles size={20} color="var(--accent-purple)" />
    if (stage.includes('detect') || stage.includes('rank') || stage.includes('scorin')) return <Search size={20} color="var(--accent-green)" />
    if (stage.includes('render') || stage.includes('encod') || stage.includes('clipping')) return <Film size={20} color="var(--accent-cyan)" />
    if (isCompleted) return <CheckCircle2 size={20} color="var(--accent-green)" />
    return <Activity size={20} color="var(--accent-cyan)" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1000, margin: '0 auto' }}>
      {/* Title & Video Info */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span className={`badge ${isCompleted ? 'badge-green' : isFailed ? 'badge-red' : 'badge-cyan'}`}>
                {status === 'candidates_ready' ? 'ANALYSIS READY' : status.toUpperCase()}
              </span>
              {isRunning && (
                <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Clock size={13} />
                  <span>Elapsed: {elapsedSec}s</span>
                </span>
              )}
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800 }}>{project.title}</h2>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Channel: <span style={{ color: 'var(--text-main)' }}>{project.uploader}</span> • Duration: {formatDuration(project.duration)}
            </div>
          </div>
          {isRunning && (
            <button className="btn btn-danger" onClick={() => setShowCancelDialog(true)}>
              <XCircle size={16} />
              <span>Cancel Job</span>
            </button>
          )}
        </div>
      </div>

      {/* Long-Stream Architecture Metric Box */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 16,
      }}>
        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', fontWeight: 600 }}>SOURCE DURATION</div>
          <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 4 }}>
            {formatDuration(long_stream_info?.source_duration || project.duration)}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Stream Chunks: <span className="font-mono tabular-nums">{long_stream_info?.chunks_processed || 1} / {long_stream_info?.total_chunks || 1}</span>
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', fontWeight: 600 }}>MOMENTS DETECTED</div>
          <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-purple)', marginTop: 4 }}>
            {long_stream_info?.candidates_detected || project.candidates.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Audio & Combat Peaks
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', fontWeight: 600 }}>STRONG CLIMAXES</div>
          <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-cyan)', marginTop: 4 }}>
            {long_stream_info?.strong_moments || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Score ≥ 70 / 100
          </div>
        </div>

        <div className="card" style={{ padding: '14px 18px' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', fontWeight: 600 }}>RECOMMENDED SHORTS</div>
          <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-green)', marginTop: 4 }}>
            {long_stream_info?.recommended_shorts || project.selected_candidate_ids.length || 5}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Quality-Gated Quota
          </div>
        </div>
      </div>

      {/* Main Progress Bar & Stage */}
      <div className="card card-glow" style={{ padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {getStageIcon()}
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>{progress.stage}</h3>
          </div>
          <span className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
            {progress.percent}%
          </span>
        </div>

        {/* Progress Bar */}
        <div style={{
          width: '100%',
          height: 12,
          background: 'rgba(0,0,0,0.5)',
          borderRadius: 6,
          overflow: 'hidden',
          border: '1px solid var(--border-color)',
          marginBottom: 14,
        }}>
          <div
            className="progress-glow"
            style={{
              width: `${progress.percent}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #00F2FE 0%, #4FACFE 50%, #8B5CF6 100%)',
              transition: 'width 0.4s ease',
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          <span>{progress.message}</span>
          <span>Step {progress.step} / {progress.total_steps}</span>
        </div>

        {/* Failure Box */}
        {isFailed && error && (
          <div style={{
            marginTop: 18,
            padding: 16,
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 8,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-red)', fontWeight: 600 }}>
              <AlertTriangle size={18} />
              <span>{error.summary}</span>
            </div>
            <pre style={{
              marginTop: 10,
              fontSize: '0.75rem',
              color: '#fca5a5',
              overflowX: 'auto',
              maxHeight: 140,
              whiteSpace: 'pre-wrap',
            }}>
              {error.details}
            </pre>
            <button className="btn btn-primary" onClick={onRetry} style={{ marginTop: 12 }}>
              <RotateCw size={15} />
              <span>Retry Processing</span>
            </button>
          </div>
        )}

        {/* Completion Proceed Button */}
        {isCompleted && (
          <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-primary" onClick={onProceed} style={{ padding: '10px 24px' }}>
              <span>{status === 'candidates_ready' ? 'Review Discovered Moments' : 'View Publishing Packages'}</span>
              <ArrowRight size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Terminal Logs Viewer */}
      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Terminal size={16} color="var(--text-dim)" />
          <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)' }}>Live Execution Logs</h4>
        </div>
        <div
          ref={logContainerRef}
          style={{
            background: '#070a0e',
            border: '1px solid var(--border-color)',
            borderRadius: 8,
            padding: 14,
            height: 180,
            overflowY: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.78rem',
            color: '#a1a1aa',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          {progress.logs.length === 0 ? (
            <div style={{ color: 'var(--text-dim)' }}>Waiting for pipeline logs...</div>
          ) : (
            progress.logs.map((log, index) => (
              <div key={index} style={{ wordBreak: 'break-word' }}>{log}</div>
            ))
          )}
        </div>
      </div>

      {/* Cancel Confirmation Modal */}
      <ConfirmDialog
        isOpen={showCancelDialog}
        title="Cancel Active Task"
        message="Are you sure you want to cancel the active processing job? Any partially extracted data will remain available."
        confirmText="Yes, Cancel Job"
        isDestructive
        onConfirm={() => {
          setShowCancelDialog(false)
          onCancel()
        }}
        onCancel={() => setShowCancelDialog(false)}
      />
    </div>
  )
}

