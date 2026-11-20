import type {
  ProjectSummary,
  ProjectDetail,
  ProcessingSettings,
  PlatformStatus,
  PublishRequest,
  PublishResult,
  PublishHistoryEntry,
} from '../types'

const API_BASE = '/api'

export async function fetchProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`)
  if (!res.ok) throw new Error('Failed to fetch projects')
  return res.json()
}

export async function fetchProject(id: string): Promise<ProjectDetail> {
  const res = await fetch(`${API_BASE}/projects/${id}`)
  if (!res.ok) throw new Error('Failed to fetch project details')
  return res.json()
}

export async function createProject(
  url: string,
  settings?: Partial<ProcessingSettings>,
  title?: string,
  sourceType?: string
): Promise<ProjectDetail> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ url, settings, title, source_type: sourceType || 'normal_video' }),
  })
  if (!res.ok) throw new Error('Failed to create project')
  return res.json()
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete project')
}

export async function startAnalysis(id: string, settings?: Partial<ProcessingSettings>): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${id}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: settings ? jsonStringify(settings) : undefined,
  })
  if (!res.ok) throw new Error('Failed to start analysis')
}

export async function selectCandidates(id: string, candidateIds: number[]): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${id}/select-candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ candidate_ids: candidateIds }),
  })
  if (!res.ok) throw new Error('Failed to select candidates')
}

export async function startRender(id: string, candidateIds?: number[], settings?: Partial<ProcessingSettings>): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${id}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ candidate_ids: candidateIds, settings }),
  })
  if (!res.ok) throw new Error('Failed to start rendering')
}

export async function cancelJob(id: string): Promise<void> {
  await fetch(`${API_BASE}/projects/${id}/cancel`, { method: 'POST' })
}

export async function updateMetadata(
  id: string,
  candidateId: number,
  data: { title?: string; description?: string; hashtags?: string[]; keywords?: string[] }
): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${id}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ candidate_id: candidateId, ...data }),
  })
  if (!res.ok) throw new Error('Failed to update metadata')
  return res.json()
}

export async function regenerateMetadata(id: string, candidateId: number): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${id}/metadata/regenerate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ candidate_id: candidateId }),
  })
  if (!res.ok) throw new Error('Failed to regenerate metadata')
  return res.json()
}

export async function fetchTimeline(projectId: string, candidateId: number): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/candidates/${candidateId}/timeline`)
  if (!res.ok) throw new Error('Failed to fetch candidate timeline')
  return res.json()
}

export async function saveTimeline(projectId: string, candidateId: number, timeline: any): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/candidates/${candidateId}/timeline`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify(timeline),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to save timeline')
  }
  return res.json()
}

export async function renderTimeline(projectId: string, candidateId: number): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/candidates/${candidateId}/timeline/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to render timeline')
  }
  return res.json()
}

export function getPackageDownloadUrl(id: string, candidateId?: number): string {
  return candidateId !== undefined
    ? `${API_BASE}/projects/${id}/package?candidate_id=${candidateId}`
    : `${API_BASE}/projects/${id}/package`
}

export async function getOutputDetail(projectId: string, candidateId: number): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/outputs/${candidateId}`)
  if (!res.ok) throw new Error('Failed to fetch output detail')
  return res.json()
}

export function getFileUrl(id: string, relativePath: string): string {
  const cleanPath = relativePath.replace(/^.*[\\/]publishing[\\/]/, 'publishing/').replace(/^.*[\\/]output[\\/][^\\/]+[\\/]/, '')
  return `${API_BASE}/projects/${id}/files/${cleanPath.replace(/\\/g, '/')}`
}

export function getSourceVideoUrl(id: string): string {
  return `${API_BASE}/projects/${id}/source-video`
}

export function getProjectAudioUrl(id: string): string {
  return `${API_BASE}/projects/${id}/audio`
}

export function subscribeProjectEvents(
  id: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
): () => void {
  const sse = new EventSource(`${API_BASE}/projects/${id}/events`)

  sse.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
    } catch {
      // heartbeat
    }
  }

  sse.onerror = (e) => {
    if (onError) onError(e)
  }

  return () => {
    sse.close()
  }
}

function jsonStringify(obj: any): string {
  return JSON.stringify(obj)
}

export async function startLiveSession(id: string): Promise<{ status: string; session_id: string }> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/start`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to start live stream')
  }
  return res.json()
}

export async function stopLiveSession(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/stop`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to stop live stream')
  return res.json()
}

export async function pauseLiveSession(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/pause`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to pause live stream')
  return res.json()
}

export async function resumeLiveSession(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/resume`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to resume live stream')
  return res.json()
}

export async function fetchLiveStatus(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/status`)
  if (!res.ok) throw new Error('Failed to fetch live status')
  return res.json()
}

export async function fetchLiveCandidates(id: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/candidates`)
  if (!res.ok) throw new Error('Failed to fetch live candidates')
  const data = await res.json()
  return data.candidates || []
}

export async function fetchLiveActivity(id: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/projects/${id}/live/activity`)
  if (!res.ok) throw new Error('Failed to fetch live activity')
  const data = await res.json()
  return data.events || []
}

export async function fetchPublishingPlatforms(): Promise<PlatformStatus[]> {
  const res = await fetch(`${API_BASE}/publishing/platforms`)
  if (!res.ok) throw new Error('Failed to fetch publishing platforms')
  return res.json()
}

export async function connectPlatform(platform: string, authData?: any): Promise<any> {
  const res = await fetch(`${API_BASE}/publishing/${platform}/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: authData ? JSON.stringify({ auth_data: authData }) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to connect platform' }))
    throw new Error(err.detail || 'Failed to connect platform')
  }
  return res.json()
}

export async function disconnectPlatform(platform: string): Promise<any> {
  const res = await fetch(`${API_BASE}/publishing/${platform}/disconnect`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to disconnect platform')
  return res.json()
}

export async function publishCandidate(
  projectId: string,
  candidateId: number,
  req: PublishRequest
): Promise<PublishResult> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/candidates/${candidateId}/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Publish failed' }))
    throw new Error(err.detail || 'Publish failed')
  }
  return res.json()
}

export async function fetchPublishHistory(projectId: string): Promise<PublishHistoryEntry[]> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/publish-history`)
  if (!res.ok) throw new Error('Failed to fetch publish history')
  return res.json()
}

export async function fetchCandidatePublishHistory(
  projectId: string,
  candidateId: number
): Promise<PublishHistoryEntry[]> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/candidates/${candidateId}/publish-history`)
  if (!res.ok) throw new Error('Failed to fetch candidate publish history')
  return res.json()
}
