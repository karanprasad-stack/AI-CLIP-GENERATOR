import React from 'react'
import { Plus, History, Settings as SettingsIcon, PlaySquare, ChevronRight } from 'lucide-react'

interface NavbarProps {
  currentView: string
  projectsCount: number
  activeProjectTitle?: string
  onNavigate: (view: 'dashboard' | 'history' | 'new') => void
  onOpenSettings: () => void
  isBackendConnected: boolean
}

export const Navbar: React.FC<NavbarProps> = ({
  currentView,
  projectsCount,
  activeProjectTitle,
  onNavigate,
  onOpenSettings,
  isBackendConnected,
}) => {
  return (
    <header style={{
      background: 'rgba(7, 11, 20, 0.85)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderBottom: '1px solid var(--border-color)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '0 28px',
      height: 64,
      display: 'flex',
      alignItems: 'center',
    }}>
      <div style={{
        maxWidth: 1600,
        width: '100%',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        {/* Brand & Breadcrumbs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div 
            onClick={() => onNavigate('dashboard')}
            style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', userSelect: 'none' }}
          >
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #22D3EE 0%, #3B82F6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#040A14',
              boxShadow: '0 0 16px rgba(34, 211, 238, 0.35)',
            }}>
              <PlaySquare size={20} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="brand-title-gradient" style={{
                  fontWeight: 800,
                  fontSize: '1.15rem',
                  letterSpacing: '-0.025em',
                }}>
                  AI CLIPPER
                </span>
                <span className="badge badge-cyan" style={{ fontSize: '0.65rem', padding: '1px 6px' }}>STUDIO</span>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', letterSpacing: '0.01em' }}>Gaming Shorts Workstation</div>
            </div>
          </div>

          {/* Breadcrumb if active project */}
          {activeProjectTitle && currentView !== 'history' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: '0.825rem',
              color: 'var(--text-muted)',
              borderLeft: '1px solid var(--border-color)',
              paddingLeft: 16,
            }}>
              <span
                style={{ cursor: 'pointer', color: 'var(--text-dim)', transition: 'color 0.15s' }}
                onClick={() => onNavigate('history')}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--text-main)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-dim)')}
              >
                Projects
              </span>
              <ChevronRight size={14} color="var(--text-dim)" />
              <span style={{
                color: 'var(--text-main)',
                fontWeight: 600,
                maxWidth: 280,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {activeProjectTitle}
              </span>
            </div>
          )}
        </div>

        {/* Center / Right Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Status Indicator */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '5px 12px',
            background: 'rgba(0, 0, 0, 0.4)',
            borderRadius: 9999,
            border: '1px solid var(--border-color)',
            fontSize: '0.74rem',
          }}>
            <span
              className={isBackendConnected ? 'live-dot-pulse' : ''}
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                backgroundColor: isBackendConnected ? 'var(--accent-green)' : 'var(--accent-red)',
                display: 'inline-block',
              }}
            />
            <span style={{ color: isBackendConnected ? 'var(--text-main)' : 'var(--text-dim)', fontWeight: 500 }}>
              {isBackendConnected ? 'FastAPI Local' : 'Disconnected'}
            </span>
          </div>

          <button
            className={`btn ${currentView === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onNavigate('history')}
            style={{ padding: '7px 14px' }}
          >
            <History size={15} />
            <span>Projects ({projectsCount})</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={onOpenSettings}
            title="Processing & Hardware Settings"
            style={{ padding: '7px 11px' }}
          >
            <SettingsIcon size={16} />
          </button>

          <button
            className="btn btn-primary"
            onClick={() => onNavigate('new')}
            style={{ padding: '7px 16px' }}
          >
            <Plus size={16} />
            <span>New Video</span>
          </button>
        </div>
      </div>
    </header>
  )
}
