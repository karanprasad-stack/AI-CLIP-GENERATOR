import React from 'react'
import { AlertTriangle, X } from 'lucide-react'

interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  isDestructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDestructive = false,
  onConfirm,
  onCancel,
}) => {
  if (!isOpen) return null

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(6px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 200,
      padding: 12,
    }}>
      <div className="card card-glow animate-modal-in w-[calc(100vw-24px)] sm:max-w-[460px] p-4 sm:p-6" style={{
        background: '#0D1322',
        border: '1px solid var(--border-color)',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: isDestructive ? 'rgba(239, 68, 68, 0.15)' : 'rgba(0, 242, 254, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: isDestructive ? 'var(--accent-red)' : 'var(--accent-cyan)',
              flexShrink: 0,
            }}>
              <AlertTriangle size={20} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>{title}</h3>
          </div>
          <button className="btn btn-secondary" onClick={onCancel} style={{ padding: 6, borderRadius: '50%' }}>
            <X size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', lineHeight: 1.5, marginBottom: 20 }}>
          {message}
        </p>

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-2.5">
          <button className="btn btn-secondary w-full sm:w-auto" onClick={onCancel}>
            {cancelText}
          </button>
          <button
            className={`btn ${isDestructive ? 'btn-danger' : 'btn-primary'} w-full sm:w-auto`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
