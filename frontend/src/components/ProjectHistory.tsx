import React, { useState } from 'react'
import { Trash2, Video, Sparkles, AlertCircle, CheckCircle2, ChevronRight, Search, Film, Clock } from 'lucide-react'
import type { ProjectSummary } from '../types'
import { ConfirmDialog } from './ui/ConfirmDialog'
import { EmptyState } from './ui/EmptyState'

interface ProjectHistoryProps {
  projects: ProjectSummary[]
  onSelectProject: (id: string) => void
  onDeleteProject: (id: string) => void
  onNewProject: () => void
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

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return 'Recent'
  }
}

export const ProjectHistory: React.FC<ProjectHistoryProps> = ({
  projects,
  onSelectProject,
  onDeleteProject,
  onNewProject,
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ProjectSummary | null>(null)

  const filteredProjects = projects.filter((p) => {
    const q = searchQuery.toLowerCase()
    return (
      p.title.toLowerCase().includes(q) ||
      p.uploader.toLowerCase().includes(q) ||
      p.video_id.toLowerCase().includes(q)
    )
  })

  const totalShorts = projects.reduce((acc, p) => acc + (p.shorts_count || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Hero Section */}
      <div className="card card-glow" style={{
        background: 'linear-gradient(135deg, rgba(13, 19, 34, 0.95) 0%, rgba(19, 28, 49, 0.88) 100%)',
        padding: '36px 36px',
        position: 'relative',
        overflow: 'hidden',
        border: '1px solid rgba(148, 163, 184, 0.15)',
      }}>
        <div style={{
          position: 'absolute',
          top: -60,
          right: -60,
          width: 260,
          height: 260,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(34, 211, 238, 0.14) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        <div style={{ maxWidth: 740, position: 'relative', zIndex: 1 }}>
          <span className="badge badge-cyan" style={{ marginBottom: 14 }}>LOCAL-FIRST CREATOR STUDIO</span>
          <h1 style={{
            fontSize: '2.2rem',
            fontWeight: 800,
            lineHeight: 1.25,
            letterSpacing: '-0.025em',
            marginBottom: 12,
          }}>
            Turn gaming streams into <span style={{ background: 'linear-gradient(135deg, #22D3EE 0%, #3B82F6 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>publish-ready Shorts</span> automatically.
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.98rem', lineHeight: 1.6, marginBottom: 24 }}>
            Local Whisper speech transcription, game event computer vision, karaoke subtitles, and multi-tier previewing — 100% free with zero cloud dependencies.
          </p>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={onNewProject} style={{ padding: '11px 26px', fontSize: '0.95rem' }}>
              <Sparkles size={18} />
              <span>+ New Project</span>
            </button>
            <div style={{ display: 'flex', gap: 14, fontSize: '0.85rem', color: 'var(--text-dim)', paddingLeft: 6 }}>
              <span>Projects: <strong className="font-mono tabular-nums" style={{ color: 'var(--text-main)' }}>{projects.length}</strong></span>
              <span>•</span>
              <span>Published Shorts: <strong className="font-mono tabular-nums" style={{ color: 'var(--accent-cyan)' }}>{totalShorts}</strong></span>
            </div>
          </div>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 14,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 460 }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search size={16} color="var(--text-dim)" style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)' }} />
            <input
              type="text"
              className="input-text"
              placeholder="Search projects by title, creator, or video ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: 38 }}
            />
          </div>
        </div>

        <div style={{ fontSize: '0.82rem', color: 'var(--text-dim)' }}>
          Showing <strong className="font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>{filteredProjects.length}</strong> of <span className="font-mono tabular-nums">{projects.length}</span> projects
        </div>
      </div>

      {/* Projects Grid */}
      {filteredProjects.length === 0 ? (
        <EmptyState
          icon={<Video size={30} />}
          title={searchQuery ? 'No Matching Projects' : 'No Projects Yet'}
          description={searchQuery ? `No project matched "${searchQuery}". Try a different search keyword.` : 'Paste a gaming video or livestream URL to let AI detect your best moments.'}
          actionText={searchQuery ? 'Clear Search' : 'Analyze First Video'}
          onAction={searchQuery ? () => setSearchQuery('') : onNewProject}
        />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 22,
        }}>
          {filteredProjects.map((proj) => {
            const isCompleted = proj.status === 'completed'
            const isAnalyzing = proj.status === 'analyzing' || proj.status === 'rendering'
            const isFailed = proj.status === 'failed'

            // Thumbnail URL if candidate 1 exists
            const thumbUrl = `/api/projects/${proj.id}/files/publishing/candidate_01/thumbnail.jpg`

            return (
              <div
                key={proj.id}
                className="card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 14,
                  cursor: 'pointer',
                  position: 'relative',
                  overflow: 'hidden',
                  padding: 16,
                  transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.borderColor = 'rgba(34, 211, 238, 0.3)'
                  e.currentTarget.style.boxShadow = '0 12px 28px rgba(0, 0, 0, 0.45), 0 0 16px rgba(34, 211, 238, 0.08)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)'
                  e.currentTarget.style.borderColor = 'var(--border-color)'
                  e.currentTarget.style.boxShadow = 'inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 4px 20px rgba(0, 0, 0, 0.35)'
                }}
                onClick={() => onSelectProject(proj.id)}
              >
                {/* Media Banner / Poster */}
                <div style={{
                  position: 'relative',
                  width: '100%',
                  aspectRatio: '16 / 9',
                  borderRadius: 8,
                  overflow: 'hidden',
                  background: 'rgba(0,0,0,0.5)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  {isCompleted ? (
                    <img
                      src={thumbUrl}
                      alt={proj.title}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, color: 'var(--text-dim)' }}>
                      <Film size={28} />
                      <span style={{ fontSize: '0.74rem' }}>Phase 7 Studio</span>
                    </div>
                  )}

                  {/* Duration Pill */}
                  <div style={{
                    position: 'absolute',
                    bottom: 8,
                    right: 8,
                    background: 'rgba(7, 11, 20, 0.85)',
                    backdropFilter: 'blur(4px)',
                    borderRadius: 4,
                    padding: '2px 6px',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                  }}>
                    <Clock size={11} />
                    <span className="font-mono tabular-nums">{formatDuration(proj.duration)}</span>
                  </div>

                  {/* Top Status Badge */}
                  <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {proj.source_type === 'live_stream' && (
                      <span className="badge badge-red" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                        <span className="live-dot-pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: '#F43F5E', display: 'inline-block' }} />
                        LIVE
                      </span>
                    )}
                    {isCompleted && <span className="badge badge-green"><CheckCircle2 size={11} /> COMPLETED</span>}
                    {isAnalyzing && <span className="badge badge-cyan">PROCESSING ({proj.percent}%)</span>}
                    {isFailed && <span className="badge badge-red"><AlertCircle size={11} /> FAILED</span>}
                    {!isCompleted && !isAnalyzing && !isFailed && (
                      <span className="badge badge-purple">{proj.status.replace('_', ' ')}</span>
                    )}
                  </div>
                </div>

                {/* Title & Channel */}
                <div>
                  <h3 style={{
                    fontSize: '0.98rem',
                    fontWeight: 700,
                    lineHeight: 1.4,
                    marginBottom: 4,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}>
                    {proj.title}
                  </h3>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Channel: <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>{proj.uploader}</span>
                  </div>
                </div>

                {/* Metrics Row */}
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  background: 'rgba(0, 0, 0, 0.3)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: '0.76rem',
                  border: '1px solid var(--border-color)',
                }}>
                  <div>
                    <span style={{ color: 'var(--text-dim)' }}>Moments: </span>
                    <strong className="font-mono tabular-nums" style={{ color: 'var(--accent-purple)' }}>{proj.candidates_count} detected</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-dim)' }}>Shorts: </span>
                    <strong className="font-mono tabular-nums" style={{ color: 'var(--accent-cyan)' }}>{proj.shorts_count} ready</strong>
                  </div>
                </div>

                {/* Bottom Actions Bar */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingTop: 10,
                  borderTop: '1px solid var(--border-color)',
                  fontSize: '0.74rem',
                  color: 'var(--text-dim)',
                }}>
                  <span>Updated {formatDate(proj.updated_at)}</span>

                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      className="btn btn-secondary"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteTarget(proj)
                      }}
                      style={{ padding: '5px 8px', color: '#FDA4AF' }}
                      title="Delete project"
                    >
                      <Trash2 size={14} />
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={(e) => {
                        e.stopPropagation()
                        onSelectProject(proj.id)
                      }}
                      style={{ padding: '5px 12px', fontSize: '0.8rem' }}
                    >
                      <span>Open</span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="Delete Project?"
        message={`Are you sure you want to delete "${deleteTarget?.title}"? All rendered clips, thumbnails, and cache files will be removed from disk.`}
        confirmText="Delete Project"
        isDestructive={true}
        onConfirm={() => {
          if (deleteTarget) {
            onDeleteProject(deleteTarget.id)
            setDeleteTarget(null)
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
