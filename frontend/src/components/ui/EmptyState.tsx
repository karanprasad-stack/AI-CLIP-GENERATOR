import React from 'react'

interface EmptyStateProps {
  icon: React.ReactNode
  title: string
  description: string
  actionText?: string
  onAction?: () => void
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  actionText,
  onAction,
}) => {
  return (
    <div className="card" style={{
      textAlign: 'center',
      padding: '50px 20px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 14,
    }}>
      <div style={{
        width: 56,
        height: 56,
        borderRadius: '50%',
        background: 'rgba(0, 242, 254, 0.1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--accent-cyan)',
      }}>
        {icon}
      </div>
      <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>{title}</h3>
      <p style={{ color: 'var(--text-muted)', maxWidth: 420, fontSize: '0.875rem', lineHeight: 1.5 }}>
        {description}
      </p>
      {actionText && onAction && (
        <button className="btn btn-primary" onClick={onAction} style={{ marginTop: 6 }}>
          {actionText}
        </button>
      )}
    </div>
  )
}
