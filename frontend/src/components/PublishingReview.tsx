import React, { useState, useEffect } from 'react'
import {
  Download, RefreshCw, Check, Film, Image as ImageIcon, FileText, ArrowLeft,
  Tag, Key, AlertTriangle, ShieldCheck, Sliders, Copy, Sparkles, UploadCloud,
  ExternalLink, CheckCircle2, History
} from 'lucide-react'
import type { ProjectDetail, PlatformStatus, PublishResult, PublishHistoryEntry } from '../types'
import {
  getFileUrl, getPackageDownloadUrl, updateMetadata, regenerateMetadata, getOutputDetail,
  fetchPublishingPlatforms, publishCandidate, fetchCandidatePublishHistory
} from '../api/client'
import { TimelineEditor } from './TimelineEditor/TimelineEditor'
import { ConfirmDialog } from './ui/ConfirmDialog'

interface PublishingReviewProps {
  project: ProjectDetail
  onBackToHistory: () => void
  onViewCandidates?: () => void
}

export const PublishingReview: React.FC<PublishingReviewProps> = ({
  project,
  onBackToHistory,
  onViewCandidates,
}) => {
  const packages = project.published_packages || []
  const [selectedIdx, setSelectedIdx] = useState(0)
  const activePackage = packages[selectedIdx] || null

  // Local editing states
  const [title, setTitle] = useState(activePackage?.title || '')
  const [titleAlternatives, setTitleAlternatives] = useState<string[]>([])
  const [description, setDescription] = useState(activePackage?.description || '')
  const [hashtags, setHashtags] = useState<string[]>(activePackage?.hashtags || [])
  const [keywords, setKeywords] = useState<string[]>(activePackage?.keywords || [])
  const [newTagInput, setNewTagInput] = useState('')
  const [newKeywordInput, setNewKeywordInput] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [isTimelineOpen, setIsTimelineOpen] = useState(false)
  const [copiedDesc, setCopiedDesc] = useState(false)

  // Publishing states (Phase 13)
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([])
  const [selectedPlatform, setSelectedPlatform] = useState<string>('youtube')
  const [publishPrivacy, setPublishPrivacy] = useState<string>('private')
  const [scheduledAt, setScheduledAt] = useState<string>('')
  const [isDryRun, setIsDryRun] = useState<boolean>(true)
  const [isPublishing, setIsPublishing] = useState<boolean>(false)
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null)
  const [publishHistory, setPublishHistory] = useState<PublishHistoryEntry[]>([])
  const [isConfirmOpen, setIsConfirmOpen] = useState<boolean>(false)
  const [confirmTitle, setConfirmTitle] = useState<string>('')
  const [confirmMsg, setConfirmMsg] = useState<string>('')
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)

  useEffect(() => {
    fetchPublishingPlatforms()
      .then((data) => {
        setPlatforms(data)
        const yt = data.find((p) => p.platform === 'youtube')
        if (yt && !yt.connected) {
          setIsDryRun(true)
        }
      })
      .catch(() => {})
  }, [])

  const loadHistory = (cid: number) => {
    fetchCandidatePublishHistory(project.id, cid)
      .then((hist) => setPublishHistory(hist))
      .catch(() => {})
  }

  const handlePublishClick = () => {
    if (!activePackage) return

    // 1. Check if public upload
    if (!isDryRun && publishPrivacy === 'public') {
      setConfirmTitle('Confirm Public Upload')
      setConfirmMsg(`You are about to publish Short #${activePackage.candidate_id} as PUBLIC on ${selectedPlatform.toUpperCase()}. It will immediately be visible to your audience. Proceed?`)
      setPendingAction(() => executePublish)
      setIsConfirmOpen(true)
      return
    }

    // 2. Check if already published
    const already = publishHistory.some(
      (h) => h.platform === selectedPlatform && h.success && !h.dry_run && (h.status === 'published' || h.status === 'scheduled')
    )
    if (!isDryRun && already) {
      setConfirmTitle('Duplicate Upload Warning')
      setConfirmMsg(`Short #${activePackage.candidate_id} has already been published to ${selectedPlatform.toUpperCase()}. Do you want to re-upload it?`)
      setPendingAction(() => executePublish)
      setIsConfirmOpen(true)
      return
    }

    executePublish()
  }

  const executePublish = async () => {
    if (!activePackage) return
    setIsPublishing(true)
    setPublishResult(null)
    try {
      const isSquareVid = (activePackage as any)?.aspect_ratio === '1:1' || project.settings?.aspect_ratio === '1:1'
      const res = await publishCandidate(project.id, activePackage.candidate_id, {
        platform: selectedPlatform,
        title,
        description,
        hashtags,
        privacy: publishPrivacy,
        scheduled_publish_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        upload_thumbnail: true,
        dry_run: isDryRun,
        aspect_ratio: isSquareVid ? '1:1' : '9:16',
      })
      setPublishResult(res)
      loadHistory(activePackage.candidate_id)
    } catch (err: any) {
      setPublishResult({
        success: false,
        platform: selectedPlatform,
        status: 'failed',
        message: err.message || 'Publishing failed.',
        timestamp: new Date().toISOString(),
        dry_run: isDryRun,
      })
    } finally {
      setIsPublishing(false)
    }
  }

  // Sync when active candidate tab changes
  React.useEffect(() => {
    if (activePackage) {
      setTitle(activePackage.title || '')
      setDescription(activePackage.description || '')
      setHashtags(activePackage.hashtags || [])
      setKeywords(activePackage.keywords || [])
      setSaveSuccess(false)
      setTitleAlternatives([])
      loadHistory(activePackage.candidate_id)
      setPublishResult(null)

      // Fetch package details for alternative titles, full description, and tags
      getOutputDetail(project.id, activePackage.candidate_id)
        .then((detail) => {
          if (detail?.title?.alternatives && Array.isArray(detail.title.alternatives)) {
            setTitleAlternatives(detail.title.alternatives)
          }
          if (detail?.publishing?.description && !activePackage.description) {
            setDescription(detail.publishing.description)
          }
          if (detail?.publishing?.hashtags && (!activePackage.hashtags || activePackage.hashtags.length === 0)) {
            setHashtags(detail.publishing.hashtags)
          }
          if (detail?.publishing?.keywords && (!activePackage.keywords || activePackage.keywords.length === 0)) {
            setKeywords(detail.publishing.keywords)
          }
        })
        .catch(() => {
          // ignore network/fallback errors
        })
    }
  }, [selectedIdx, activePackage, project.id])

  if (packages.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '60px 20px' }}>
        <h3>No Rendered Shorts Found</h3>
        <p style={{ color: 'var(--text-muted)', marginTop: 8 }}>This project does not have any rendered Shorts yet.</p>
        <button className="btn btn-secondary" onClick={onBackToHistory} style={{ marginTop: 16 }}>
          Back to Projects
        </button>
      </div>
    )
  }

  const handleSave = async () => {
    if (!activePackage) return
    setIsSaving(true)
    try {
      await updateMetadata(project.id, activePackage.candidate_id, {
        title,
        description,
        hashtags,
        keywords,
      })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch {
      alert('Failed to save metadata updates.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleRegenerate = async () => {
    if (!activePackage) return
    setIsRegenerating(true)
    try {
      const res = await regenerateMetadata(project.id, activePackage.candidate_id)
      if (res?.metadata) {
        setTitle(res.metadata.title?.selected || title)
        setDescription(res.metadata.description || description)
        setHashtags(res.metadata.hashtags || hashtags)
        setKeywords(res.metadata.keywords || keywords)
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 3000)
      }
    } catch {
      alert('Failed to regenerate metadata.')
    } finally {
      setIsRegenerating(false)
    }
  }

  const handleAddTag = () => {
    if (!newTagInput.trim()) return
    const formatted = newTagInput.startsWith('#') ? newTagInput.trim() : `#${newTagInput.trim()}`
    if (!hashtags.includes(formatted)) {
      setHashtags([...hashtags, formatted])
    }
    setNewTagInput('')
  }

  const handleRemoveTag = (tagToRemove: string) => {
    setHashtags(hashtags.filter((t) => t !== tagToRemove))
  }

  const handleAddKeyword = () => {
    const trimmed = newKeywordInput.trim().toLowerCase()
    if (!trimmed) return
    if (!keywords.includes(trimmed)) {
      setKeywords([...keywords, trimmed])
    }
    setNewKeywordInput('')
  }

  const handleRemoveKeyword = (keywordToRemove: string) => {
    setKeywords(keywords.filter((k) => k !== keywordToRemove))
  }

  // Quality checks & warnings
  const isTitleLengthValid = title.length >= 20 && title.length <= 70
  const isDescLengthValid = description.length >= 40 && description.length <= 500
  const hasAttribution = description.toLowerCase().includes('original video') || 
                         description.toLowerCase().includes('youtube.com') || 
                         description.toLowerCase().includes('credit') ||
                         description.toLowerCase().includes(project.uploader.toLowerCase())

  const videoUrl = getFileUrl(project.id, `publishing/candidate_${activePackage.candidate_id.toString().padStart(2, '0')}/final.mp4`)
  const thumbUrl = getFileUrl(project.id, `publishing/candidate_${activePackage.candidate_id.toString().padStart(2, '0')}/thumbnail.jpg`)

  const mq = activePackage.metadata_quality
  const isSquare = (activePackage as any)?.aspect_ratio === '1:1' || project.settings?.aspect_ratio === '1:1'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span className="badge badge-green">PUBLISHING READY</span>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>• {isSquare ? '1080×1080 (1:1)' : '1080×1920 (9:16)'} @ 60fps</span>
          </div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Publishing Packages & Metadata Editor
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Source: {project.title}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={onBackToHistory}>
            <ArrowLeft size={16} />
            <span>Projects</span>
          </button>
          {onViewCandidates && (
            <button className="btn btn-secondary" onClick={onViewCandidates} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Film size={16} />
              <span>Candidate Review</span>
            </button>
          )}
          {activePackage && (
            <button
              className="btn btn-secondary"
              onClick={() => setIsTimelineOpen(true)}
              style={{ borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }}
            >
              <Sliders size={16} />
              <span>Edit Short #{activePackage.candidate_id} Timeline</span>
            </button>
          )}
          <a
            className="btn btn-primary"
            href={getPackageDownloadUrl(project.id)}
            download
            style={{ textDecoration: 'none' }}
          >
            <Download size={16} />
            <span>Download All ({packages.length}) Shorts ZIP</span>
          </a>
        </div>
      </div>

      {/* Candidate Tabs Bar */}
      <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 6 }}>
        {packages.map((pkg, idx) => {
          const isSelected = idx === selectedIdx
          return (
            <button
              key={pkg.candidate_id}
              onClick={() => setSelectedIdx(idx)}
              className={`btn ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '8px 16px', whiteSpace: 'nowrap' }}
            >
              <span>Short #{pkg.candidate_id}</span>
              <span className="badge badge-cyan" style={{ fontSize: '0.7rem', padding: '1px 5px', background: 'rgba(0,0,0,0.3)' }}>
                Q: {pkg.quality_score.toFixed(2)}
              </span>
            </button>
          )
        })}
      </div>

      {/* Main 2-Column Workspace: Video Player Left, Metadata Editor Right */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 420px) minmax(0, 1fr)', gap: 28, alignItems: 'start' }}>
        {/* Left Column: Vertical 9:16 Shorts Player & Thumbnail Preview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Vertical Video Card */}
          <div className="card card-glow" style={{ padding: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>9:16 Vertical Preview</span>
              <span className="badge badge-purple">BURNED SUBTITLES</span>
            </div>

            <div style={{
              width: '100%',
              borderRadius: 8,
              overflow: 'hidden',
              background: '#000',
              aspectRatio: isSquare ? '1 / 1' : '9 / 16',
              maxHeight: 520,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <video
                controls
                src={videoUrl}
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              >
                Your browser does not support vertical video preview.
              </video>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
              <a
                className="btn btn-secondary"
                href={videoUrl}
                download={`short_${activePackage.candidate_id}.mp4`}
                style={{ flex: 1, textDecoration: 'none' }}
              >
                <Film size={15} />
                <span>Download MP4</span>
              </a>
            </div>
          </div>

          {/* Thumbnail Card */}
          <div className="card" style={{ padding: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>1280×720 Thumbnail</span>
              <span className="badge badge-green">Score: {activePackage.thumbnail_score.toFixed(2)}</span>
            </div>
            <img
              src={thumbUrl}
              alt="Thumbnail"
              style={{ width: '100%', borderRadius: 8, aspectRatio: '16 / 9', objectFit: 'cover' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                Frame: {activePackage.thumbnail_timestamp.toFixed(2)}s
              </span>
              <a
                className="btn btn-secondary"
                href={thumbUrl}
                download={`thumbnail_${activePackage.candidate_id}.jpg`}
                style={{ padding: '5px 12px', fontSize: '0.75rem', textDecoration: 'none' }}
              >
                <ImageIcon size={14} />
                <span>Download JPG</span>
              </a>
            </div>
          </div>

          {/* Phase 7E Creator Quality Audit Widget */}
          {activePackage.publishability ? (
            <div className="card" style={{ padding: 14, background: '#090d14', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ShieldCheck size={16} color="var(--accent-green)" />
                  <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>Creator Quality Audit</span>
                </div>
                <span className={`badge ${activePackage.publishability.recommendation === 'publish' ? 'badge-green' : (activePackage.publishability.recommendation === 'review' ? 'badge-amber' : 'badge-red')}`}>
                  {activePackage.publishability.recommendation.toUpperCase()} • {activePackage.publishability.score.toFixed(1)}/100
                </span>
              </div>

              {activePackage.publishability.dimensions && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6, fontSize: '0.75rem', marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Moment:</span>
                    <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{activePackage.publishability.dimensions.moment.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Narrative:</span>
                    <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>{activePackage.publishability.dimensions.narrative.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Visual/Audio:</span>
                    <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>{activePackage.publishability.dimensions.presentation.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Publishing:</span>
                    <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{activePackage.publishability.dimensions.publishing.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Technical:</span>
                    <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>{activePackage.publishability.dimensions.technical.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Diversity:</span>
                    <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>{activePackage.publishability.dimensions.diversity.toFixed(0)}</span>
                  </div>
                </div>
              )}

              {activePackage.publishability.reasons && activePackage.publishability.reasons.length > 0 && (
                <div style={{ fontSize: '0.75rem', color: 'var(--accent-green)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <div>✓ {activePackage.publishability.reasons[0]}</div>
                </div>
              )}
              {activePackage.publishability.warnings && activePackage.publishability.warnings.length > 0 && (
                <div style={{ fontSize: '0.75rem', color: 'var(--accent-amber)', display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
                  <div>⚠ {activePackage.publishability.warnings[0]}</div>
                </div>
              )}
            </div>
          ) : null}

          {/* Metadata Quality Breakdown Widget */}
          {mq && (
            <div className="card" style={{ padding: 14, background: '#090d14' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Metadata Quality Audit</span>
                <span className="badge badge-green">Score: {mq.overall.toFixed(2)}</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, fontSize: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Relevance:</span>
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{mq.relevance.toFixed(2)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Specificity:</span>
                  <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>{mq.specificity.toFixed(2)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Naturalness:</span>
                  <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>{mq.naturalness.toFixed(2)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Grounding:</span>
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{mq.grounding.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Metadata Editor */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <FileText size={20} color="var(--accent-cyan)" />
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Short #{activePackage.candidate_id} Metadata</h2>
            </div>

            <button
              className="btn btn-secondary"
              onClick={handleRegenerate}
              disabled={isRegenerating}
              style={{ fontSize: '0.8rem', padding: '6px 14px' }}
            >
              <RefreshCw size={14} className={isRegenerating ? 'spin' : ''} />
              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate Metadata'}</span>
            </button>
          </div>

          {/* Title Editor */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>YouTube Shorts Title</label>
              <div style={{ display: 'flex', gap: 8, fontSize: '0.75rem', alignItems: 'center' }}>
                <span style={{ color: isTitleLengthValid ? 'var(--accent-green)' : 'var(--accent-amber)', fontWeight: 600 }}>
                  {title.length} / 70 chars
                </span>
                <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>
                  Quality: {activePackage.quality_score.toFixed(2)}
                </span>
              </div>
            </div>
            <input
              type="text"
              className="input-text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Catchy, natural, candidate-specific Shorts title"
            />
            {!isTitleLengthValid && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4, fontSize: '0.75rem', color: 'var(--accent-amber)' }}>
                <AlertTriangle size={12} />
                <span>Optimal YouTube Shorts title length is 20–70 characters for mobile viewport.</span>
              </div>
            )}

            {titleAlternatives.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Sparkles size={12} color="var(--accent-purple)" />
                  <span>AI Title Variants (Click to select):</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {titleAlternatives.map((alt, aIdx) => {
                    const isSelectedTitle = title === alt
                    return (
                      <button
                        key={aIdx}
                        type="button"
                        onClick={() => setTitle(alt)}
                        style={{
                          background: isSelectedTitle ? 'rgba(139, 92, 246, 0.16)' : 'rgba(255, 255, 255, 0.03)',
                          border: isSelectedTitle ? '1px solid rgba(139, 92, 246, 0.45)' : '1px solid var(--border-color)',
                          color: isSelectedTitle ? '#C084FC' : 'var(--text-muted)',
                          borderRadius: 6,
                          padding: '7px 12px',
                          fontSize: '0.8rem',
                          textAlign: 'left',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 8,
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <span>{alt}</span>
                        {isSelectedTitle && <Check size={14} color="#C084FC" />}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Description Editor */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Video Description & Attribution</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    if (description) {
                      navigator.clipboard.writeText(description)
                      setCopiedDesc(true)
                      setTimeout(() => setCopiedDesc(false), 2000)
                    }
                  }}
                  style={{ padding: '3px 8px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 4 }}
                >
                  {copiedDesc ? <Check size={12} color="var(--accent-green)" /> : <Copy size={12} />}
                  <span>{copiedDesc ? 'Copied!' : 'Copy Description'}</span>
                </button>
                <span style={{ fontSize: '0.75rem', color: isDescLengthValid ? 'var(--accent-green)' : 'var(--accent-amber)', fontWeight: 600 }}>
                  {description.length} / 500 chars (target 40–500)
                </span>
              </div>
            </div>
            <textarea
              className="textarea"
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ resize: 'vertical' }}
              placeholder="Engaging summary with creator attribution..."
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
              {!isDescLengthValid && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--accent-amber)' }}>
                  <AlertTriangle size={12} />
                  <span>Optimal description length is 40–500 characters.</span>
                </div>
              )}
              {hasAttribution ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--accent-green)' }}>
                  <ShieldCheck size={12} />
                  <span>Original creator attribution detected.</span>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--accent-amber)' }}>
                  <AlertTriangle size={12} />
                  <span>Notice: Creator attribution / original video link not explicitly found in description.</span>
                </div>
              )}
            </div>
          </div>

          {/* Hashtags Editor */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Tag size={15} color="var(--accent-purple)" />
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                Hashtags ({hashtags.length})
              </label>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
              {hashtags.map((tag) => (
                <span
                  key={tag}
                  className="badge badge-purple"
                  style={{ fontSize: '0.8rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <span>{tag}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(tag)}
                    style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '0.9rem', lineHeight: 1 }}
                    title="Remove tag"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="input-text"
                placeholder="Add tag (e.g. #GamingFails)"
                value={newTagInput}
                onChange={(e) => setNewTagInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddTag(); } }}
                style={{ maxWidth: 260 }}
              />
              <button type="button" className="btn btn-secondary" onClick={handleAddTag}>
                Add Tag
              </button>
            </div>
          </div>

          {/* Keywords / SEO Tags Editor */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Key size={15} color="var(--accent-cyan)" />
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                SEO Keywords ({keywords.length})
              </label>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
              {keywords.map((kw) => (
                <span
                  key={kw}
                  className="badge badge-cyan"
                  style={{ fontSize: '0.75rem', padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
                >
                  <span>{kw}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveKeyword(kw)}
                    style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '0.85rem', lineHeight: 1 }}
                    title="Remove keyword"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="input-text"
                placeholder="Add keyword (e.g. clutch ace)"
                value={newKeywordInput}
                onChange={(e) => setNewKeywordInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddKeyword(); } }}
                style={{ maxWidth: 260 }}
              />
              <button type="button" className="btn btn-secondary" onClick={handleAddKeyword}>
                Add Keyword
              </button>
            </div>
          </div>

          {/* Action Footer */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 16, borderTop: '1px solid var(--border-color)', flexWrap: 'wrap', gap: 12 }}>
            <div>
              {saveSuccess && (
                <span style={{ color: 'var(--accent-green)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={16} />
                  <span>Metadata saved successfully on disk!</span>
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <a
                className="btn btn-secondary"
                href={getPackageDownloadUrl(project.id, activePackage.candidate_id)}
                download
                style={{ textDecoration: 'none' }}
              >
                <Download size={15} />
                <span>Download Candidate #{activePackage.candidate_id} Bundle</span>
              </a>

              <button className="btn btn-primary" onClick={handleSave} disabled={isSaving}>
                <span>{isSaving ? 'Saving...' : 'Save Metadata Changes'}</span>
              </button>
            </div>
          </div>

          {/* Direct Social Publish Card (Phase 13) */}
          <div className="card card-glow" style={{ padding: 18, marginTop: 12, border: '1px solid rgba(34, 211, 238, 0.25)', background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.8) 0%, rgba(13, 19, 34, 0.95) 100%)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <UploadCloud size={18} color="var(--accent-cyan)" />
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>Direct Social Publish (Phase 13)</h3>
              </div>
              <span className="badge badge-purple" style={{ fontSize: '0.72rem' }}>Local-First Studio Layer</span>
            </div>

            {/* Platform Selection Pills */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
              {['youtube', 'tiktok', 'instagram'].map((plat) => {
                const isSel = selectedPlatform === plat
                const pInfo = platforms.find((p) => p.platform === plat)
                const isConn = pInfo?.connected || false
                const label = plat === 'youtube' ? 'YouTube Shorts' : (plat === 'tiktok' ? 'TikTok' : 'Instagram Reels')

                return (
                  <button
                    key={plat}
                    type="button"
                    onClick={() => {
                      setSelectedPlatform(plat)
                      if (!isConn) setIsDryRun(true)
                    }}
                    className={`btn ${isSel ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                      padding: '7px 14px',
                      fontSize: '0.82rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      borderColor: isSel ? undefined : (isConn ? 'rgba(34, 197, 94, 0.3)' : undefined),
                    }}
                  >
                    <span style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: isConn ? 'var(--accent-green)' : (pInfo?.configured ? 'var(--accent-cyan)' : 'var(--text-dim)'),
                      boxShadow: isConn ? '0 0 8px var(--accent-green)' : undefined,
                      display: 'inline-block',
                    }} />
                    <span>{label}</span>
                    {isConn && <span style={{ fontSize: '0.7rem', color: 'var(--accent-green)' }}>✓</span>}
                  </button>
                )
              })}
            </div>

            {/* Settings Row: Privacy & Scheduling */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-dim)', marginBottom: 6 }}>
                  Upload Privacy Level
                </label>
                <select
                  className="select"
                  value={publishPrivacy}
                  onChange={(e) => setPublishPrivacy(e.target.value)}
                  style={{ width: '100%', fontSize: '0.82rem', padding: '7px 10px' }}
                >
                  <option value="private">Private (Default / Safe)</option>
                  <option value="unlisted">Unlisted (Share via Link)</option>
                  <option value="public">Public (Immediately Visible)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-dim)', marginBottom: 6 }}>
                  Schedule Date/Time (Optional)
                </label>
                <input
                  type="datetime-local"
                  className="input-text"
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  style={{ width: '100%', fontSize: '0.82rem', padding: '6px 10px' }}
                />
              </div>
            </div>

            {/* Dry Run Checkbox Toggle */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              borderRadius: 6,
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--border-color)',
              marginBottom: 14,
            }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>
                <input
                  type="checkbox"
                  checked={isDryRun}
                  onChange={(e) => setIsDryRun(e.target.checked)}
                />
                <span>Simulate Upload (Dry Run Mode)</span>
              </label>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                {isDryRun ? 'No live network upload. Validates payload & package.' : 'Live network upload to platform.'}
              </span>
            </div>

            {/* Publish Trigger Button */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <button
                className={`btn ${isDryRun ? 'btn-secondary' : 'btn-primary'}`}
                onClick={handlePublishClick}
                disabled={isPublishing}
                style={{
                  flex: 1,
                  padding: '10px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  fontWeight: 700,
                  fontSize: '0.88rem',
                }}
              >
                <UploadCloud size={16} />
                <span>
                  {isPublishing
                    ? 'Publishing in Progress...'
                    : (isDryRun
                      ? `Simulate ${selectedPlatform === 'youtube' ? 'YouTube Shorts' : (selectedPlatform === 'tiktok' ? 'TikTok' : 'Instagram Reels')} Upload`
                      : `Publish Short #${activePackage.candidate_id} to ${selectedPlatform === 'youtube' ? 'YouTube Shorts' : (selectedPlatform === 'tiktok' ? 'TikTok' : 'Instagram Reels')}`
                    )}
                </span>
              </button>
            </div>

            {/* Publish Execution Result Alert Banner */}
            {publishResult && (
              <div style={{
                marginTop: 14,
                padding: '12px 14px',
                borderRadius: 6,
                fontSize: '0.82rem',
                background: publishResult.success ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                border: `1px solid ${publishResult.success ? 'var(--accent-green)' : '#f87171'}`,
                color: publishResult.success ? 'var(--text-main)' : '#f87171',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
                    {publishResult.success ? <CheckCircle2 size={15} color="var(--accent-green)" /> : <AlertTriangle size={15} color="#f87171" />}
                    <span>{publishResult.status.toUpperCase()}: {publishResult.message}</span>
                  </div>
                  {publishResult.remote_url && (
                    <a
                      href={publishResult.remote_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary"
                      style={{ padding: '3px 8px', fontSize: '0.74rem', display: 'flex', alignItems: 'center', gap: 4 }}
                    >
                      <ExternalLink size={12} />
                      <span>Open Link</span>
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Candidate Publish History */}
            {publishHistory.length > 0 && (
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-dim)', marginBottom: 8 }}>
                  <History size={13} />
                  <span>Publish History for Short #{activePackage.candidate_id} ({publishHistory.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {publishHistory.map((h, hIdx) => (
                    <div
                      key={hIdx}
                      style={{
                        padding: '6px 10px',
                        borderRadius: 4,
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.04)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '0.74rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="badge badge-cyan" style={{ fontSize: '0.68rem', padding: '1px 5px' }}>
                          {h.platform.toUpperCase()}
                        </span>
                        <span className={`badge ${h.status === 'published' ? 'badge-green' : (h.status === 'dry_run' ? 'badge-purple' : 'badge-amber')}`} style={{ fontSize: '0.68rem', padding: '1px 5px' }}>
                          {h.status.toUpperCase()}
                        </span>
                        <span style={{ color: 'var(--text-dim)' }}>
                          {new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                      </div>
                      {h.remote_url && (
                        <a
                          href={h.remote_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--accent-primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
                        >
                          <span>{h.remote_id}</span>
                          <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Confirmation Dialog for Public or Duplicate Uploads */}
      <ConfirmDialog
        isOpen={isConfirmOpen}
        title={confirmTitle}
        message={confirmMsg}
        confirmText="Proceed"
        cancelText="Cancel"
        isDestructive={confirmTitle.includes('Public')}
        onConfirm={() => {
          setIsConfirmOpen(false)
          if (pendingAction) {
            pendingAction()
            setPendingAction(null)
          }
        }}
        onCancel={() => {
          setIsConfirmOpen(false)
          setPendingAction(null)
        }}
      />

      {/* Phase 8 Multi-Track Timeline Editor Overlay */}
      {isTimelineOpen && activePackage && (
        <TimelineEditor
          project={project}
          candidateId={activePackage.candidate_id}
          onClose={() => setIsTimelineOpen(false)}
          onRenderSuccess={() => {
            setIsTimelineOpen(false)
            // Reload project or refresh
            window.location.reload()
          }}
        />
      )}
    </div>
  )
}

