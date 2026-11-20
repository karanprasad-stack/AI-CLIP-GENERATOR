import React, { useState } from 'react'
import { X, Video, Radio, Sparkles, Sliders, Info } from 'lucide-react'
import type { ProcessingSettings, SourceType } from '../types'

interface NewProjectModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (url: string, settings: ProcessingSettings, title?: string, sourceType?: SourceType) => void
  defaultSettings: ProcessingSettings
  isSubmitting: boolean
}

function isValidStreamUrl(input: string, sourceType: SourceType): boolean {
  const trimmed = input.trim()
  if (!trimmed) return false
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return false
  if (sourceType === 'live_stream') {
    // Live streams accept YouTube (watch, live, @channel), Twitch, Kick, or direct .m3u8
    const lower = trimmed.toLowerCase()
    return (
      lower.includes('youtube.com') ||
      lower.includes('youtu.be') ||
      lower.includes('twitch.tv') ||
      lower.includes('kick.com') ||
      lower.includes('.m3u8')
    )
  }
  const ytRegex = /(?:v=|\/|youtu\.be\/|shorts\/)([0-9A-Za-z_-]{11})/
  return ytRegex.test(trimmed) || trimmed.includes('youtube.com') || trimmed.includes('youtu.be')
}

export const NewProjectModal: React.FC<NewProjectModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  defaultSettings,
  isSubmitting,
}) => {
  const [sourceType, setSourceType] = useState<SourceType>('normal_video')
  const [url, setUrl] = useState('')
  const [projectName, setProjectName] = useState('')
  const [settings, setSettings] = useState<ProcessingSettings>(defaultSettings)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [urlTouched, setUrlTouched] = useState(false)

  if (!isOpen) return null

  const isUrlValid = isValidStreamUrl(url, sourceType)

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        setUrl(text.trim())
        setUrlTouched(true)
      }
    } catch {
      // clipboard permission denied
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setUrlTouched(true)
    if (!isUrlValid) return

    onSubmit(url.trim(), settings, projectName.trim() || undefined, sourceType)
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      padding: 16,
    }}>
      <div className="card card-glow animate-modal-in" style={{
        maxWidth: 720,
        width: '100%',
        maxHeight: '94vh',
        overflowY: 'auto',
        background: '#0D1322',
        border: '1px solid var(--border-color)',
        padding: 28,
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#050b14',
            }}>
              <Video size={22} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 800 }}>Create New Shorts Project</h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Automated gaming moment detection & 9:16 Shorts cropping</p>
            </div>
          </div>
          <button className="btn btn-secondary" onClick={onClose} style={{ padding: 6, borderRadius: '50%' }}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Dual Source Mode Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 8 }}>
              Source Type
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <button
                type="button"
                onClick={() => setSourceType('normal_video')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: sourceType === 'normal_video' ? '1.5px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                  background: sourceType === 'normal_video' ? 'rgba(0, 242, 254, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  color: sourceType === 'normal_video' ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                }}
              >
                <Video size={18} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem', color: sourceType === 'normal_video' ? 'var(--text-main)' : 'var(--text-muted)' }}>
                    Normal Video
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Standard VOD & Long-Stream Processing
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setSourceType('live_stream')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: sourceType === 'live_stream' ? '1.5px solid var(--accent-red)' : '1px solid var(--border-color)',
                  background: sourceType === 'live_stream' ? 'rgba(255, 75, 75, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  color: sourceType === 'live_stream' ? 'var(--accent-red)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ position: 'relative' }}>
                  <Radio size={18} />
                  <span style={{
                    position: 'absolute',
                    top: -2,
                    right: -2,
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: '#ff4444',
                    animation: 'pulse 1.5s infinite',
                  }} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem', color: sourceType === 'live_stream' ? 'var(--text-main)' : 'var(--text-muted)' }}>
                    Live Stream
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Continuous Rolling Capture & Live Detection
                  </div>
                </div>
              </button>
            </div>
          </div>

          {/* Main URL Input */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                {sourceType === 'live_stream' ? 'YouTube Live Stream URL' : 'YouTube Video or Livestream URL'}{' '}
                <span style={{ color: sourceType === 'live_stream' ? 'var(--accent-red)' : 'var(--accent-cyan)' }}>*</span>
              </label>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                {sourceType === 'live_stream' ? 'Rolling capture in 90s segments' : 'Supports 15–180s clips & 4–6+ hour streams'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="input-text"
                placeholder={sourceType === 'live_stream' ? 'https://youtube.com/live/... or twitch.tv/... or direct .m3u8' : 'https://www.youtube.com/watch?v=EdtUDpqjltA or youtu.be/...'}
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  setUrlTouched(true)
                }}
                autoFocus
                style={{
                  borderColor: urlTouched && !isUrlValid && url ? 'var(--accent-red)' : undefined,
                }}
              />
              <button type="button" className="btn btn-secondary" onClick={handlePaste} style={{ whiteSpace: 'nowrap' }}>
                Paste
              </button>
            </div>

            {urlTouched && !isUrlValid && url && (
              <div style={{ color: 'var(--accent-red)', fontSize: '0.8rem', marginTop: 6 }}>
                {sourceType === 'live_stream'
                  ? 'Please provide a valid live stream URL (YouTube /live/, Twitch, Kick, or direct .m3u8)'
                  : 'Please provide a valid YouTube URL (e.g. https://www.youtube.com/watch?v=...)'}
              </div>
            )}
          </div>

          {/* Optional Project Name */}
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
              Project Name <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>(Optional — automatically generated from title if empty)</span>
            </label>
            <input
              type="text"
              className="input-text"
              placeholder="e.g. CS:GO Clutch Highlights Vol. 1"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
          </div>

          {/* Duration & Shorts Count Controls */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {/* Duration Preset */}
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                Clip Duration Preset
              </label>
              <select
                className="select"
                style={{ width: '100%' }}
                value={settings.duration_mode}
                onChange={(e) => {
                  const mode = e.target.value as any
                  let minD = 15
                  let maxD = 180
                  if (mode === '15_30') { minD = 15; maxD = 30 }
                  else if (mode === '30_60') { minD = 30; maxD = 60 }
                  else if (mode === '60_180') { minD = 60; maxD = 180 }
                  setSettings({ ...settings, duration_mode: mode, min_duration: minD, max_duration: maxD })
                }}
              >
                <option value="auto">Adaptive Range (15–180s)</option>
                <option value="15_30">Quick & Punchy (15–30s)</option>
                <option value="30_60">Standard Shorts (30–60s)</option>
                <option value="60_180">Extended Story (60–180s)</option>
                <option value="custom">Custom Duration...</option>
              </select>
            </div>

            {/* Shorts Count Mode */}
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                Number of Shorts
              </label>
              <select
                className="select"
                style={{ width: '100%' }}
                value={settings.num_shorts_mode}
                onChange={(e) => setSettings({ ...settings, num_shorts_mode: e.target.value as any })}
              >
                <option value="auto">Auto (Quality-Gated Best Moments)</option>
                <option value="custom">Target Count ({settings.num_shorts} Shorts)</option>
              </select>
            </div>
          </div>

          {/* Custom Duration Inputs if selected */}
          {settings.duration_mode === 'custom' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, background: 'rgba(0,0,0,0.25)', padding: 12, borderRadius: 8 }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Min Duration (seconds)</label>
                <input
                  type="number"
                  min={15}
                  max={settings.max_duration}
                  className="input-text"
                  value={settings.min_duration}
                  onChange={(e) => setSettings({ ...settings, min_duration: parseInt(e.target.value) || 15 })}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Max Duration (seconds)</label>
                <input
                  type="number"
                  min={settings.min_duration}
                  max={180}
                  className="input-text"
                  value={settings.max_duration}
                  onChange={(e) => setSettings({ ...settings, max_duration: parseInt(e.target.value) || 180 })}
                />
              </div>
            </div>
          )}

          {/* Helper notice regarding quality threshold */}
          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            background: 'rgba(0, 242, 254, 0.05)',
            border: '1px solid rgba(0, 242, 254, 0.15)',
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: '0.8rem',
            color: '#93c5fd',
          }}>
            <Info size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <strong>Quality-First Engine:</strong> The AI evaluates combat lexical density, audio volume spikes, and climax causality. If a video does not have enough high-scoring moments, only genuinely strong candidates are recommended.
            </div>
          </div>

          {/* Subtitles & Hinglish Pipeline */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Subtitle Language Mode</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={settings.captions}
                  onChange={(e) => setSettings({ ...settings, captions: e.target.checked })}
                />
                <span>Enable Subtitles</span>
              </label>
            </div>

            {settings.captions && (
              <select
                className="select"
                style={{ width: '100%' }}
                value={settings.subtitle_language}
                onChange={(e) => setSettings({ ...settings, subtitle_language: e.target.value as any })}
              >
                <option value="auto">Auto Detect Video Speech</option>
                <option value="hinglish">Hinglish (Roman Hindi + English Gaming)</option>
                <option value="original">Original Transcription Only</option>
                <option value="english">English (Global)</option>
                <option value="hindi">Hindi (Devanagari)</option>
              </select>
            )}

            {settings.subtitle_language === 'hinglish' && settings.captions && (
              <div style={{ fontSize: '0.75rem', color: '#c084fc', marginTop: 4 }}>
                Hinglish mode normalizes natural mixed speech into Roman Hindi (e.g. <em>"Bhai ye clutch kaise kiya?! 💀"</em>) while preserving original audio transcription.
              </div>
            )}
          </div>

          {/* Advanced Pipeline Collapsible */}
          <div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{ width: '100%', justifyContent: 'space-between' }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sliders size={16} />
                <span>{showAdvanced ? 'Hide Advanced Options' : 'Show Layout, Audio & Effects Settings'}</span>
              </span>
              <span>{showAdvanced ? '▲' : '▼'}</span>
            </button>

            {showAdvanced && (
              <div style={{
                marginTop: 12,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 12,
                background: 'rgba(0,0,0,0.25)',
                padding: 16,
                borderRadius: 8,
                border: '1px solid var(--border-color)',
              }}>
                {/* Game / Content Mode */}
                <div style={{ gridColumn: 'span 2' }}>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    Game Intelligence Mode
                  </label>
                  <select
                    className="select"
                    style={{ width: '100%' }}
                    value={settings.game_mode || 'auto'}
                    onChange={(e) => setSettings({ ...settings, game_mode: e.target.value as any })}
                  >
                    <option value="auto">Auto-Detect Game & Genre (Recommended)</option>
                    <option value="story_open_world">Story & Open-World (GTA VI/V, RDR2, Cyberpunk, Elden Ring)</option>
                    <option value="horror_survival">Horror & Survival (Resident Evil, Phasmophobia, Lethal Company)</option>
                    <option value="valorant">Competitive FPS — Valorant (Kill-feed & Round CV)</option>
                    <option value="competitive_fps">Competitive FPS — General (CS2, Apex, CoD, Fortnite)</option>
                    <option value="generic">Generic / Variety Gaming</option>
                  </select>
                </div>

                {/* Frame Aspect Ratio Selection */}
                <div style={{ gridColumn: 'span 2' }}>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                    Render Frame Aspect Ratio
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <button
                      type="button"
                      className={`btn ${settings.aspect_ratio !== '1:1' ? 'btn-primary' : 'btn-secondary'}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'flex-start',
                        gap: 12,
                        padding: '12px 14px',
                        borderRadius: 10,
                      }}
                      onClick={() => setSettings({ ...settings, aspect_ratio: '9:16', resolution: '1080x1920' })}
                    >
                      <div style={{
                        width: 14,
                        height: 24,
                        border: '2px solid currentColor',
                        borderRadius: 3,
                        opacity: 0.9,
                        flexShrink: 0,
                      }} />
                      <div style={{ textAlign: 'left' }}>
                        <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>9:16 Vertical</div>
                        <div style={{ fontSize: '0.7rem', opacity: 0.8 }}>1080×1920 • Shorts/Reels/TikTok</div>
                      </div>
                    </button>

                    <button
                      type="button"
                      className={`btn ${settings.aspect_ratio === '1:1' ? 'btn-primary' : 'btn-secondary'}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'flex-start',
                        gap: 12,
                        padding: '12px 14px',
                        borderRadius: 10,
                      }}
                      onClick={() => setSettings({ ...settings, aspect_ratio: '1:1', resolution: '1080x1080' })}
                    >
                      <div style={{
                        width: 18,
                        height: 18,
                        border: '2px solid currentColor',
                        borderRadius: 3,
                        opacity: 0.9,
                        flexShrink: 0,
                      }} />
                      <div style={{ textAlign: 'left' }}>
                        <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>1:1 Square</div>
                        <div style={{ fontSize: '0.7rem', opacity: 0.8 }}>1080×1080 • Square Feed/Clips</div>
                      </div>
                    </button>
                  </div>
                </div>

                {/* 9:16 Layout Strategy */}
                <div style={{ gridColumn: 'span 2' }}>
                  <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                    Framing / Cropping Strategy
                  </label>
                  <select
                    className="select"
                    style={{ width: '100%' }}
                    value={settings.layout}
                    onChange={(e) => setSettings({ ...settings, layout: e.target.value as any })}
                  >
                    <option value="auto">Auto Adaptive Framing</option>
                    <option value="smart_crop">Smart Center Crop</option>
                    <option value="blurred_background">Blurred Background Pillarbox</option>
                    <option value="facecam_gameplay">Facecam Top + Gameplay Bottom</option>
                  </select>
                </div>

                {/* Kill-Feed PIP Overlay for 9:16 */}
                {settings.aspect_ratio !== '1:1' && (
                  <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.03)', padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Kill-Feed PIP (9:16 FPS)</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          Overlays top-right kill & headshot confirmations on 9:16 center-cropped FPS video
                        </div>
                      </div>
                      <select
                        className="select"
                        style={{ width: '130px', padding: '4px 8px', fontSize: '0.8rem' }}
                        value={settings.kill_feed_overlay || 'auto'}
                        onChange={(e) => setSettings({ ...settings, kill_feed_overlay: e.target.value as any })}
                      >
                        <option value="auto">Auto (FPS Only)</option>
                        <option value="on">Always On</option>
                        <option value="off">Off</option>
                      </select>
                    </div>
                  </div>
                )}

                <label className="toggle-label">
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Contextual Emojis</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Burn dynamic reaction emojis</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.emoji}
                    onChange={(e) => setSettings({ ...settings, emoji: e.target.checked })}
                  />
                </label>

                <label className="toggle-label">
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Smart Visual Effects</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Climax zoom, shake & flash</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.effects}
                    onChange={(e) => setSettings({ ...settings, effects: e.target.checked })}
                  />
                </label>

                <label className="toggle-label">
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Gaming SFX Mixing</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Whooshes & impacts on cuts</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.sfx}
                    onChange={(e) => setSettings({ ...settings, sfx: e.target.checked })}
                  />
                </label>

                <label className="toggle-label">
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Speech-Aware Ducking</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Lowers game volume during dialogue</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.ducking}
                    onChange={(e) => setSettings({ ...settings, ducking: e.target.checked })}
                  />
                </label>
              </div>
            )}
          </div>

          {/* Configuration Summary Badge */}
          <div style={{
            background: 'rgba(0,0,0,0.3)',
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: '0.78rem',
            border: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
          }}>
            <span style={{ color: 'var(--text-dim)' }}>Configuration Summary:</span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span className="badge badge-cyan">{settings.min_duration}–{settings.max_duration}s</span>
              <span className="badge badge-purple">{settings.num_shorts_mode === 'auto' ? 'Auto Quota' : `${settings.num_shorts} Shorts`}</span>
              <span className="badge badge-green">{settings.aspect_ratio === '1:1' ? '1080×1080 60FPS (1:1)' : '1080×1920 60FPS (9:16)'}</span>
              <span className="badge badge-amber">{settings.subtitle_language.toUpperCase()}</span>
            </div>
          </div>

          {/* Submit Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || !url.trim()}
              style={{ padding: '10px 26px', fontSize: '0.95rem' }}
            >
              <Sparkles size={18} />
              <span>{isSubmitting ? 'Starting Analysis...' : 'Analyze Video'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
