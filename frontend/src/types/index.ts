export interface ProcessingSettings {
  duration_mode: 'auto' | '15_30' | '30_60' | '60_180' | 'custom'
  min_duration: number
  max_duration: number
  num_shorts_mode: 'auto' | 'custom'
  num_shorts: number
  layout: 'auto' | 'smart_crop' | 'blurred_background' | 'facecam_gameplay'
  captions: boolean
  subtitle_language: 'auto' | 'original' | 'english' | 'hindi' | 'hinglish'
  word_highlighting: boolean
  emoji: boolean
  effects: boolean
  effects_mode: 'smart' | 'custom'
  audio: boolean
  sfx: boolean
  ducking: boolean
  thumbnail: boolean
  metadata_enabled: boolean
  llm: boolean
  semantic_reranker?: boolean
  quality_preset: 'Standard' | 'High' | 'Very High' | 'Custom'
  aspect_ratio?: '9:16' | '1:1'
  kill_feed_overlay?: 'auto' | 'on' | 'off'
  game_mode?: 'auto' | 'valorant' | 'competitive_fps' | 'story_open_world' | 'horror_survival' | 'generic'
  resolution: string
  fps: number
  target_lufs: number
  true_peak: number
}

export interface ScoreBreakdown {
  gameplay_event_score?: number
  audio_score?: number
  transcript_score?: number
  context_score?: number
  boundary_score?: number
  [key: string]: any
}

export interface TimelineBoundaries {
  source_in: number
  source_out: number
  duration: number
  min_allowed: number
  max_allowed: number
}

export interface TimelineVideoTrack {
  source_file: string
  layout: string
  resolution: string
  aspect_ratio?: string
  fps: number
  enabled: boolean
  kill_feed_overlay?: boolean
  kill_feed_roi?: [number, number, number, number] | number[] | null
}

export interface SubtitleWordItem {
  word: string
  start: number
  end: number
}

export interface SubtitleItem {
  id: string
  start: number
  end: number
  text: string
  words: SubtitleWordItem[]
  language: string
  confidence: number
  enabled: boolean
  source: 'ai' | 'user'
  edited: boolean
  original_text?: string
}

export interface EmojiItem {
  id: string
  timestamp: number
  duration: number
  emoji: string
  animation: string
  position: string
  enabled: boolean
  source: 'ai' | 'user'
  edited: boolean
}

export interface EffectItem {
  id: string
  type: string
  start: number
  end: number
  intensity: number
  focal_point?: number[]
  reason?: string
  enabled: boolean
  source: 'ai' | 'user'
  edited: boolean
}

export interface SfxItem {
  id: string
  timestamp: number
  event_type: string
  asset_name: string
  gain_db: number
  reason?: string
  enabled: boolean
  source: 'ai' | 'user'
  edited: boolean
}

export interface DuckingItem {
  id: string
  start: number
  end: number
  attenuation_db: number
  attack_ms: number
  release_ms: number
  enabled: boolean
  source: 'ai' | 'user'
  edited: boolean
}

export interface TimelineMetadata {
  created_at: string
  updated_at: string
  source: string
  edit_summary?: string
  dirty_tracks: string[]
}

export interface TimelineEDL {
  project_id: string
  candidate_id: number
  version: number
  duration: number
  boundaries: TimelineBoundaries
  video_track: TimelineVideoTrack
  subtitles_track: SubtitleItem[]
  emoji_track: EmojiItem[]
  effects_track: EffectItem[]
  sfx_track: SfxItem[]
  ducking_track: DuckingItem[]
  metadata: TimelineMetadata
}


export interface PublishabilityDimensions {
  moment: number
  narrative: number
  presentation: number
  publishing: number
  technical: number
  diversity: number
}

export interface PublishabilityInfo {
  score: number
  level: 'excellent' | 'strong' | 'review' | 'weak' | 'reject'
  recommendation: 'publish' | 'review' | 'reject'
  dimensions: PublishabilityDimensions
  reasons: string[]
  warnings: string[]
  blocking_issues: string[]
}

export interface CandidateOutput {
  video_url: string
  filename: string
  size_bytes?: number
  thumbnail_url?: string | null
  duration?: number
}

export interface SemanticAudit {
  enabled: boolean
  score?: number
  is_filler?: boolean
  verdict?: string
  hook_score?: number
  standalone_score?: number
  entertainment_score?: number
}

export interface Candidate {
  candidate_id: number
  rank: number
  start: number
  end: number
  duration: number
  final_score: number
  score_breakdown?: ScoreBreakdown
  gameplay_event?: string
  secondary_events?: string[]
  strongest_reaction?: string
  tone?: string
  signals?: string[]
  selected?: boolean
  status?: string
  global_rank?: number
  chunk_id?: string
  quality_gate_status?: string
  duplicate_group?: string
  diversity_group?: string
  selection_reason?: string
  source_position_str?: string
  publishability?: PublishabilityInfo
  semantic_audit?: SemanticAudit
  base_composite_score?: number
  scene_warning?: string
  scene_cut_snapped?: boolean
  aspect_ratio?: string
  game_archetype?: string
  detected_game_title?: string
  effect_style?: string
  rendered?: boolean
  transcript_excerpt?: string
  gameplay_events?: any[]
  duration_tier?: string
  ranking_reasons?: string[]
  output?: CandidateOutput | null
}

export interface LongStreamInfo {
  source_duration: number
  chunks_processed: number
  total_chunks: number
  candidates_detected: number
  strong_moments: number
  recommended_shorts: number
  chunks_failed?: number
  chunks_reused?: number
  deduplicated_candidates?: number
  selected_candidates?: number
  quality_gate_reason?: string
}

export interface ProgressState {
  step: number
  total_steps: number
  percent: number
  stage: string
  message: string
  current_candidate: number
  logs: string[]
}

export interface MetadataQuality {
  overall: number
  relevance: number
  specificity: number
  naturalness: number
  uniqueness: number
  grounding: number
}

export interface PublishedPackage {
  candidate_id: number
  package_dir: string
  title: string
  description?: string
  hashtags?: string[]
  keywords?: string[]
  thumbnail: string
  thumbnail_score: number
  thumbnail_timestamp: number
  quality_score: number
  status: string
  metadata_quality?: MetadataQuality
  publishability?: PublishabilityInfo
}

export type SourceType = 'normal_video' | 'live_stream'

export interface LiveSessionInfo {
  session_id: string | null
  status: string
  total_segments: number
  segments_processed: number
  candidates_detected: number
  candidates_ready: number
  storage_used?: number
}

export interface LiveActivityEvent {
  id: string
  timestamp: string
  time_str: string
  event_type: string
  message: string
  details?: Record<string, any>
}

export interface LiveStatusResponse {
  project_id: string
  session: Record<string, any> | null
  candidates_count: number
  publish_ready_count: number
  activity_recent: LiveActivityEvent[]
  storage_used_bytes: number
}

export interface ProjectDetail {
  id: string
  video_id: string
  url: string
  title: string
  uploader: string
  duration: number
  language: string
  created_at: string
  updated_at: string
  status: 'queued' | 'analyzing' | 'candidates_ready' | 'rendering' | 'completed' | 'failed' | 'cancelled' | 'starting' | 'connecting' | 'live' | 'reconnecting' | 'processing' | 'stopping' | 'ended'
  source_type?: SourceType
  live_session_info?: LiveSessionInfo | null
  settings: ProcessingSettings
  long_stream_info: LongStreamInfo
  candidates: Candidate[]
  selected_candidate_ids: number[]
  published_packages: PublishedPackage[]
  progress: ProgressState
  has_source_video?: boolean
  source_video_url?: string | null
  youtube_video_id?: string | null
  has_audio?: boolean
  audio_url?: string | null
  source_url?: string | null
  error?: {
    summary: string
    details: string
  } | null
}

export interface ProjectSummary {
  id: string
  video_id: string
  url: string
  title: string
  uploader: string
  duration: number
  status: string
  source_type?: SourceType
  created_at: string
  updated_at: string
  candidates_count: number
  shorts_count: number
  percent: number
}

export type CandidateSortOption = 'score' | 'duration' | 'rank' | 'publishability'
export type CandidateFilterOption = 'all' | 'selected' | 'publish' | 'review' | 'reject' | 'strong' | 'funny' | 'combat' | 'timing'
