import manifest from './plugin.json'

export interface SpotifySettings {
  dynamicMode?: 'always' | 'on_event' | 'off'
  userPriority?: number
  accentColor: string
  clientId: string
  clientSecret: string
  redirectUri: string
  showArtist: boolean
  showAlbum: boolean
  showProgressBar: boolean
  showTimeRemaining: boolean
  showEqualizer: boolean
  triggerOnTrackChange: boolean
  triggerOnPlayStart: boolean
  triggerWhilePlaying: boolean
}

export interface SpotifyPluginData {
  authenticated?: boolean
  configured?: boolean
  is_playing?: boolean
  track_id?: string | null
  title?: string | null
  artist?: string | null
  album?: string | null
  progress_ms?: number
  duration_ms?: number
  progress_pct?: number
  event_triggered?: boolean
  fetched_at?: string | null
  error?: string | null
}

export const DEFAULT_SPOTIFY_SETTINGS: SpotifySettings =
  manifest.defaultSettings as SpotifySettings
