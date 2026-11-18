import manifest from './plugin.json'

export type WeatherIconId =
  | 'clear'
  | 'partly-cloudy'
  | 'overcast'
  | 'fog'
  | 'drizzle'
  | 'rain'
  | 'snow'
  | 'storm'
  | 'unknown'

export interface WeatherSettings {
  accentColor: string
  cityName: string
  latitude: number
  longitude: number
  showCondition: boolean
  showHighLow: boolean
  showHumidity: boolean
  showWind: boolean
  showCornerBrackets: boolean
  alertOnSevereWeather: boolean
  triggerOnRain: boolean
  triggerOnStorm: boolean
  triggerOnSnow: boolean
  triggerOnFog: boolean
  triggerOnDrizzle: boolean
  triggerOnHighWind: boolean
  windThresholdKmh: number
  triggerOnExtremeTemp: boolean
  tempLowThresholdC: number
  tempHighThresholdC: number
}

export interface WeatherPluginData {
  temperature_c?: number | null
  humidity_pct?: number | null
  wind_kmh?: number | null
  weather_code?: number | null
  condition?: string
  icon?: WeatherIconId
  temp_max_c?: number | null
  temp_min_c?: number | null
  city_name?: string
  latitude?: number
  longitude?: number
  severe?: boolean
  event_triggered?: boolean
  fetched_at?: string
  stale?: boolean
  error?: string | null
}

export const DEFAULT_WEATHER_SETTINGS: WeatherSettings =
  manifest.defaultSettings as WeatherSettings
