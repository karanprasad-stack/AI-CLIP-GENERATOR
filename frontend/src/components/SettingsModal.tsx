import React, { useState, useEffect } from 'react'
import { X, Cpu, Sliders, Volume2, Subtitles, Settings, Share2, CheckCircle, AlertTriangle, RefreshCw, Key } from 'lucide-react'
import type { ProcessingSettings, PlatformStatus } from '../types'
import { fetchPublishingPlatforms, connectPlatform, disconnectPlatform } from '../api/client'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
  settings: ProcessingSettings
  onSave: (settings: ProcessingSettings) => void
}

type TabType = 'general' | 'subtitles' | 'audio' | 'hardware' | 'publishing'

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSave,
}) => {
  const [localSettings, setLocalSettings] = useState<ProcessingSettings>(settings)
  const [activeTab, setActiveTab] = useState<TabType>('general')
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([])
  const [isLoadingPlatforms, setIsLoadingPlatforms] = useState(false)
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null)
  const [platformActionMsg, setPlatformActionMsg] = useState<{ platform: string; text: string; error?: boolean } | null>(null)

  useEffect(() => {
    if (isOpen) {
      loadPlatforms()
    }
  }, [isOpen])

  const loadPlatforms = async () => {
    setIsLoadingPlatforms(true)
    try {
      const data = await fetchPublishingPlatforms()
      setPlatforms(data)
    } catch {
      // ignore
    } finally {
      setIsLoadingPlatforms(false)
    }
  }

  const handleConnect = async (platformName: string) => {
    setConnectingPlatform(platformName)
    setPlatformActionMsg(null)
    try {
      await connectPlatform(platformName)
      setPlatformActionMsg({ platform: platformName, text: 'Connected successfully!' })
      await loadPlatforms()
    } catch (err: any) {
      setPlatformActionMsg({ platform: platformName, text: err.message || 'Connection failed.', error: true })
    } finally {
      setConnectingPlatform(null)
    }
  }

  const handleDisconnect = async (platformName: string) => {
    setConnectingPlatform(platformName)
    setPlatformActionMsg(null)
    try {
      await disconnectPlatform(platformName)
      setPlatformActionMsg({ platform: platformName, text: 'Disconnected.' })
      await loadPlatforms()
    } catch (err: any) {
      setPlatformActionMsg({ platform: platformName, text: err.message || 'Disconnect failed.', error: true })
    } finally {
      setConnectingPlatform(null)
    }
  }

  if (!isOpen) return null

  const handleChange = (key: keyof ProcessingSettings, value: any) => {
    setLocalSettings((prev) => ({
      ...prev,
      [key]: value,
    }))
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0,0,0,0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      padding: 16,
    }}>
      <div className="card card-glow animate-modal-in" style={{
        maxWidth: 680,
        width: '100%',
        maxHeight: '90vh',
        overflowY: 'auto',
        position: 'relative',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        padding: 24,
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Sliders size={20} color="var(--accent-cyan)" />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Engine & Hardware Preferences</h2>
          </div>
          <button className="btn btn-secondary" onClick={onClose} style={{ padding: 6, borderRadius: '50%' }}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid var(--border-color)', paddingBottom: 10, marginBottom: 20 }}>
          <button
            className={`btn ${activeTab === 'general' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('general')}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Settings size={14} />
            <span>General</span>
          </button>
          <button
            className={`btn ${activeTab === 'subtitles' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('subtitles')}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Subtitles size={14} />
            <span>Subtitles & Hinglish</span>
          </button>
          <button
            className={`btn ${activeTab === 'audio' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('audio')}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Volume2 size={14} />
            <span>Audio & SFX</span>
          </button>
          <button
            className={`btn ${activeTab === 'hardware' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('hardware')}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Cpu size={14} />
            <span>GPU / NVENC</span>
          </button>
          <button
            className={`btn ${activeTab === 'publishing' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => {
              setActiveTab('publishing')
              loadPlatforms()
            }}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            <Share2 size={14} />
            <span>Publishing Accounts</span>
          </button>
        </div>

        {/* Tab 1: General */}
        {activeTab === 'general' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                Framing & Layout Mode
              </label>
              <select
                className="select"
                value={localSettings.layout}
                onChange={(e) => handleChange('layout', e.target.value)}
              >
                <option value="auto">Auto (Salient subject detection + center crop)</option>
                <option value="center">Fixed Center Crop (1080×1920)</option>
                <option value="face_cam">Gameplay Top + Facecam Bottom Stack</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  Resolution Output
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={localSettings.resolution}
                  readOnly
                  style={{ opacity: 0.8 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  Target Framerate
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={`${localSettings.fps} FPS`}
                  readOnly
                  style={{ opacity: 0.8 }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  Default Duration Presets
                </label>
                <select
                  className="select"
                  value={localSettings.duration_mode}
                  onChange={(e) => handleChange('duration_mode', e.target.value)}
                >
                  <option value="auto">Auto (Adaptive 15s–180s)</option>
                  <option value="quick">Quick (15s–30s)</option>
                  <option value="short">Short (30s–60s)</option>
                  <option value="extended">Extended (60s–180s)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  Encoding Quality Preset
                </label>
                <select
                  className="select"
                  value={localSettings.quality_preset}
                  onChange={(e) => handleChange('quality_preset', e.target.value)}
                >
                  <option value="High">High (CQ 19 - NVENC P6)</option>
                  <option value="Fast">Fast (CQ 23 - NVENC P4)</option>
                  <option value="Lossless">Ultra (CQ 16 - NVENC P7)</option>
                </select>
              </div>
            </div>

            <div style={{ padding: '12px 14px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: 8, border: '1px solid var(--border-color)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}>
                <input
                  type="checkbox"
                  checked={localSettings.semantic_reranker !== false}
                  onChange={(e) => handleChange('semantic_reranker', e.target.checked)}
                />
                <span>AI Judge & Semantic Reranker (Local Ollama)</span>
              </label>
              <p style={{ margin: '4px 0 0 24px', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                Evaluates hook strength, storytelling payoff, and down-ranks stream filler. Runs safely on top candidates if local Ollama (Llama 3) is running; falls back seamlessly if offline.
              </p>
            </div>
          </div>
        )}

        {/* Tab 2: Subtitles & Hinglish Pipeline */}
        {activeTab === 'subtitles' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                Primary Subtitle Language
              </label>
              <select
                className="select"
                value={localSettings.subtitle_language}
                onChange={(e) => handleChange('subtitle_language', e.target.value)}
              >
                <option value="auto">Auto Detect</option>
                <option value="original">Original Audio Language</option>
                <option value="hinglish">Hinglish (Roman Hindi + English Gaming)</option>
                <option value="hindi">Hindi (Devanagari)</option>
                <option value="english">English (Global)</option>
              </select>
            </div>

            <div style={{
              background: 'rgba(139, 92, 246, 0.12)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              padding: '12px 16px',
              borderRadius: 8,
              fontSize: '0.8rem',
              color: '#d8b4fe',
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Hinglish Subtitles Hook (Phase 7 Architecture):</div>
              Allows seamless generation of Romanized Hindi captions for gaming channels while keeping English gaming vocabulary (e.g. <em>"Clutch kar diya bhai!"</em>). Preserves word-level karaoke sync without hallucination.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.captions}
                  onChange={(e) => handleChange('captions', e.target.checked)}
                />
                <span>Burn Word-Level Subtitles onto Video</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.word_highlighting}
                  onChange={(e) => handleChange('word_highlighting', e.target.checked)}
                />
                <span>Active Karaoke Word Highlighting (Cyan Glow)</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.emoji}
                  onChange={(e) => handleChange('emoji', e.target.checked)}
                />
                <span>Contextual Gaming Emojis (💀, 🔥, 🎯, 😱)</span>
              </label>
            </div>
          </div>
        )}

        {/* Tab 3: Audio Polish & SFX */}
        {activeTab === 'audio' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  Target Integrated Loudness
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={`${localSettings.target_lufs} LUFS (Broadcast Standard)`}
                  readOnly
                  style={{ opacity: 0.8 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
                  True Peak Ceiling
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={`${localSettings.true_peak} dBTP (Distortion Prevention)`}
                  readOnly
                  style={{ opacity: 0.8 }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.audio}
                  onChange={(e) => handleChange('audio', e.target.checked)}
                />
                <span>Enable Master Loudness Normalization (Phase 6A)</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.ducking}
                  onChange={(e) => handleChange('ducking', e.target.checked)}
                />
                <span>Automatic Dynamic Ducking During Speech Peaks</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.85rem' }}>
                <input
                  type="checkbox"
                  checked={localSettings.sfx}
                  onChange={(e) => handleChange('sfx', e.target.checked)}
                />
                <span>Procedural Sound Effects (Whoosh, Impact, Bass Drop)</span>
              </label>
            </div>
          </div>
        )}

        {/* Tab 4: GPU / Hardware Acceleration */}
        {activeTab === 'hardware' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{
              background: 'rgba(0, 242, 254, 0.05)',
              border: '1px solid var(--border-color)',
              padding: 16,
              borderRadius: 8,
              fontSize: '0.85rem',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: 'var(--text-muted)' }}>Video Encoder:</span>
                <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>NVIDIA NVENC (h264_nvenc)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: 'var(--text-muted)' }}>Whisper Inference:</span>
                <span style={{ fontWeight: 600, color: 'var(--accent-purple)' }}>CUDA FP16 Local Execution</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: 'var(--text-muted)' }}>Fallback Capability:</span>
                <span style={{ color: 'var(--text-main)' }}>Automatic CPU (libx264) graceful degradation</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>External Cloud API Cost:</span>
                <span style={{ fontWeight: 700, color: 'var(--accent-green)' }}>$0.00 (100% Free / Local-First)</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Publishing Accounts */}
        {activeTab === 'publishing' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>Social Media Publishing Layer (Phase 13)</h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', margin: '4px 0 0 0' }}>
                  Local-first, modular social upload adapters. Credentials are kept strictly in your local <code>config/credentials/</code> folder.
                </p>
              </div>
              <button
                className="btn btn-secondary"
                onClick={loadPlatforms}
                disabled={isLoadingPlatforms}
                style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <RefreshCw size={13} className={isLoadingPlatforms ? 'animate-spin' : ''} />
                <span>Refresh Status</span>
              </button>
            </div>

            {platformActionMsg && (
              <div style={{
                padding: '8px 12px',
                borderRadius: 6,
                fontSize: '0.8rem',
                background: platformActionMsg.error ? 'rgba(239, 68, 68, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                border: `1px solid ${platformActionMsg.error ? '#f87171' : 'var(--accent-green)'}`,
                color: platformActionMsg.error ? '#f87171' : 'var(--accent-green)',
              }}>
                {platformActionMsg.text}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {platforms.map((p) => {
                const isConnecting = connectingPlatform === p.platform

                return (
                  <div
                    key={p.platform}
                    style={{
                      background: 'rgba(15, 23, 42, 0.7)',
                      borderRadius: 8,
                      border: '1px solid var(--border-color)',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                          width: 32,
                          height: 32,
                          borderRadius: 6,
                          background: p.platform === 'youtube' ? 'rgba(239, 68, 68, 0.15)' : (p.platform === 'tiktok' ? 'rgba(34, 211, 238, 0.15)' : 'rgba(236, 72, 153, 0.15)'),
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: p.platform === 'youtube' ? '#f87171' : (p.platform === 'tiktok' ? 'var(--accent-cyan)' : '#f472b6'),
                          fontWeight: 700,
                          fontSize: '0.85rem',
                        }}>
                          {p.platform === 'youtube' ? 'YT' : (p.platform === 'tiktok' ? 'TT' : 'IG')}
                        </div>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: '0.92rem', color: 'var(--text-main)' }}>
                            {p.display_name}
                          </div>
                          <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                            Privacy: {p.supported_privacy.join(', ')} • Scheduling: {p.supports_scheduling ? 'Supported' : 'Immediate only'}
                          </div>
                        </div>
                      </div>

                      {/* Status Badge */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {p.connected ? (
                          <span className="badge badge-green" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem' }}>
                            <CheckCircle size={12} /> Connected: {p.account_name}
                          </span>
                        ) : !p.sdk_installed ? (
                          <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem' }}>
                            <AlertTriangle size={12} /> SDK Missing
                          </span>
                        ) : p.configured ? (
                          <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>
                            Configured (Not Signed In)
                          </span>
                        ) : (
                          <span className="badge" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                            Not Configured
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Hint / Setup Information */}
                    <div style={{
                      fontSize: '0.78rem',
                      color: p.connected ? 'var(--text-main)' : 'var(--text-muted)',
                      background: 'rgba(0, 0, 0, 0.25)',
                      padding: '8px 12px',
                      borderRadius: 6,
                      borderLeft: `3px solid ${p.connected ? 'var(--accent-green)' : (p.configured ? 'var(--accent-cyan)' : 'var(--text-dim)')}`,
                    }}>
                      {p.setup_hint}
                    </div>

                    {/* Action Buttons */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                      {p.connected ? (
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleDisconnect(p.platform)}
                          disabled={isConnecting}
                          style={{ fontSize: '0.78rem', padding: '4px 10px', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                        >
                          Disconnect Account
                        </button>
                      ) : p.platform === 'youtube' && p.configured && p.sdk_installed ? (
                        <button
                          className="btn btn-primary"
                          onClick={() => handleConnect(p.platform)}
                          disabled={isConnecting}
                          style={{ fontSize: '0.78rem', padding: '4px 12px', display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                          <Key size={13} />
                          <span>{isConnecting ? 'Authorizing...' : 'Connect via Google OAuth'}</span>
                        </button>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--border-color)' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={() => {
              onSave(localSettings)
              onClose()
            }}
          >
            Save Preferences
          </button>
        </div>
      </div>
    </div>
  )
}

