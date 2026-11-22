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
    <header
      className="sticky top-0 z-50 flex items-center h-14 md:h-16 px-3 sm:px-6"
      style={{
        background: 'rgba(7, 11, 20, 0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      <div style={{
        maxWidth: 1600,
        width: '100%',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'nowrap',
        gap: 8,
      }}>
        {/* Brand & Breadcrumbs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          <div 
            onClick={() => onNavigate('dashboard')}
            style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', userSelect: 'none', flexShrink: 0 }}
          >
            <div style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #22D3EE 0%, #3B82F6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#040A14',
              boxShadow: '0 0 16px rgba(34, 211, 238, 0.35)',
              flexShrink: 0,
            }}>
              <PlaySquare size={18} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="brand-title-gradient" style={{
                  fontWeight: 800,
                  fontSize: '1.05rem',
                  letterSpacing: '-0.025em',
                  whiteSpace: 'nowrap',
                }}>
                  AI CLIPPER
                </span>
                <span className="badge badge-cyan" style={{ fontSize: '0.62rem', padding: '1px 5px' }}>STUDIO</span>
              </div>
              <div className="hidden md:block" style={{ fontSize: '0.68rem', color: 'var(--text-dim)', letterSpacing: '0.01em' }}>
                Gaming Shorts Workstation
              </div>
            </div>
          </div>

          {/* Breadcrumb if active project - hidden on mobile to avoid overflow */}
          {activeProjectTitle && currentView !== 'history' && (
            <div className="hidden lg:flex" style={{
              alignItems: 'center',
              gap: 8,
              fontSize: '0.825rem',
              color: 'var(--text-muted)',
              borderLeft: '1px solid var(--border-color)',
              paddingLeft: 14,
              minWidth: 0,
            }}>
              <span
                style={{ cursor: 'pointer', color: 'var(--text-dim)', transition: 'color 0.15s', whiteSpace: 'nowrap' }}
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
                maxWidth: 240,
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          {/* Status Indicator */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '5px 8px',
            background: 'rgba(0, 0, 0, 0.4)',
            borderRadius: 9999,
            border: '1px solid var(--border-color)',
            fontSize: '0.72rem',
          }}>
            <span
              className={isBackendConnected ? 'live-dot-pulse' : ''}
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                backgroundColor: isBackendConnected ? 'var(--accent-green)' : 'var(--accent-red)',
                display: 'inline-block',
                flexShrink: 0,
              }}
            />
            <span className="hidden sm:inline" style={{ color: isBackendConnected ? 'var(--text-main)' : 'var(--text-dim)', fontWeight: 500, whiteSpace: 'nowrap' }}>
              {isBackendConnected ? 'FastAPI Local' : 'Disconnected'}
            </span>
          </div>

          <button
            className={`btn ${currentView === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onNavigate('history')}
            style={{ padding: '6px 10px' }}
          >
            <History size={15} />
            <span className="hidden sm:inline">Projects ({projectsCount})</span>
            <span className="sm:hidden font-mono text-xs">({projectsCount})</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={onOpenSettings}
            title="Processing & Hardware Settings"
            style={{ padding: '6px 9px' }}
          >
            <SettingsIcon size={16} />
          </button>

          <button
            className="btn btn-primary"
            onClick={() => onNavigate('new')}
            style={{ padding: '6px 12px' }}
          >
            <Plus size={16} />
            <span className="hidden xs:inline sm:inline">New Video</span>
            <span className="xs:hidden sm:hidden">New</span>
          </button>
        </div>
      </div>
    </header>
  )
}
