import React, { useState, useMemo, useRef, useEffect } from 'react'
import {
  CheckSquare, Square, Flame, ArrowRight, Filter, SlidersHorizontal,
  ShieldCheck, AlertTriangle, XCircle, CheckCircle, Video, Play, Pause,
  RotateCcw, FileText, Copy, Check, Plus, MessageSquare, Clock, Sparkles, Bot
} from 'lucide-react'
import type { Candidate, ProjectDetail, CandidateSortOption, CandidateFilterOption } from '../types'
import { getFileUrl, getSourceVideoUrl, getProjectAudioUrl } from '../api/client'
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

function extractYoutubeId(project: ProjectDetail): string | null {
  if (project.youtube_video_id && /^[0-9A-Za-z_-]{11}$/.test(project.youtube_video_id)) {
    return project.youtube_video_id
  }
  const sources = [
    project.youtube_video_id,
    project.source_url,
    project.url,
    project.video_id,
    project.id,
  ]
  for (const src of sources) {
    if (!src || typeof src !== 'string') continue
    const trimmed = src.trim()
    if (/^[0-9A-Za-z_-]{11}$/.test(trimmed)) return trimmed
    const match = trimmed.match(/(?:v=|\/|youtu\.be\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})/)
    if (match) return match[1]
  }
  return null
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

  const isSquare = project.settings?.aspect_ratio === '1:1'
  const aspectLabel = isSquare ? '1:1' : '9:16'

  // Pre-render video & audio player state
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(activePreviewCandidate?.start || 0)
  const [sourceVideoError, setSourceVideoError] = useState(false)
  const [preferAudioPreview, setPreferAudioPreview] = useState(false)

  useEffect(() => {
    if (activePreviewCandidate) {
      setCurrentTime(activePreviewCandidate.start)
      setIsPlaying(false)
      setSourceVideoError(false)
      if (videoRef.current) {
        videoRef.current.currentTime = activePreviewCandidate.start
        videoRef.current.pause()
      }
      if (audioRef.current) {
        audioRef.current.currentTime = activePreviewCandidate.start
        audioRef.current.pause()
      }
    }
  }, [activePreviewCandidate?.rank, activePreviewCandidate?.candidate_id, activePreviewCandidate?.start, activePreviewCandidate?.end])

  const handlePlayPause = () => {
    if (!videoRef.current || !activePreviewCandidate) return
    if (isPlaying) {
      videoRef.current.pause()
      setIsPlaying(false)
    } else {
      if (
        videoRef.current.currentTime >= activePreviewCandidate.end ||
        videoRef.current.currentTime < activePreviewCandidate.start
      ) {
        videoRef.current.currentTime = activePreviewCandidate.start
      }
      videoRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false))
    }
  }

  const handleReplay = () => {
    if (!videoRef.current || !activePreviewCandidate) return
    videoRef.current.currentTime = activePreviewCandidate.start
    setCurrentTime(activePreviewCandidate.start)
    videoRef.current
      .play()
      .then(() => setIsPlaying(true))
      .catch(() => setIsPlaying(false))
  }

  const handleTimeUpdate = () => {
    if (!videoRef.current || !activePreviewCandidate) return
    const cur = videoRef.current.currentTime
    setCurrentTime(cur)
    if (cur >= activePreviewCandidate.end) {
      videoRef.current.pause()
      setIsPlaying(false)
      videoRef.current.currentTime = activePreviewCandidate.start
      setCurrentTime(activePreviewCandidate.start)
    }
  }

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value)
    setCurrentTime(newTime)
    if (videoRef.current) {
      videoRef.current.currentTime = newTime
    }
  }

  const [filter, setFilter] = useState<CandidateFilterOption>('all')
  const [sort, setSort] = useState<CandidateSortOption>('score')
  const [isRenderConfirmOpen, setIsRenderConfirmOpen] = useState(false)
  const [copiedDescId, setCopiedDescId] = useState<number | null>(null)
  const [isDescExpanded, setIsDescExpanded] = useState(false)

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
    if (filter === 'selected') {
      result = result.filter((c) => selectedIds.includes(c.candidate_id || c.rank))
    } else if (filter === 'publish') {
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
          <div style={{ textAlign: 'center', padding: '6px 16px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.28)', borderRadius: 8 }}>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-green)' }}>{publishCount}</div>
            <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#a7f3d0', letterSpacing: '0.04em' }}>READY TO PUBLISH</div>
          </div>
          <div style={{ textAlign: 'center', padding: '6px 16px', background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.28)', borderRadius: 8 }}>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-amber)' }}>{reviewCount}</div>
            <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#fde68a', letterSpacing: '0.04em' }}>NEEDS REVIEW</div>
          </div>
          <div style={{ textAlign: 'center', padding: '6px 16px', background: 'rgba(244, 63, 94, 0.12)', border: '1px solid rgba(244, 63, 94, 0.28)', borderRadius: 8 }}>
            <div className="font-mono tabular-nums" style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fb7185' }}>{rejectCount}</div>
            <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#fecdd3', letterSpacing: '0.04em' }}>REJECTED</div>
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
              className={`btn ${filter === 'selected' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter('selected')}
              style={{ padding: '4px 10px', fontSize: '0.8rem', color: filter === 'selected' ? '#fff' : 'var(--accent-cyan)' }}
            >
              Selected ({selectedIds.length})
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
            <strong style={{ color: 'var(--accent-cyan)' }}>{selectedIds.length}</strong> selected for {aspectLabel} rendering
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
                  className={`card ${isActive ? 'card-glow card-active' : ''}`}
                  onClick={() => setActivePreviewId(id)}
                  style={{
                    display: 'flex',
                    gap: 16,
                    padding: 18,
                    cursor: 'pointer',
                    borderColor: isActive ? 'var(--accent-cyan)' : (isSelected ? 'rgba(34, 211, 238, 0.45)' : 'var(--border-color)'),
                    background: isActive ? 'rgba(19, 28, 49, 0.95)' : 'var(--bg-card)',
                    boxShadow: isActive ? '0 0 20px rgba(34, 211, 238, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.08)' : undefined,
                    transition: 'all 0.18s cubic-bezier(0.16, 1, 0.3, 1)',
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
                            <Video size={11} /> {c.aspect_ratio === '1:1' || project.settings?.aspect_ratio === '1:1' ? '1:1 RENDERED' : '9:16 RENDERED'}
                          </span>
                        )}
                        {c.semantic_audit?.is_filler && (
                          <span className="badge badge-amber" style={{ fontSize: '0.72rem', padding: '2px 6px', background: 'rgba(239, 68, 68, 0.2)', color: '#f87171' }}>
                            FILLER
                          </span>
                        )}
                        {c.scene_cut_snapped && (
                          <span className="badge badge-purple" style={{ fontSize: '0.72rem', padding: '2px 6px' }}>
                            SCENE SNAPPED
                          </span>
                        )}
                        <span className="font-mono tabular-nums" style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>
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
                            <span className="font-mono tabular-nums" style={{
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
                          <span className="font-mono tabular-nums" style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                            Moment: {c.final_score.toFixed(1)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Semantic Tags */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {c.detected_game_title && (
                        <span className="badge badge-purple" style={{ fontWeight: 600 }}>{c.detected_game_title}</span>
                      )}
                      {c.game_archetype && c.game_archetype !== 'generic' && !c.detected_game_title && (
                        <span className="badge" style={{ background: 'rgba(255,255,255,0.08)', color: 'var(--text-dim)', fontSize: '0.72rem' }}>
                          {c.game_archetype.replace('_', ' ')}
                        </span>
                      )}
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

                // Priority 1: Rendered Short MP4
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
                          <span>{activePreviewCandidate.aspect_ratio === '1:1' || project.settings?.aspect_ratio === '1:1' ? 'Rendered 1:1 Square Video' : 'Rendered 9:16 Vertical Video'}</span>
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
                        style={{
                          width: '100%',
                          maxHeight: 380,
                          aspectRatio: activePreviewCandidate.aspect_ratio === '1:1' || project.settings?.aspect_ratio === '1:1' ? '1 / 1' : '9 / 16',
                          display: 'block',
                          margin: '0 auto',
                          background: '#000',
                          objectFit: 'contain',
                        }}
                      >
                        Your browser does not support video preview.
                      </video>
                    </div>
                  )
                }

                // Priority 2: Local source.mp4 with scoped window scrubber
                const hasLocalSource = Boolean(project.has_source_video || project.source_video_url)
                if (hasLocalSource && !sourceVideoError && !preferAudioPreview) {
                  const sourceVideoSrc = project.source_video_url || getSourceVideoUrl(project.id)
                  const candDuration = Math.max(0.1, activePreviewCandidate.end - activePreviewCandidate.start)
                  const relativeProgress = Math.min(Math.max(0, currentTime - activePreviewCandidate.start), candDuration)

                  return (
                    <div style={{
                      width: '100%',
                      borderRadius: 8,
                      overflow: 'hidden',
                      background: '#090d16',
                      border: '1px solid rgba(99, 102, 241, 0.4)',
                      boxShadow: '0 4px 20px rgba(99, 102, 241, 0.12)',
                    }}>
                      <div style={{
                        padding: '8px 12px',
                        background: 'rgba(99, 102, 241, 0.1)',
                        borderBottom: '1px solid rgba(99, 102, 241, 0.2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
                          <Video size={14} />
                          <span>Source Preview (Pre-Render)</span>
                          <span className="badge badge-cyan" style={{ fontSize: '0.7rem', padding: '1px 6px' }}>Local File</span>
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          Window: {formatTime(activePreviewCandidate.start)} → {formatTime(activePreviewCandidate.end)} ({activePreviewCandidate.duration.toFixed(1)}s)
                        </span>
                      </div>

                      <video
                        ref={videoRef}
                        playsInline
                        preload="metadata"
                        src={sourceVideoSrc}
                        onTimeUpdate={handleTimeUpdate}
                        onPlay={() => setIsPlaying(true)}
                        onPause={() => setIsPlaying(false)}
                        onClick={handlePlayPause}
                        onError={() => setSourceVideoError(true)}
                        style={{
                          width: '100%',
                          minHeight: 240,
                          maxHeight: 280,
                          aspectRatio: '16 / 9',
                          display: 'block',
                          background: '#000',
                          cursor: 'pointer',
                          objectFit: 'contain',
                        }}
                      />

                      {/* Scoped Window Scrubber & Controls */}
                      <div style={{
                        padding: '10px 14px',
                        background: 'rgba(15, 23, 42, 0.85)',
                        borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <button
                            className="btn btn-secondary"
                            onClick={handlePlayPause}
                            title={isPlaying ? 'Pause' : 'Play window'}
                            style={{ padding: '6px 10px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 4 }}
                          >
                            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
                            <span>{isPlaying ? 'Pause' : 'Play'}</span>
                          </button>
                          <button
                            className="btn btn-secondary"
                            onClick={handleReplay}
                            title="Replay candidate window"
                            style={{ padding: '6px 8px' }}
                          >
                            <RotateCcw size={14} />
                          </button>

                          <input
                            type="range"
                            min={activePreviewCandidate.start}
                            max={activePreviewCandidate.end}
                            step={0.1}
                            value={currentTime}
                            onChange={handleScrub}
                            style={{
                              flex: 1,
                              accentColor: 'var(--accent-primary)',
                              cursor: 'pointer',
                            }}
                          />

                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', minWidth: 64, textAlign: 'right', fontFamily: 'monospace' }}>
                            {formatTime(relativeProgress)} / {formatTime(candDuration)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                }

                // Priority 3: YouTube Embed fallback
                const resolvedYtId = extractYoutubeId(project)
                if (resolvedYtId && !preferAudioPreview) {
                  const startSec = Math.floor(activePreviewCandidate.start)
                  const endSec = Math.ceil(activePreviewCandidate.end)
                  const embedUrl = `https://www.youtube.com/embed/${resolvedYtId}?start=${startSec}&end=${endSec}&autoplay=0&rel=0`

                  return (
                    <div style={{
                      width: '100%',
                      borderRadius: 8,
                      overflow: 'hidden',
                      background: '#090d16',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      boxShadow: '0 4px 20px rgba(239, 68, 68, 0.1)',
                    }}>
                      <div style={{
                        padding: '8px 12px',
                        background: 'rgba(239, 68, 68, 0.08)',
                        borderBottom: '1px solid rgba(239, 68, 68, 0.2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 600, color: '#f87171' }}>
                          <Video size={14} />
                          <span>YouTube Stream Preview</span>
                          <span className="badge badge-purple" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.3)', fontSize: '0.7rem', padding: '1px 6px' }}>YouTube Embed</span>
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          Window: {formatTime(activePreviewCandidate.start)} → {formatTime(activePreviewCandidate.end)}
                        </span>
                      </div>
                      <iframe
                        key={`${resolvedYtId}-${activePreviewCandidate.rank}-${startSec}-${endSec}`}
                        src={embedUrl}
                        title={`YouTube Preview ${activePreviewCandidate.rank}`}
                        style={{
                          width: '100%',
                          minHeight: 240,
                          aspectRatio: '16 / 9',
                          border: 'none',
                          display: 'block',
                          background: '#000',
                        }}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                      />
                      <div style={{
                        padding: '6px 12px',
                        background: 'rgba(15, 23, 42, 0.85)',
                        borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '0.72rem',
                        color: 'var(--text-dim)',
                      }}>
                        <span>Local video not yet downloaded (Phase 2 Ingest). Playing stream embed.</span>
                        <button
                          style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', fontSize: '0.72rem', textDecoration: 'underline' }}
                          onClick={() => setPreferAudioPreview(true)}
                        >
                          Can't play? Switch to Audio
                        </button>
                      </div>
                    </div>
                  )
                }

                // Fallback: Seekable Source Audio player
                const audioSrc = project.audio_url || getProjectAudioUrl(project.id)
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
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        <span>Candidate Awaiting {aspectLabel} Render</span>
                        <span className="badge badge-amber" style={{ fontSize: '0.7rem', padding: '1px 6px' }}>Audio Fallback</span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        Source Window: <strong>{formatTime(activePreviewCandidate.start)} → {formatTime(activePreviewCandidate.end)}</strong> ({activePreviewCandidate.duration.toFixed(1)}s)
                      </div>
                    </div>

                    {/* Source Audio Preview snippet */}
                    <div style={{ width: '100%', maxWidth: 320, marginTop: 2 }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                        <Play size={11} /> Source Audio Snippet (HTTP 206)
                      </div>
                      <audio
                        ref={audioRef}
                        controls
                        preload="metadata"
                        src={`${audioSrc}#t=${activePreviewCandidate.start.toFixed(1)},${activePreviewCandidate.end.toFixed(1)}`}
                        style={{ width: '100%', height: 32 }}
                      />
                    </div>

                    {resolvedYtId && (
                      <button
                        className="btn btn-secondary"
                        onClick={() => {
                          setPreferAudioPreview(false)
                          setSourceVideoError(false)
                        }}
                        style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 6 }}
                      >
                        <Video size={13} color="#f87171" />
                        <span>Switch to YouTube Video Preview</span>
                      </button>
                    )}

                    <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', background: 'rgba(255,255,255,0.04)', padding: '6px 12px', borderRadius: 4, maxWidth: 320 }}>
                      Select this candidate and click <strong>Render Selected Shorts</strong> below to produce {aspectLabel} video with subtitles & effects.
                    </div>
                  </div>
                )
              })()}

              {/* Quick Decision Context Box */}
              {(() => {
                const activeCid = activePreviewCandidate.candidate_id || activePreviewCandidate.rank
                const isSelected = selectedIds.includes(activeCid)
                return (
                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    padding: 12,
                    borderRadius: 8,
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                  }}>
                    {/* Primary Select Toggle Button */}
                    <button
                      className={`btn ${isSelected ? 'btn-secondary' : 'btn-primary'}`}
                      onClick={() => toggleSelect(activeCid)}
                      style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 8,
                        fontWeight: 600,
                        padding: '10px 14px',
                        background: isSelected ? 'rgba(34, 197, 94, 0.15)' : undefined,
                        borderColor: isSelected ? 'rgba(34, 197, 94, 0.5)' : undefined,
                        color: isSelected ? 'var(--accent-green)' : undefined,
                      }}
                    >
                      {isSelected ? <Check size={16} /> : <Plus size={16} />}
                      <span>{isSelected ? `Selected for ${aspectLabel} Rendering` : `Select for ${aspectLabel} Rendering`}</span>
                    </button>

                    {/* Metadata & Event Chips */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                      {activePreviewCandidate.duration_tier && (
                        <span className="badge badge-cyan" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.72rem' }}>
                          <Clock size={11} />
                          {activePreviewCandidate.duration_tier.toUpperCase()}
                        </span>
                      )}
                      {activePreviewCandidate.gameplay_event && (
                        <span className="badge badge-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.72rem' }}>
                          <Sparkles size={11} />
                          {activePreviewCandidate.gameplay_event.replace(/_/g, ' ')}
                        </span>
                      )}
                      {activePreviewCandidate.gameplay_events && activePreviewCandidate.gameplay_events.length > 0 && activePreviewCandidate.gameplay_events.map((ev: any, idx: number) => {
                        const evName = typeof ev === 'string' ? ev : (ev.event_type || ev.name || JSON.stringify(ev))
                        return (
                          <span key={idx} className="badge badge-purple" style={{ fontSize: '0.7rem' }}>
                            {evName}
                          </span>
                        )
                      })}
                      {activePreviewCandidate.ranking_reasons && activePreviewCandidate.ranking_reasons.map((reason: string, idx: number) => (
                        <span key={idx} style={{ fontSize: '0.7rem', color: 'var(--text-dim)', background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: 4 }}>
                          {reason}
                        </span>
                      ))}
                    </div>

                    {/* Spoken Transcript Excerpt */}
                    {activePreviewCandidate.transcript_excerpt && (
                      <div style={{
                        background: 'rgba(0, 0, 0, 0.3)',
                        borderRadius: 6,
                        padding: '8px 10px',
                        borderLeft: '3px solid var(--accent-primary)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem', color: 'var(--text-dim)', fontWeight: 600 }}>
                          <MessageSquare size={12} color="var(--accent-primary)" />
                          <span>Spoken In This Moment:</span>
                        </div>
                        <div style={{ fontSize: '0.78rem', color: '#e2e8f0', fontStyle: 'italic', lineHeight: 1.4 }}>
                          "{activePreviewCandidate.transcript_excerpt}"
                        </div>
                      </div>
                    )}

                    {/* Local LLM AI Judge Insight */}
                    {activePreviewCandidate.semantic_audit?.enabled && (
                      <div style={{
                        background: activePreviewCandidate.semantic_audit.is_filler ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.08)',
                        borderRadius: 6,
                        padding: '8px 10px',
                        border: `1px solid ${activePreviewCandidate.semantic_audit.is_filler ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.25)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem', fontWeight: 700, color: activePreviewCandidate.semantic_audit.is_filler ? '#f87171' : 'var(--accent-green)' }}>
                            <Bot size={13} />
                            <span>AI Judge Verdict:</span>
                          </div>
                          {activePreviewCandidate.semantic_audit.is_filler ? (
                            <span className="badge badge-amber" style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', fontSize: '0.68rem', padding: '1px 5px' }}>
                              Potential Filler
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                              Hook: {activePreviewCandidate.semantic_audit.hook_score ?? '--'} • Payoff: {activePreviewCandidate.semantic_audit.entertainment_score ?? '--'}
                            </span>
                          )}
                        </div>
                        {activePreviewCandidate.semantic_audit.verdict && (
                          <div style={{ fontSize: '0.76rem', color: 'var(--text-main)', lineHeight: 1.35 }}>
                            {activePreviewCandidate.semantic_audit.verdict}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Scene Analyzer Warning */}
                    {activePreviewCandidate.scene_warning && (
                      <div style={{
                        background: 'rgba(245, 158, 11, 0.1)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        borderRadius: 6,
                        padding: '6px 10px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontSize: '0.73rem',
                        color: 'var(--accent-amber)',
                      }}>
                        <AlertTriangle size={13} />
                        <span>{activePreviewCandidate.scene_warning}</span>
                      </div>
                    )}
                  </div>
                )
              })()}

              {/* Auto-Generated Description & Tags (if candidate is already rendered/packaged) */}
              {(() => {
                const candId = activePreviewCandidate.candidate_id || activePreviewCandidate.rank
                const matchingPkg = project.published_packages?.find((p) => p.candidate_id === candId)
                if (!matchingPkg?.description) return null

                return (
                  <div style={{
                    background: 'rgba(0,0,0,0.3)',
                    padding: 12,
                    borderRadius: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    border: '1px solid rgba(255,255,255,0.08)'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>
                        <FileText size={14} color="var(--accent-primary)" />
                        Auto-Generated Description
                      </div>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '2px 8px', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: 4 }}
                        onClick={() => {
                          if (matchingPkg.description) {
                            navigator.clipboard.writeText(matchingPkg.description)
                            setCopiedDescId(candId)
                            setTimeout(() => setCopiedDescId(null), 2000)
                          }
                        }}
                      >
                        {copiedDescId === candId ? <Check size={12} color="var(--accent-green)" /> : <Copy size={12} />}
                        {copiedDescId === candId ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                    <div style={{
                      fontSize: '0.78rem',
                      color: 'var(--text-dim)',
                      whiteSpace: 'pre-wrap',
                      maxHeight: isDescExpanded ? 'none' : 80,
                      overflow: 'hidden',
                      lineHeight: 1.4,
                    }}>
                      {matchingPkg.description}
                    </div>
                    {matchingPkg.description.length > 120 && (
                      <button
                        style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', fontSize: '0.72rem', cursor: 'pointer', textAlign: 'left', padding: 0 }}
                        onClick={() => setIsDescExpanded(!isDescExpanded)}
                      >
                        {isDescExpanded ? 'Show less' : 'Show more...'}
                      </button>
                    )}
                    {matchingPkg.hashtags && matchingPkg.hashtags.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 2 }}>
                        {matchingPkg.hashtags.map((tag: string, idx: number) => (
                          <span key={idx} style={{ fontSize: '0.7rem', background: 'rgba(99,102,241,0.15)', color: 'var(--accent-primary)', padding: '2px 6px', borderRadius: 4 }}>
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
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
                {selectedIds.includes(activePreviewCandidate.rank || activePreviewCandidate.candidate_id) ? 'Deselect Candidate' : `Select for ${aspectLabel} Rendering`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Render Confirmation Modal */}
      <ConfirmDialog
        isOpen={isRenderConfirmOpen}
        title="Render Selected Shorts?"
        message={`You have selected ${selectedIds.length} candidate moments. The pipeline will render ${aspectLabel} video with NVENC hardware acceleration, burn karaoke subtitles & emojis, apply context-aware effects, mix gaming SFX, and assemble complete publishing packages.`}
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
