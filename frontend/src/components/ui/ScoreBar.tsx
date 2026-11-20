import React from 'react'

interface ScoreBarProps {
  label: string
  score: number
  maxScore?: number
}

export const ScoreBar: React.FC<ScoreBarProps> = ({ label, score, maxScore = 100 }) => {
  const percent = Math.min(100, Math.max(0, (score / maxScore) * 100))

  // Disciplined semantic color coding based on creator quality score
  let barGradient = 'linear-gradient(90deg, rgba(244, 63, 94, 0.8), #F43F5E)'
  let textColor = '#FB7185'

  if (percent >= 75) {
    barGradient = 'linear-gradient(90deg, #10B981, #34D399)'
    textColor = '#34D399'
  } else if (percent >= 55) {
    barGradient = 'linear-gradient(90deg, #0EA5E9, #22D3EE)'
    textColor = '#38BDF8'
  } else if (percent >= 40) {
    barGradient = 'linear-gradient(90deg, #D97706, #F59E0B)'
    textColor = '#FBBF24'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.74rem' }}>
        <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>{label}</span>
        <span
          className="font-mono"
          style={{ fontWeight: 600, color: textColor, fontVariantNumeric: 'tabular-nums' }}
        >
          {score.toFixed(1)}
        </span>
      </div>
      <div style={{
        width: '100%',
        height: 5,
        background: 'rgba(0, 0, 0, 0.45)',
        borderRadius: 9999,
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.05)',
      }}>
        <div style={{
          width: `${percent}%`,
          height: '100%',
          background: barGradient,
          borderRadius: 9999,
          transition: 'width 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        }} />
      </div>
    </div>
  )
}
