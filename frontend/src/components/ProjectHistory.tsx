import React, { useState } from 'react'
import { Trash2, Video, Radio, Sparkles, AlertCircle, CheckCircle2, ChevronRight, Search, Film, Clock } from 'lucide-react'
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
        background: 'linear-gradient(135deg, rgba(16, 21, 31, 0.95) 0%, rgba(20, 27, 40, 0.9) 100%)',
        padding: '36px 32px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute',
          top: -40,
          right: -40,
          width: 220,
          height: 220,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0, 242, 254, 0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        <div style={{ maxWidth: 720 }}>
          <span className="badge badge-cyan" style={{ marginBottom: 12 }}>LOCAL-FIRST CREATOR STUDIO</span>
          <h1 style={{
            fontSize: '2.1rem',
            fontWeight: 800,
            lineHeight: 1.25,
            letterSpacing: '-0.02em',
            marginBottom: 10,
          }}>
            Turn long gaming videos into <span style={{ background: 'linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>high-quality Shorts</span> automatically.
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '1rem', lineHeight: 1.6, marginBottom: 20 }}>
            Discover the moments worth posting with Whisper speech alignment, gaming audio peaks, karaoke subtitles, and context-aware effects.
          </p>

          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={onNewProject} style={{ padding: '10px 24px', fontSize: '0.95rem' }}>
              <Sparkles size={18} />
              <span>+ New Project</span>
            </button>
            <div style={{ display: 'flex', gap: 16, fontSize: '0.85rem', color: 'var(--text-dim)', paddingLeft: 8 }}>
              <span>Projects: <strong style={{ color: 'var(--text-main)' }}>{projects.length}</strong></span>
              <span>•</span>
              <span>Published Shorts: <strong style={{ color: 'var(--accent-cyan)' }}>{totalShorts}</strong></span>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 440 }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search size={16} color="var(--text-dim)" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
            <input
              type="text"
              className="input-text"
              placeholder="Search projects by title, creator, or video ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: 36 }}
            />
          </div>
        </div>

        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Showing {filteredProjects.length} of {projects.length} projects
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
          gap: 20,
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
                  background: 'rgba(0,0,0,0.4)',
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
                      <span style={{ fontSize: '0.75rem' }}>Phase 7 Studio</span>
                    </div>
                  )}

                  {/* Duration Pill */}
                  <div style={{
                    position: 'absolute',
                    bottom: 8,
                    right: 8,
                    background: 'rgba(0,0,0,0.8)',
                    borderRadius: 4,
                    padding: '2px 6px',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}>
                    <Clock size={11} />
                    <span>{formatDuration(proj.duration)}</span>
                  </div>

                  {/* Top Status Badge */}
                  <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {proj.source_type === 'live_stream' && (
                      <span className="badge badge-red" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Radio size={10} /> LIVE
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
                    fontSize: '1rem',
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
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Channel: <span style={{ color: 'var(--text-main)' }}>{proj.uploader}</span>
                  </div>
                </div>

                {/* Metrics Row */}
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  background: 'rgba(0,0,0,0.25)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: '0.78rem',
                  border: '1px solid var(--border-color)',
                }}>
                  <div>
                    <span style={{ color: 'var(--text-dim)' }}>Moments: </span>
                    <strong style={{ color: 'var(--accent-purple)' }}>{proj.candidates_count} detected</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-dim)' }}>Shorts: </span>
                    <strong style={{ color: 'var(--accent-cyan)' }}>{proj.shorts_count} ready</strong>
                  </div>
                </div>

                {/* Bottom Actions Bar */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingTop: 10,
                  borderTop: '1px solid var(--border-color)',
                  fontSize: '0.75rem',
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
                      style={{ padding: '5px 8px', color: '#f87171' }}
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
