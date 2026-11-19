import React, { useState, useMemo } from 'react'
import { CheckSquare, Square, Flame, ArrowRight, Filter, SlidersHorizontal, ShieldCheck, AlertTriangle, XCircle, CheckCircle, Video, Play } from 'lucide-react'
import type { Candidate, ProjectDetail, CandidateSortOption, CandidateFilterOption } from '../types'
import { getFileUrl } from '../api/client'
import { ScoreBar } from './ui/ScoreBar'
import { ConfirmDialog } from './ui/ConfirmDialog'
import { EmptyState } from './ui/EmptyState'

interface CandidateReviewProps {
  project: ProjectDetail
  onRender: (selectedCandidateIds: number[]) => void
  onBackToHistory: () => void
  onOpenPublishing?: () => void
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

export const CandidateReview: React.FC<CandidateReviewProps> = ({
  project,
  onRender,
  onBackToHistory,
  onOpenPublishing,
}) => {
  const [selectedIds, setSelectedIds] = useState<number[]>(
    project.selected_candidate_ids.length > 0
      ? project.selected_candidate_ids
      : project.candidates.slice(0, 5).map((c) => c.candidate_id || c.rank)
  )

  const [activePreviewId, setActivePreviewId] = useState<number>(
    project.candidates[0]?.candidate_id || project.candidates[0]?.rank || 1
  )

  const activePreviewCandidate = useMemo<Candidate | null>(() => {
    return (
      project.candidates.find((c) => (c.candidate_id || c.rank) === activePreviewId) ||
      project.candidates[0] ||
      null
    )
  }, [project.candidates, activePreviewId])

  const [filter, setFilter] = useState<CandidateFilterOption>('all')
  const [sort, setSort] = useState<CandidateSortOption>('score')
  const [isRenderConfirmOpen, setIsRenderConfirmOpen] = useState(false)

  // Creator quality counts
  const publishCount = useMemo(() =>
    project.candidates.filter((c) => c.publishability?.recommendation === 'publish').length,
    [project.candidates]
  )
  const reviewCount = useMemo(() =>
    project.candidates.filter((c) => c.publishability?.recommendation === 'review').length,
    [project.candidates]
  )
  const rejectCount = useMemo(() =>
    project.candidates.filter((c) => c.publishability?.recommendation === 'reject').length,
    [project.candidates]
  )
  const strongMomentsCount = useMemo(() =>
    project.candidates.filter((c) => c.final_score >= 70).length,
    [project.candidates]
  )

  // Filter and sort candidates
  const processedCandidates = useMemo(() => {
    let result = [...project.candidates]

    // Quality Gate & Semantic Filtering
    if (filter === 'publish') {
      result = result.filter((c) => c.publishability?.recommendation === 'publish')
    } else if (filter === 'review') {
      result = result.filter((c) => c.publishability?.recommendation === 'review')
    } else if (filter === 'reject') {
      result = result.filter((c) => c.publishability?.recommendation === 'reject')
    } else if (filter === 'strong') {
      result = result.filter((c) => c.final_score >= 70)
    } else if (filter === 'funny') {
      result = result.filter((c) => c.tone?.includes('funny') || c.gameplay_event?.includes('fail') || c.gameplay_event?.includes('timing'))
    } else if (filter === 'combat') {
      result = result.filter((c) => c.gameplay_event?.includes('clutch') || c.gameplay_event?.includes('shot') || c.gameplay_event?.includes('kill'))
    } else if (filter === 'timing') {
      result = result.filter((c) => c.gameplay_event?.includes('timing') || c.signals?.some((s) => s.includes('timing')))
    }

    // Sorting
    if (sort === 'score') {
      result.sort((a, b) => b.final_score - a.final_score)
    } else if (sort === 'publishability') {
      result.sort((a, b) => (b.publishability?.score ?? 0) - (a.publishability?.score ?? 0))
    } else if (sort === 'duration') {
      result.sort((a, b) => a.duration - b.duration)
    } else if (sort === 'rank') {
      result.sort((a, b) => (a.rank || a.candidate_id) - (b.rank || b.candidate_id))
    }

    return result
  }, [project.candidates, filter, sort])

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }

  const selectTopN = (n: number) => {
    const ids = project.candidates.slice(0, n).map((c) => c.rank || c.candidate_id)
    setSelectedIds(ids)
  }

  const selectRecommended = () => {
    const publishable = project.candidates.filter(c => c.publishability?.recommendation === 'publish')
    if (publishable.length > 0) {
      setSelectedIds(publishable.map(c => c.rank || c.candidate_id))
    } else {
      const recCount = project.long_stream_info?.recommended_shorts || 5
      selectTopN(recCount)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span className="badge badge-purple">PHASE 7E CREATOR QUALITY</span>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>
              • {project.candidates.length} moments evaluated across 6 creator dimensions
            </span>
          </div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Candidate Review & Creator Quality Gate
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Source: <strong style={{ color: 'var(--text-main)' }}>{project.title}</strong> ({project.uploader})
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn btn-secondary" onClick={onBackToHistory}>
            Back to Projects
          </button>
          {project.published_packages && project.published_packages.length > 0 && onOpenPublishing && (
            <button
              className="btn btn-secondary"
              onClick={onOpenPublishing}
              style={{ borderColor: 'var(--accent-green)', color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <CheckCircle size={15} />
              <span>View Publishing Packages ({project.published_packages.length})</span>
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={() => setIsRenderConfirmOpen(true)}
            disabled={selectedIds.length === 0}
            style={{ padding: '8px 22px' }}
          >
            <span>Render {selectedIds.length} Selected Shorts</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>

      {/* Creator Quality Gate Summary Banner */}
      <div className="card" style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
        padding: '14px 20px',
        background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.08) 0%, rgba(59, 130, 246, 0.08) 100%)',
        border: '1px solid rgba(16, 185, 129, 0.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ShieldCheck size={26} color="var(--accent-green)" />
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>
              Creator Quality Intelligence Active
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Evaluating complete Shorts potential (Moment, Narrative, Presentation, Publishing, Technical, Diversity).
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'center', padding: '4px 12px', background: 'rgba(16, 185, 129, 0.15)', borderRadius: 6 }}>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-green)' }}>{publishCount}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>READY TO PUBLISH</div>
          </div>
          <div style={{ textAlign: 'center', padding: '4px 12px', background: 'rgba(245, 158, 11, 0.15)', borderRadius: 6 }}>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-amber)' }}>{reviewCount}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>NEEDS REVIEW</div>
          </div>
          <div style={{ textAlign: 'center', padding: '4px 12px', background: 'rgba(239, 68, 68, 0.15)', borderRadius: 6 }}>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#f87171' }}>{rejectCount}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>REJECTED</div>
          </div>
        </div>
      </div>

      {/* Control Bar: Filters, Sorting & Selection Toolbar */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
          {/* Filter Pills */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Filter size={14} /> Gate Filter:
            </span>
            <button
              className={`btn ${filter === 'all' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('all')}
              style={{ padding: '4px 10px', fontSize: '0.8rem' }}
            >
              All ({project.candidates.length})
            </button>
            <button
              className={`btn ${filter === 'publish' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('publish')}
              style={{ padding: '4px 10px', fontSize: '0.8rem', color: filter === 'publish' ? '#fff' : 'var(--accent-green)' }}
            >
              Publish ({publishCount})
            </button>
            <button
              className={`btn ${filter === 'review' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('review')}
              style={{ padding: '4px 10px', fontSize: '0.8rem', color: filter === 'review' ? '#fff' : 'var(--accent-amber)' }}
            >
              Review ({reviewCount})
            </button>
            <button
              className={`btn ${filter === 'reject' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('reject')}
              style={{ padding: '4px 10px', fontSize: '0.8rem', color: filter === 'reject' ? '#fff' : '#f87171' }}
            >
              Reject ({rejectCount})
            </button>
            <button
              className={`btn ${filter === 'strong' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('strong')}
              style={{ padding: '4px 10px', fontSize: '0.8rem' }}
            >
              Strong Moment (≥70) ({strongMomentsCount})
            </button>
            <button
              className={`btn ${filter === 'combat' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('combat')}
              style={{ padding: '4px 10px', fontSize: '0.8rem' }}
            >
              Combat & Clutches
            </button>
            <button
              className={`btn ${filter === 'funny' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('funny')}
              style={{ padding: '4px 10px', fontSize: '0.8rem' }}
            >
              Funny
            </button>
          </div>

          {/* Sort Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <SlidersHorizontal size={14} /> Sort:
            </span>
            <select
              className="select"
              value={sort}
              onChange={(e) => setSort(e.target.value as any)}
              style={{ padding: '5px 10px', fontSize: '0.8rem' }}
            >
              <option value="publishability">Highest Publishability</option>
              <option value="score">Highest Moment Score</option>
              <option value="duration">Shortest Duration</option>
              <option value="rank">Chronological (Rank)</option>
            </select>
          </div>
        </div>

        {/* Quick Selection Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, paddingTop: 10, borderTop: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Selection:</span>
            <button className="btn btn-secondary" onClick={selectRecommended} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
              Publish-Ready ({publishCount > 0 ? publishCount : project.long_stream_info?.recommended_shorts || 5})
            </button>
            <button className="btn btn-secondary" onClick={() => selectTopN(3)} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
              Top 3
            </button>
            <button className="btn btn-secondary" onClick={() => selectTopN(5)} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
              Top 5
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setSelectedIds(project.candidates.map((c) => c.rank || c.candidate_id))}
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              Select All
            </button>
            <button className="btn btn-secondary" onClick={() => setSelectedIds([])} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
              Clear
            </button>
          </div>

          <div style={{ fontSize: '0.85rem' }}>
            <strong style={{ color: 'var(--accent-cyan)' }}>{selectedIds.length}</strong> selected for 9:16 rendering
          </div>
        </div>
      </div>

      {/* Main Workspace: Left Candidate Cards, Right Audit & Preview Panel */}
      {processedCandidates.length === 0 ? (
        <EmptyState
          icon={<Filter size={28} />}
          title="No Candidates Match Filter"
          description="Try selecting a different filter category to view other detected gaming moments."
          actionText="Show All Candidates"
          onAction={() => setFilter('all')}
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(360px, 1fr)', gap: 24, alignItems: 'start' }}>
          {/* Left: Candidate Cards List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {processedCandidates.map((c) => {
              const id = c.candidate_id || c.rank
              const isSelected = selectedIds.includes(id)
              const isActive = activePreviewCandidate ? ((activePreviewCandidate.candidate_id || activePreviewCandidate.rank) === id) : false
              const isCandRendered = Boolean(c.rendered || c.output?.video_url || project.published_packages?.some((pkg) => pkg.candidate_id === id))
              const pub = c.publishability

              return (
                <div
                  key={id}
                  className="card"
                  onClick={() => setActivePreviewId(id)}
                  style={{
                    display: 'flex',
                    gap: 16,
                    padding: 18,
                    cursor: 'pointer',
                    borderColor: isActive ? 'var(--accent-cyan)' : (isSelected ? 'rgba(0, 242, 254, 0.4)' : 'var(--border-color)'),
                    background: isActive ? '#141c29' : 'var(--bg-card)',
                    boxShadow: isActive ? '0 0 18px rgba(0, 242, 254, 0.12)' : 'none',
                    transition: 'all 0.18s ease',
                  }}
                >
                  {/* Checkbox */}
                  <div
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleSelect(id)
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      color: isSelected ? 'var(--accent-cyan)' : 'var(--text-dim)',
                    }}
                  >
                    {isSelected ? <CheckSquare size={22} /> : <Square size={22} />}
                  </div>

                  {/* Candidate Content */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {/* Header Row: Rank, Time Window, Scores */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className="badge badge-purple" style={{ fontSize: '0.8rem', padding: '3px 8px' }}>
                          RANK #{c.rank || id}
                        </span>
                        {c.chunk_id && (
                          <span className="badge badge-cyan" style={{ fontSize: '0.75rem', padding: '2px 6px' }}>
                            {c.chunk_id}
                          </span>
                        )}
                        {isCandRendered && (
                          <span className="badge badge-green" style={{ fontSize: '0.72rem', padding: '2px 6px', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Video size={11} /> 9:16 RENDERED
                          </span>
                        )}
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>
                          {formatTime(c.start)} → {formatTime(c.end)} ({c.duration.toFixed(1)}s)
                        </span>
                      </div>

                      {/* Dual Score Badges */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        {/* Publishability Badge */}
                        {pub && (
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '3px 8px',
                            borderRadius: 6,
                            background: pub.recommendation === 'publish' ? 'rgba(16, 185, 129, 0.2)' : (pub.recommendation === 'review' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(239, 68, 68, 0.2)'),
                            border: `1px solid ${pub.recommendation === 'publish' ? 'var(--accent-green)' : (pub.recommendation === 'review' ? 'var(--accent-amber)' : '#f87171')}`,
                          }}>
                            {pub.recommendation === 'publish' ? <CheckCircle size={13} color="var(--accent-green)" /> : (pub.recommendation === 'review' ? <AlertTriangle size={13} color="var(--accent-amber)" /> : <XCircle size={13} color="#f87171" />)}
                            <span style={{
                              fontSize: '0.78rem',
                              fontWeight: 700,
                              color: pub.recommendation === 'publish' ? 'var(--accent-green)' : (pub.recommendation === 'review' ? 'var(--accent-amber)' : '#f87171'),
                            }}>
                              PUBLISHABILITY: {pub.score.toFixed(1)} [{pub.level.toUpperCase()}]
                            </span>
                          </div>
                        )}

                        {/* Raw Moment Score */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Flame size={15} color="var(--accent-cyan)" />
                          <span style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                            Moment: {c.final_score.toFixed(1)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Semantic Tags */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {c.gameplay_event && (
                        <span className="badge badge-cyan">{c.gameplay_event}</span>
                      )}
                      {c.tone && (
                        <span className="badge badge-amber">{c.tone}</span>
                      )}
                      {c.strongest_reaction && c.strongest_reaction !== 'unknown' && (
                        <span className="badge badge-green">"{c.strongest_reaction}"</span>
                      )}
                      {c.secondary_events?.map((sec, sIdx) => (
                        <span key={sIdx} className="badge badge-purple" style={{ opacity: 0.8 }}>
                          {sec}
                        </span>
                      ))}
                    </div>

                    {/* 6 Creator Dimensions Breakdown */}
                    {pub?.dimensions && (
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(6, 1fr)',
                        gap: 6,
                        background: 'rgba(0,0,0,0.35)',
                        padding: '6px 10px',
                        borderRadius: 6,
                      }}>
                        <ScoreBar label="Moment" score={pub.dimensions.moment ?? 0} />
                        <ScoreBar label="Narrative" score={pub.dimensions.narrative ?? 0} />
                        <ScoreBar label="Visual/Audio" score={pub.dimensions.presentation ?? 0} />
                        <ScoreBar label="Publishing" score={pub.dimensions.publishing ?? 0} />
                        <ScoreBar label="Technical" score={pub.dimensions.technical ?? 0} />
                        <ScoreBar label="Diversity" score={pub.dimensions.diversity ?? 0} />
                      </div>
                    )}

                    {/* Key Reason & Warning Tags */}
                    {pub && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.78rem' }}>
                        {pub.reasons.length > 0 && (
                          <div style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span>✓</span>
                            <span>{pub.reasons[0]}</span>
                          </div>
                        )}
                        {pub.warnings.length > 0 && (
                          <div style={{ color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span>⚠</span>
                            <span>{pub.warnings[0]}</span>
                          </div>
                        )}
                        {pub.blocking_issues.length > 0 && (
                          <div style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span>✕</span>
                            <span>{pub.blocking_issues[0]}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right: Selected Candidate Preview & Creator Quality Auditor Card */}
          {activePreviewCandidate && (
            <div className="card card-glow" style={{ position: 'sticky', top: 90, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
                  Candidate #{activePreviewCandidate.rank} Audit & Preview
                </h3>
                {activePreviewCandidate.publishability && (
                  <span className={`badge ${activePreviewCandidate.publishability.recommendation === 'publish' ? 'badge-green' : (activePreviewCandidate.publishability.recommendation === 'review' ? 'badge-amber' : 'badge-red')}`}>
                    {activePreviewCandidate.publishability.recommendation.toUpperCase()}
                  </span>
                )}
              </div>

              {/* Video Player or Pre-Render Preview Card */}
              {(() => {
                const activeCid = activePreviewCandidate.candidate_id || activePreviewCandidate.rank
                const matchingPkg = project.published_packages?.find((pkg) => pkg.candidate_id === activeCid)
                const isRendered = Boolean(
                  activePreviewCandidate.rendered ||
                  activePreviewCandidate.output?.video_url ||
                  matchingPkg
                )
                const renderedVideoUrl = activePreviewCandidate.output?.video_url
                  ? activePreviewCandidate.output.video_url
                  : (isRendered
                      ? getFileUrl(project.id, `publishing/candidate_${activeCid.toString().padStart(2, '0')}/final.mp4`)
                      : null)

                if (isRendered && renderedVideoUrl) {
                  return (
                    <div style={{
                      width: '100%',
                      borderRadius: 8,
                      overflow: 'hidden',
                      background: '#000',
                      border: '1px solid var(--accent-cyan)',
                      boxShadow: '0 4px 20px rgba(0, 242, 254, 0.15)',
                    }}>
                      <div style={{
                        padding: '8px 12px',
                        background: 'rgba(0, 242, 254, 0.08)',
                        borderBottom: '1px solid rgba(0, 242, 254, 0.2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                          <CheckCircle size={14} color="var(--accent-cyan)" />
                          <span>Rendered 9:16 Vertical Video</span>
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          HTTP 206 Streaming
                        </span>
                      </div>
                      <video
                        controls
                        playsInline
                        preload="metadata"
                        key={renderedVideoUrl}
                        src={renderedVideoUrl}
                        style={{ width: '100%', maxHeight: 380, display: 'block', margin: '0 auto', background: '#000' }}
                      >
                        Your browser does not support video preview.
                      </video>
                    </div>
                  )
                }

                return (
                  <div style={{
                    width: '100%',
                    borderRadius: 8,
                    background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%)',
                    border: '1px dashed var(--border-color)',
                    padding: '20px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    textAlign: 'center',
                    gap: 10,
                  }}>
                    <div style={{
                      width: 42,
                      height: 42,
                      borderRadius: '50%',
                      background: 'rgba(99, 102, 241, 0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--accent-primary)',
                    }}>
                      <Video size={22} />
                    </div>

                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: 2 }}>
                        Candidate Awaiting 9:16 Render
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        Source Window: <strong>{formatTime(activePreviewCandidate.start)} → {formatTime(activePreviewCandidate.end)}</strong> ({activePreviewCandidate.duration.toFixed(1)}s)
                      </div>
                    </div>

                    {/* Source Audio Preview snippet */}
                    <div style={{ width: '100%', maxWidth: 300, marginTop: 2 }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                        <Play size={11} /> Source Audio Snippet
                      </div>
                      <audio
                        controls
                        preload="none"
                        src={`${getFileUrl(project.id, 'audio.wav')}#t=${activePreviewCandidate.start.toFixed(1)},${activePreviewCandidate.end.toFixed(1)}`}
                        style={{ width: '100%', height: 32 }}
                      />
                    </div>

                    <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', background: 'rgba(255,255,255,0.04)', padding: '6px 12px', borderRadius: 4, maxWidth: 300 }}>
                      Select this candidate and click <strong>Render Selected Shorts</strong> below to produce the vertical video with subtitles, effects & SFX.
                    </div>
                  </div>
                )
              })()}

              {/* Creator Quality Dimension Breakdown */}
              {activePreviewCandidate.publishability && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-dim)' }}>
                      6-DIMENSION CREATOR SCORE:
                    </span>
                    <strong style={{ color: 'var(--accent-green)', fontSize: '1.05rem' }}>
                      {activePreviewCandidate.publishability.score.toFixed(1)} / 100
                    </strong>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                    <ScoreBar label="Moment Quality" score={activePreviewCandidate.publishability.dimensions.moment ?? 0} />
                    <ScoreBar label="Narrative Quality" score={activePreviewCandidate.publishability.dimensions.narrative ?? 0} />
                    <ScoreBar label="Presentation Quality" score={activePreviewCandidate.publishability.dimensions.presentation ?? 0} />
                    <ScoreBar label="Publishing Quality" score={activePreviewCandidate.publishability.dimensions.publishing ?? 0} />
                    <ScoreBar label="Technical Quality" score={activePreviewCandidate.publishability.dimensions.technical ?? 0} />
                    <ScoreBar label="Diversity Quality" score={activePreviewCandidate.publishability.dimensions.diversity ?? 0} />
                  </div>
                </div>
              )}

              {/* Audit Reasons & Warnings */}
              {activePreviewCandidate.publishability && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '0.8rem' }}>
                  {activePreviewCandidate.publishability.reasons.length > 0 && (
                    <div>
                      <div style={{ color: 'var(--accent-green)', fontWeight: 600, marginBottom: 4 }}>
                        Strengths ({activePreviewCandidate.publishability.reasons.length}):
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {activePreviewCandidate.publishability.reasons.slice(0, 3).map((r, i) => (
                          <div key={i} style={{ color: '#cbd5e1' }}>• {r}</div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activePreviewCandidate.publishability.warnings.length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <div style={{ color: 'var(--accent-amber)', fontWeight: 600, marginBottom: 4 }}>
                        Creator Warnings ({activePreviewCandidate.publishability.warnings.length}):
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {activePreviewCandidate.publishability.warnings.map((w, i) => (
                          <div key={i} style={{ color: '#cbd5e1' }}>⚠ {w}</div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activePreviewCandidate.publishability.blocking_issues.length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <div style={{ color: '#f87171', fontWeight: 600, marginBottom: 4 }}>
                        Blocking Issues:
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {activePreviewCandidate.publishability.blocking_issues.map((b, i) => (
                          <div key={i} style={{ color: '#fca5a5' }}>✕ {b}</div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Action Button */}
              <button
                className={`btn ${selectedIds.includes(activePreviewCandidate.rank || activePreviewCandidate.candidate_id) ? 'btn-danger' : 'btn-primary'}`}
                onClick={() => toggleSelect(activePreviewCandidate.rank || activePreviewCandidate.candidate_id)}
                style={{ marginTop: 6 }}
              >
                {selectedIds.includes(activePreviewCandidate.rank || activePreviewCandidate.candidate_id) ? 'Deselect Candidate' : 'Select for 9:16 Rendering'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Render Confirmation Modal */}
      <ConfirmDialog
        isOpen={isRenderConfirmOpen}
        title="Render Selected Shorts?"
        message={`You have selected ${selectedIds.length} candidate moments. The pipeline will render 9:16 vertical video with NVENC hardware acceleration, burn karaoke subtitles & emojis, apply context-aware effects, mix gaming SFX, and assemble complete publishing packages.`}
        confirmText={`Render ${selectedIds.length} Shorts`}
        onConfirm={() => {
          setIsRenderConfirmOpen(false)
          onRender(selectedIds)
        }}
        onCancel={() => setIsRenderConfirmOpen(false)}
      />
    </div>
  )
}
