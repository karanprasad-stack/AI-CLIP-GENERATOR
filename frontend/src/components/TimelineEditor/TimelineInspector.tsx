import React from 'react'
import { Type, Smile, Sparkles, Volume2, Mic, Sliders, Trash2, RotateCcw, Power } from 'lucide-react'
import type { SubtitleItem, EmojiItem, EffectItem, SfxItem, DuckingItem, TimelineBoundaries } from '../../types'

export type SelectedTimelineItem =
  | { type: 'subtitle'; item: SubtitleItem }
  | { type: 'emoji'; item: EmojiItem }
  | { type: 'effect'; item: EffectItem }
  | { type: 'sfx'; item: SfxItem }
  | { type: 'ducking'; item: DuckingItem }
  | { type: 'boundaries'; item: TimelineBoundaries }
  | null

interface TimelineInspectorProps {
  selection: SelectedTimelineItem
  onUpdate: (updatedSelection: SelectedTimelineItem) => void
  onDelete: (selection: SelectedTimelineItem) => void
  onSeek: (seconds: number) => void
}

export const TimelineInspector: React.FC<TimelineInspectorProps> = ({
  selection,
  onUpdate,
  onDelete,
  onSeek,
}) => {
  if (!selection) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        color: 'var(--text-dim)',
        fontSize: '0.85rem',
        textAlign: 'center',
      }}>
        <Sliders size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
        <div style={{ fontWeight: 600, color: 'var(--text-muted)' }}>No Item Selected</div>
        <p style={{ marginTop: 4, fontSize: '0.8rem' }}>
          Click any subtitle, emoji, visual effect, or SFX event on the timeline to inspect and edit properties.
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 18px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {selection.type === 'subtitle' && <Type size={16} color="var(--accent-cyan)" />}
          {selection.type === 'emoji' && <Smile size={16} color="var(--accent-amber)" />}
          {selection.type === 'effect' && <Sparkles size={16} color="var(--accent-purple)" />}
          {selection.type === 'sfx' && <Volume2 size={16} color="var(--accent-green)" />}
          {selection.type === 'ducking' && <Mic size={16} color="#38bdf8" />}
          {selection.type === 'boundaries' && <Sliders size={16} color="var(--text-main)" />}
          <span style={{ fontWeight: 700, fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {selection.type} Inspector
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {selection.type !== 'boundaries' && (
            <button
              className="btn btn-secondary"
              onClick={() => {
                const copy = { ...selection } as any
                copy.item.enabled = !copy.item.enabled
                copy.item.edited = true
                onUpdate(copy)
              }}
              style={{
                padding: '4px 8px',
                fontSize: '0.75rem',
                color: (selection.item as any).enabled ? 'var(--accent-green)' : '#f87171',
              }}
              title="Toggle Enable / Disable"
            >
              <Power size={13} />
              <span>{(selection.item as any).enabled ? 'Enabled' : 'Disabled'}</span>
            </button>
          )}

          {selection.type !== 'boundaries' && (
            <button
              className="btn btn-danger"
              onClick={() => onDelete(selection)}
              style={{ padding: '4px 8px', fontSize: '0.75rem' }}
              title="Delete Event"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Subtitle Inspector */}
      {selection.type === 'subtitle' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              SUBTITLE TEXT (HINGLISH / ENGLISH / HINDI)
            </label>
            <textarea
              className="input-text"
              rows={3}
              value={selection.item.text}
              onChange={(e) => {
                onUpdate({
                  type: 'subtitle',
                  item: { ...selection.item, text: e.target.value, edited: true },
                })
              }}
              style={{ width: '100%', fontSize: '0.9rem', resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Start (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.start}
                onChange={(e) => {
                  const s = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'subtitle',
                    item: { ...selection.item, start: s, edited: true },
                  })
                  onSeek(s)
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                End (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.end}
                onChange={(e) => {
                  const end = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'subtitle',
                    item: { ...selection.item, end, edited: true },
                  })
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
            <span>Language: <strong style={{ color: 'var(--text-main)' }}>{selection.item.language}</strong></span>
            <span>Duration: <strong style={{ color: 'var(--accent-cyan)' }}>{(selection.item.end - selection.item.start).toFixed(2)}s</strong></span>
          </div>

          {selection.item.original_text && selection.item.edited && (
            <div style={{ background: 'rgba(0,0,0,0.3)', padding: 8, borderRadius: 6, fontSize: '0.75rem' }}>
              <div style={{ color: 'var(--text-dim)', marginBottom: 2 }}>Original AI Text:</div>
              <div style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>"{selection.item.original_text}"</div>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  onUpdate({
                    type: 'subtitle',
                    item: { ...selection.item, text: selection.item.original_text || '', edited: false },
                  })
                }}
                style={{ marginTop: 6, padding: '3px 8px', fontSize: '0.7rem' }}
              >
                <RotateCcw size={11} />
                <span>Restore AI Text</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Emoji Inspector */}
      {selection.type === 'emoji' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              EMOJI CHARACTER
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="input-text"
                value={selection.item.emoji}
                onChange={(e) => {
                  onUpdate({
                    type: 'emoji',
                    item: { ...selection.item, emoji: e.target.value, edited: true },
                  })
                }}
                style={{ fontSize: '1.4rem', width: 70, textAlign: 'center' }}
              />
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {['😂', '💀', '🔥', '😱', '👑', '🎯', '💥', '👀'].map((em) => (
                  <button
                    key={em}
                    className="btn btn-secondary"
                    onClick={() => {
                      onUpdate({
                        type: 'emoji',
                        item: { ...selection.item, emoji: em, edited: true },
                      })
                    }}
                    style={{ padding: '4px 8px', fontSize: '1.1rem' }}
                  >
                    {em}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Timestamp (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.timestamp}
                onChange={(e) => {
                  const t = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'emoji',
                    item: { ...selection.item, timestamp: t, edited: true },
                  })
                  onSeek(t)
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Duration (sec)
              </label>
              <input
                type="number"
                step="0.1"
                min="0.2"
                max="5.0"
                className="input-text"
                value={selection.item.duration}
                onChange={(e) => {
                  const d = parseFloat(e.target.value) || 1.2
                  onUpdate({
                    type: 'emoji',
                    item: { ...selection.item, duration: d, edited: true },
                  })
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Visual Effect Inspector */}
      {selection.type === 'effect' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              EFFECT TYPE
            </label>
            <select
              className="select"
              value={selection.item.type}
              onChange={(e) => {
                onUpdate({
                  type: 'effect',
                  item: { ...selection.item, type: e.target.value, edited: true },
                })
              }}
              style={{ width: '100%' }}
            >
              <option value="subtle_zoom">Subtle Zoom (1.08x)</option>
              <option value="punch_zoom">Punch Zoom (1.15x)</option>
              <option value="impact_zoom">Impact Zoom (1.22x)</option>
              <option value="micro_shake">Micro Shake (Subtle)</option>
              <option value="impact_shake">Impact Shake (Intense)</option>
              <option value="emphasis_flash">Emphasis Flash</option>
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Start (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.start}
                onChange={(e) => {
                  const s = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'effect',
                    item: { ...selection.item, start: s, edited: true },
                  })
                  onSeek(s)
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                End (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.end}
                onChange={(e) => {
                  const end = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'effect',
                    item: { ...selection.item, end, edited: true },
                  })
                }}
              />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 4 }}>
              <span style={{ color: 'var(--text-muted)' }}>Intensity:</span>
              <strong style={{ color: 'var(--accent-purple)' }}>{Math.round(selection.item.intensity * 100)}%</strong>
            </div>
            <input
              type="range"
              min="0.1"
              max="1.0"
              step="0.05"
              value={selection.item.intensity}
              onChange={(e) => {
                onUpdate({
                  type: 'effect',
                  item: { ...selection.item, intensity: parseFloat(e.target.value), edited: true },
                })
              }}
              style={{ width: '100%' }}
            />
          </div>

          {selection.item.reason && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              AI Justification: <em>{selection.item.reason}</em>
            </div>
          )}
        </div>
      )}

      {/* SFX Inspector */}
      {selection.type === 'sfx' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              SOUND EFFECT TYPE
            </label>
            <select
              className="select"
              value={selection.item.event_type}
              onChange={(e) => {
                const evType = e.target.value
                const assetMap: Record<string, string> = {
                  whoosh: 'whoosh_strong.wav',
                  major_impact: 'impact_heavy.wav',
                  minor_impact: 'impact_medium.wav',
                  reaction_accent: 'pop.wav',
                  transition: 'whoosh_soft.wav',
                }
                onUpdate({
                  type: 'sfx',
                  item: {
                    ...selection.item,
                    event_type: evType,
                    asset_name: assetMap[evType] || 'whoosh_soft.wav',
                    edited: true,
                  },
                })
              }}
              style={{ width: '100%' }}
            >
              <option value="whoosh">Whoosh (Fast Swish)</option>
              <option value="major_impact">Major Impact (Sub Bass Hit)</option>
              <option value="minor_impact">Minor Impact (Click / Punch)</option>
              <option value="reaction_accent">Reaction Pop</option>
              <option value="transition">Soft Transition</option>
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Timestamp (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.timestamp}
                onChange={(e) => {
                  const t = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'sfx',
                    item: { ...selection.item, timestamp: t, edited: true },
                  })
                  onSeek(t)
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Gain (dB)
              </label>
              <input
                type="number"
                step="0.5"
                min="-30"
                max="0"
                className="input-text"
                value={selection.item.gain_db}
                onChange={(e) => {
                  const g = parseFloat(e.target.value) || -14.0
                  onUpdate({
                    type: 'sfx',
                    item: { ...selection.item, gain_db: g, edited: true },
                  })
                }}
              />
            </div>
          </div>

          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Asset: <span style={{ fontFamily: 'monospace', color: 'var(--text-main)' }}>{selection.item.asset_name}</span>
          </div>
        </div>
      )}

      {/* Ducking Inspector */}
      {selection.type === 'ducking' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Start (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.start}
                onChange={(e) => {
                  const s = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'ducking',
                    item: { ...selection.item, start: s, edited: true },
                  })
                  onSeek(s)
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                End (sec)
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                className="input-text"
                value={selection.item.end}
                onChange={(e) => {
                  const end = parseFloat(e.target.value) || 0
                  onUpdate({
                    type: 'ducking',
                    item: { ...selection.item, end, edited: true },
                  })
                }}
              />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 4 }}>
              <span style={{ color: 'var(--text-muted)' }}>Background Attenuation:</span>
              <strong style={{ color: '#38bdf8' }}>{selection.item.attenuation_db.toFixed(1)} dB</strong>
            </div>
            <input
              type="range"
              min="-15"
              max="0"
              step="0.5"
              value={selection.item.attenuation_db}
              onChange={(e) => {
                onUpdate({
                  type: 'ducking',
                  item: { ...selection.item, attenuation_db: parseFloat(e.target.value), edited: true },
                })
              }}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )}

      {/* Boundaries Inspector */}
      {selection.type === 'boundaries' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Source In (sec)
              </label>
              <input
                type="number"
                step="0.5"
                min="0"
                className="input-text"
                value={selection.item.source_in}
                onChange={(e) => {
                  const sin = parseFloat(e.target.value) || 0
                  const dur = Math.max(0.1, selection.item.source_out - sin)
                  onUpdate({
                    type: 'boundaries',
                    item: { ...selection.item, source_in: sin, duration: dur },
                  })
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Source Out (sec)
              </label>
              <input
                type="number"
                step="0.5"
                min="0"
                className="input-text"
                value={selection.item.source_out}
                onChange={(e) => {
                  const sout = parseFloat(e.target.value) || 0
                  const dur = Math.max(0.1, sout - selection.item.source_in)
                  onUpdate({
                    type: 'boundaries',
                    item: { ...selection.item, source_out: sout, duration: dur },
                  })
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
            <span>Calculated Duration:</span>
            <strong style={{ color: 'var(--accent-cyan)' }}>{selection.item.duration.toFixed(2)}s</strong>
          </div>
        </div>
      )}
    </div>
  )
}
