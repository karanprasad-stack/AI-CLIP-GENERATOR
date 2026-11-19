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
      background: 'rgba(15, 20, 28, 0.88)',
      backdropFilter: 'blur(16px)',
      borderBottom: '1px solid var(--border-color)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '12px 24px',
    }}>
      <div style={{
        maxWidth: 1440,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        {/* Brand & Breadcrumbs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div 
            onClick={() => onNavigate('dashboard')}
            style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}
          >
            <div style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #00F2FE 0%, #4FACFE 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#050B14',
              boxShadow: '0 0 16px rgba(0, 242, 254, 0.4)',
            }}>
              <PlaySquare size={22} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 800, fontSize: '1.15rem', letterSpacing: '-0.02em', background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  AI CLIPPER
                </span>
                <span className="badge badge-cyan" style={{ fontSize: '0.65rem', padding: '2px 6px' }}>7B STUDIO</span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Gaming Shorts Workstation</div>
            </div>
          </div>

          {/* Breadcrumb if active project */}
          {activeProjectTitle && currentView !== 'history' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.85rem',
              color: 'var(--text-muted)',
              borderLeft: '1px solid var(--border-color)',
              paddingLeft: 16,
            }}>
              <span
                style={{ cursor: 'pointer', color: 'var(--text-dim)' }}
                onClick={() => onNavigate('history')}
              >
                Projects
              </span>
              <ChevronRight size={14} />
              <span style={{
                color: 'var(--text-main)',
                fontWeight: 600,
                maxWidth: 260,
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
            gap: 6,
            padding: '6px 12px',
            background: 'rgba(0,0,0,0.3)',
            borderRadius: 20,
            border: '1px solid var(--border-color)',
            fontSize: '0.75rem',
          }}>
            <span style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: isBackendConnected ? 'var(--accent-green)' : 'var(--accent-red)',
              boxShadow: isBackendConnected ? '0 0 8px #10B981' : '0 0 8px #EF4444',
            }} />
            <span style={{ color: isBackendConnected ? 'var(--text-main)' : 'var(--text-dim)' }}>
              {isBackendConnected ? 'FastAPI Local' : 'Disconnected'}
            </span>
          </div>

          <button
            className={`btn ${currentView === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onNavigate('history')}
            style={{ padding: '7px 14px' }}
          >
            <History size={16} />
            <span>Projects ({projectsCount})</span>
          </button>

          <button
            className="btn btn-secondary"
            onClick={onOpenSettings}
            title="Processing & Hardware Settings"
            style={{ padding: '7px 12px' }}
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
