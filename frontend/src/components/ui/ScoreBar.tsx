import React from 'react'

interface ScoreBarProps {
  label: string
  score: number
  maxScore?: number
}

export const ScoreBar: React.FC<ScoreBarProps> = ({ label, score, maxScore = 100 }) => {
  const percent = Math.min(100, Math.max(0, (score / maxScore) * 100))
  
  // Color coding based on score threshold
  let barColor = 'var(--accent-red)'
  if (percent >= 75) {
    barColor = 'var(--accent-green)'
  } else if (percent >= 55) {
    barColor = 'var(--accent-cyan)'
  } else if (percent >= 40) {
    barColor = 'var(--accent-amber)'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontWeight: 600, color: barColor }}>{score.toFixed(1)}</span>
      </div>
      <div style={{
        width: '100%',
        height: 6,
        background: 'rgba(0, 0, 0, 0.4)',
        borderRadius: 3,
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.05)',
      }}>
        <div style={{
          width: `${percent}%`,
          height: '100%',
          backgroundColor: barColor,
          borderRadius: 3,
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  )
}
