import { useState, useEffect } from 'react'
import { Navbar } from './components/Navbar'
import { ProjectHistory } from './components/ProjectHistory'
import { NewProjectModal } from './components/NewProjectModal'
import { SettingsModal } from './components/SettingsModal'
import { LiveProgress } from './components/LiveProgress'
import { CandidateReview } from './components/CandidateReview'
import { PublishingReview } from './components/PublishingReview'
import { LiveSessionView } from './components/LiveSessionView'
import { TimelineEditor } from './components/TimelineEditor/TimelineEditor'
import {
  fetchProjects,
  fetchProject,
  createProject,
  deleteProject,
  startAnalysis,
  startLiveSession,
  startRender,
  cancelJob,
  subscribeProjectEvents,
  testServerConnection,
  getApiBaseUrl,
} from './api/client'
import type { ProjectSummary, ProjectDetail, ProcessingSettings, SourceType } from './types'

const DEFAULT_SETTINGS: ProcessingSettings = {
  duration_mode: 'auto',
  min_duration: 15,
  max_duration: 180,
  num_shorts_mode: 'auto',
  num_shorts: 5,
  layout: 'auto',
  captions: true,
  subtitle_language: 'auto',
  word_highlighting: true,
  emoji: true,
  effects: true,
  effects_mode: 'smart',
  audio: true,
  sfx: true,
  ducking: true,
  thumbnail: true,
  metadata_enabled: true,
  llm: false,
  quality_preset: 'High',
  resolution: '1080x1920',
  fps: 60,
  target_lufs: -14.0,
  true_peak: -1.0,
}

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [activeProject, setActiveProject] = useState<ProjectDetail | null>(null)
  const [view, setView] = useState<'history' | 'progress' | 'candidates' | 'publishing' | 'live'>('history')
  const [editingCandidateId, setEditingCandidateId] = useState<number | null>(null)
  const [isNewModalOpen, setIsNewModalOpen] = useState(false)
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false)
  const [settings, setSettings] = useState<ProcessingSettings>(DEFAULT_SETTINGS)
  const [isBackendConnected, setIsBackendConnected] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showMobileServerBanner, setShowMobileServerBanner] = useState(false)

  useEffect(() => {
    // Check if running in a native mobile shell (Capacitor) without a configured server URL
    const isCapacitor =
      typeof (window as any).Capacitor !== 'undefined' &&
      typeof (window as any).Capacitor.isNativePlatform === 'function' &&
      (window as any).Capacitor.isNativePlatform()

    if (isCapacitor && !getApiBaseUrl()) {
      setShowMobileServerBanner(true)
    }
  }, [])

  const loadProjects = async () => {
    try {
      const data = await fetchProjects()
      setProjects(data)
      setIsBackendConnected(true)
    } catch {
      setIsBackendConnected(false)
    }
  }

  useEffect(() => {
    loadProjects()
    const timer = setInterval(loadProjects, 10000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    testServerConnection()
      .then((res) => setIsBackendConnected(res.ok))
      .catch(() => setIsBackendConnected(false))
  }, [])

  useEffect(() => {
    if (!activeProject) return
    const isRunning = activeProject.status === 'analyzing' || activeProject.status === 'rendering'
    if (!isRunning) return

    const unsubscribe = subscribeProjectEvents(
      activeProject.id,
      (event) => {
        setActiveProject((prev) => {
          if (!prev) return null
          return {
            ...prev,
            progress: {
              ...prev.progress,
              step: event.step ?? prev.progress.step,
              total_steps: event.total_steps ?? prev.progress.total_steps,
              percent: event.percent ?? prev.progress.percent,
              stage: event.stage ?? prev.progress.stage,
              message: event.message ?? prev.progress.message,
              current_candidate: event.current_candidate ?? prev.progress.current_candidate,
              logs: event.message ? [...prev.progress.logs, event.message] : prev.progress.logs,
            },
          }
        })

        if (event.step === event.total_steps && event.percent === 100) {
          fetchProject(activeProject.id).then((fresh) => {
            setActiveProject(fresh)
            if (fresh.status === 'candidates_ready') {
              setView('candidates')
            } else if (fresh.status === 'completed') {
              setView('publishing')
            }
            loadProjects()
          })
        }
      }
    )

    return () => unsubscribe()
  }, [activeProject?.id, activeProject?.status])

  const handleSelectProject = async (id: string) => {
    try {
      const detail = await fetchProject(id)
      setActiveProject(detail)
      if (detail.source_type === 'live_stream') {
        if (detail.status === 'completed') {
          setView('publishing')
        } else {
          setView('live')
        }
      } else if (detail.status === 'completed') {
        setView('publishing')
      } else if (detail.status === 'candidates_ready') {
        setView('candidates')
      } else if (detail.status === 'analyzing' || detail.status === 'rendering') {
        setView('progress')
      } else {
        setView('candidates')
      }
    } catch {
      alert('Failed to load project details.')
    }
  }

  const handleDeleteProject = async (id: string) => {
    try {
      await deleteProject(id)
      if (activeProject?.id === id) {
        setActiveProject(null)
        setView('history')
      }
      loadProjects()
    } catch {
      alert('Failed to delete project.')
    }
  }

  const handleCreateAndAnalyze = async (
    url: string,
    projectSettings: ProcessingSettings,
    title?: string,
    sourceType?: SourceType
  ) => {
    setIsSubmitting(true)
    try {
      const proj = await createProject(url, projectSettings, title, sourceType)
      if (sourceType === 'live_stream') {
        await startLiveSession(proj.id)
        const fresh = await fetchProject(proj.id)
        setActiveProject(fresh)
        setIsNewModalOpen(false)
        setView('live')
      } else {
        await startAnalysis(proj.id, projectSettings)
        const fresh = await fetchProject(proj.id)
        setActiveProject(fresh)
        setIsNewModalOpen(false)
        setView('progress')
      }
      loadProjects()
    } catch (e: any) {
      alert(`Error starting project: ${e.message}`)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleStartRender = async (selectedIds: number[]) => {
    if (!activeProject) return
    try {
      await startRender(activeProject.id, selectedIds, activeProject.settings)
      const fresh = await fetchProject(activeProject.id)
      setActiveProject(fresh)
      setView('progress')
      loadProjects()
    } catch (e: any) {
      alert(`Error starting render: ${e.message}`)
    }
  }

  const handleCancelJob = async () => {
    if (!activeProject) return
    await cancelJob(activeProject.id)
    const fresh = await fetchProject(activeProject.id)
    setActiveProject(fresh)
  }

  return (
    <div className="app-container">
      <Navbar
        currentView={view}
        projectsCount={projects.length}
        activeProjectTitle={activeProject?.title}
        onNavigate={(newView) => {
          if (newView === 'new') {
            setIsNewModalOpen(true)
          } else {
            setView('history')
          }
        }}
        onOpenSettings={() => setIsSettingsModalOpen(true)}
        isBackendConnected={isBackendConnected}
      />

      {/* Capacitor Mobile Setup Notification Banner */}
      {showMobileServerBanner && (
        <div style={{
          background: 'rgba(234, 179, 8, 0.12)',
          borderBottom: '1px solid rgba(234, 179, 8, 0.3)',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          fontSize: 13,
          color: '#FDE047',
          zIndex: 40,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>📱</span>
            <span><strong>Mobile App:</strong> Connect to your PC backend IP (e.g. <code>http://192.168.1.x:8000</code>) to analyze videos.</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => {
                setShowMobileServerBanner(false)
                setIsSettingsModalOpen(true)
              }}
              className="btn btn-primary btn-sm"
              style={{ fontSize: 12, padding: '4px 10px' }}
            >
              Configure Server URL
            </button>
            <button
              onClick={() => setShowMobileServerBanner(false)}
              className="btn btn-ghost btn-sm"
              style={{ fontSize: 12, padding: '4px 8px', color: '#CBD5E1' }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <main className="main-content">
        {view === 'history' && (
          <ProjectHistory
            projects={projects}
            onSelectProject={handleSelectProject}
            onDeleteProject={handleDeleteProject}
            onNewProject={() => setIsNewModalOpen(true)}
          />
        )}

        {view === 'progress' && activeProject && (
          <LiveProgress
            project={activeProject}
            onCancel={handleCancelJob}
            onProceed={() => {
              if (activeProject.status === 'candidates_ready') {
                setView('candidates')
              } else if (activeProject.status === 'completed') {
                setView('publishing')
              }
            }}
            onRetry={() => startAnalysis(activeProject.id, activeProject.settings)}
          />
        )}

        {view === 'candidates' && activeProject && (
          <CandidateReview
            project={activeProject}
            onRender={handleStartRender}
            onBackToHistory={() => setView('history')}
            onOpenPublishing={() => setView('publishing')}
          />
        )}

        {view === 'publishing' && activeProject && (
          <PublishingReview
            project={activeProject}
            onBackToHistory={() => setView('history')}
            onViewCandidates={() => setView('candidates')}
          />
        )}

        {view === 'live' && activeProject && (
          <LiveSessionView
            project={activeProject}
            onOpenTimelineEditor={(cid) => setEditingCandidateId(cid)}
            onRefreshProject={() => handleSelectProject(activeProject.id)}
          />
        )}
      </main>

      {/* Phase 8 Timeline Editor Modal */}
      {editingCandidateId !== null && activeProject && (
        <TimelineEditor
          project={activeProject}
          candidateId={editingCandidateId}
          onClose={() => setEditingCandidateId(null)}
          onRenderSuccess={() => {
            handleSelectProject(activeProject.id)
          }}
        />
      )}

      <NewProjectModal
        isOpen={isNewModalOpen}
        onClose={() => setIsNewModalOpen(false)}
        onSubmit={handleCreateAndAnalyze}
        defaultSettings={settings}
        isSubmitting={isSubmitting}
      />

      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => setIsSettingsModalOpen(false)}
        settings={settings}
        onSave={setSettings}
      />
    </div>
  )
}

export default App
