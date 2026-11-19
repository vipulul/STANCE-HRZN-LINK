"""Spotify Web API Now Playing plugin provider auto-discovered from `plugins/spotify/`."""

from __future__ import annotations

import asyncio
import base64
import html
import inspect
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SPOTIFY_SCOPES = "user-read-currently-playing user-read-playback-state"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/api/plugins/spotify/callback"
LEGACY_LOCALHOST_REDIRECT_URI = "http://localhost:8080/api/plugins/spotify/callback"

POLL_INTERVAL_PLAYING_S = 2.5
POLL_INTERVAL_IDLE_S = 5.0
ERROR_BACKOFF_S = 10.0
TOKEN_REFRESH_MARGIN_S = 60.0


def _normalize_redirect_uri(raw_uri: Any) -> str:
    """Normalize redirect URI to Spotify's required explicit loopback IP when localhost is used."""
    uri = str(raw_uri or "").strip()
    if not uri or uri == LEGACY_LOCALHOST_REDIRECT_URI:
        return DEFAULT_REDIRECT_URI
    return uri


def _ensure_plugin_routes_before_catchall() -> None:
    """Move any dynamically mounted `/api/plugins/*` routes ahead of SPA `/{full_path:path}`."""
    app = None
    reg_mod = sys.modules.get("server.plugins.registry")
    if reg_mod is not None:
        app = getattr(reg_mod, "_MOUNTED_APP", None)
    if app is None:
        main_mod = sys.modules.get("server.main")
        if main_mod is not None:
            app = getattr(main_mod, "app", None)
    router = getattr(app, "router", None) if app is not None else None
    routes = getattr(router, "routes", None) if router is not None else None
    if not isinstance(routes, list):
        return

    catchall_idx = next(
        (
            idx
            for idx, route in enumerate(routes)
            if getattr(route, "path", None) == "/{full_path:path}"
        ),
        None,
    )
    if catchall_idx is None:
        return

    after = routes[catchall_idx + 1 :]
    trailing_plugin_routes = [
        route for route in after if str(getattr(route, "path", "")).startswith("/api/plugins/")
    ]
    if not trailing_plugin_routes:
        return

    trailing_ids = {id(route) for route in trailing_plugin_routes}
    remaining_after = [route for route in after if id(route) not in trailing_ids]
    routes[:] = (
        routes[:catchall_idx]
        + trailing_plugin_routes
        + [routes[catchall_idx]]
        + remaining_after
    )
    if hasattr(app, "openapi_schema"):
        app.openapi_schema = None


def _resolve_data_dir() -> Path:
    env_dir = os.getenv("HRZN_DATA_DIR")
    return Path(env_dir) if env_dir else (REPO_ROOT / "data")


def _extract_track_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Spotify track or episode payload into flat HUD fields."""
    is_playing = bool(payload.get("is_playing", False))
    playing_type = str(payload.get("currently_playing_type") or "track")
    item = payload.get("item")

    if not isinstance(item, dict):
        if playing_type == "ad":
            return {
                "is_playing": is_playing,
                "track_id": "__spotify_ad__",
                "title": "Advertisement",
                "artist": "Spotify",
                "album": "",
                "progress_ms": 0,
                "duration_ms": 0,
            }
        return {
            "is_playing": False,
            "track_id": None,
            "title": None,
            "artist": None,
            "album": None,
            "progress_ms": 0,
            "duration_ms": 0,
        }

    track_id = str(item.get("id") or item.get("uri") or item.get("name") or "") or None
    title = str(item.get("name") or "").strip() or None

    if playing_type == "episode" or "show" in item:
        show = item.get("show") or {}
        artist = str(show.get("name") or "Podcast").strip() or "Podcast"
        album = str(show.get("publisher") or "").strip()
    else:
        raw_artists = item.get("artists") or []
        artist_names = [
            str(a.get("name") or "").strip()
            for a in raw_artists
            if isinstance(a, dict) and str(a.get("name") or "").strip()
        ]
        artist = ", ".join(artist_names) or "Unknown Artist"
        album_obj = item.get("album") or {}
        album = str(album_obj.get("name") or "").strip()

    try:
        progress_ms = max(0, int(payload.get("progress_ms") or 0))
    except (TypeError, ValueError):
        progress_ms = 0

    try:
        duration_ms = max(0, int(item.get("duration_ms") or 0))
    except (TypeError, ValueError):
        duration_ms = 0

    if duration_ms > 0:
        progress_ms = min(progress_ms, duration_ms)

    return {
        "is_playing": is_playing,
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "album": album,
        "progress_ms": progress_ms,
        "duration_ms": duration_ms,
    }


def _render_callback_html(
    *,
    success: bool,
    headline: str,
    detail: str,
) -> str:
    """Render a self-contained dark confirmation or error page for OAuth redirect."""
    accent = "#1ed760" if success else "#ff4d6d"
    badge = "CONNECTED" if success else "AUTH ERROR"
    safe_headline = html.escape(headline)
    safe_detail = html.escape(detail)
    auto_script = (
        """
        <script>
          (function () {
            if (window.opener && !window.opener.closed) {
              try {
                window.opener.postMessage({ type: 'spotify-oauth-success' }, '*');
              } catch (err) {}
              setTimeout(function () { window.close(); }, 1100);
            } else {
              setTimeout(function () { window.location.replace('/'); }, 1500);
            }
          })();
        </script>
        """
        if success
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>STANCE // HRZN-LINK — Spotify OAuth</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #020617;
      color: #f8fafc;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      padding: 24px;
    }}
    .card {{
      width: 100%;
      max-width: 440px;
      background: #000000;
      border: 1px solid {accent};
      border-radius: 12px;
      padding: 28px;
      box-shadow: 0 0 32px rgba(30, 215, 96, 0.14);
    }}
    .badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.14em;
      color: {accent};
      border: 1px solid {accent};
      border-radius: 4px;
      padding: 3px 8px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0 0 10px 0;
      font-size: 18px;
      letter-spacing: 0.04em;
    }}
    p {{
      margin: 0 0 20px 0;
      font-size: 13px;
      line-height: 1.5;
      color: #cbd5e1;
    }}
    a.btn {{
      display: inline-block;
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: #020617;
      background: {accent};
      padding: 10px 16px;
      border-radius: 8px;
    }}
  </style>
</head>
<body>
  <main class="card">
    <div class="badge">SPOTIFY // {badge}</div>
    <h1>{safe_headline}</h1>
    <p>{safe_detail}</p>
    <a class="btn" href="/">RETURN TO HRZN-LINK</a>
  </main>
  {auto_script}
</body>
</html>"""


class SpotifyPluginProvider(HudPluginProvider):
    """Live Spotify Web API Now Playing provider with OAuth 2.0 Authorization Code flow."""

    id = "spotify"
    name = "Spotify Now Playing"
    description = (
        "Live Spotify track title, artist, scrub progress bar, animated equalizer, "
        "and track-change auto-surface."
    )
    base_priority = 7
    default_dynamic_mode = "on_event"
    supports_on_event = True
    default_settings: dict[str, Any] = {
        "dynamicMode": "on_event",
        "userPriority": 7,
        "accentColor": "#1ed760",
        "clientId": "",
        "clientSecret": "",
        "redirectUri": DEFAULT_REDIRECT_URI,
        "showArtist": True,
        "showAlbum": False,
        "showProgressBar": True,
        "showTimeRemaining": True,
        "showEqualizer": True,
        "showCornerBrackets": True,
        "triggerOnTrackChange": True,
        "triggerOnPlayStart": True,
        "triggerWhilePlaying": True,
    }

    def __init__(self, start_poller: bool = True) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

        self._last_settings: Optional[dict[str, Any]] = None
        self._last_live_cfg: Optional[dict[str, Any]] = None
        self._pending_oauth_states: set[str] = set()

        self._tokens: Optional[dict[str, Any]] = self._load_tokens_from_disk()
        self._playback: dict[str, Any] = {
            "is_playing": False,
            "track_id": None,
            "title": None,
            "artist": None,
            "album": None,
            "progress_ms": 0,
            "duration_ms": 0,
            "poll_mono": 0.0,
            "last_poll_at": None,
            "error": None,
        }
        self._backoff_until: float = 0.0

        # Track change / play start baseline for evaluate()
        self._last_evaluated_track_id: Optional[str] = None
        self._last_evaluated_is_playing: bool = False

        self._poller_thread: Optional[threading.Thread] = None
        if start_poller:
            self._register_and_start_poller()

    def _tokens_path(self) -> Path:
        return _resolve_data_dir() / "spotify_tokens.json"

    def _load_tokens_from_disk(self) -> Optional[dict[str, Any]]:
        path = self._tokens_path()
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        if not (raw.get("access_token") or raw.get("refresh_token")):
            return None
        return raw

    def _save_tokens_to_disk(self, tokens: dict[str, Any]) -> None:
        path = self._tokens_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _delete_tokens_from_disk(self) -> None:
        path = self._tokens_path()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def _register_and_start_poller(self) -> None:
        """Stop any previous reloaded Spotify poller thread and start our daemon poller."""
        reg_mod = sys.modules.get("server.plugins.registry")
        if reg_mod is not None:
            prev_stop = getattr(reg_mod, "_spotify_poller_stop", None)
            prev_wake = getattr(reg_mod, "_spotify_poller_wake", None)
            if isinstance(prev_stop, threading.Event):
                prev_stop.set()
            if isinstance(prev_wake, threading.Event):
                prev_wake.set()
            setattr(reg_mod, "_spotify_poller_stop", self._stop_event)
            setattr(reg_mod, "_spotify_poller_wake", self._wake_event)

        thread = threading.Thread(
            target=self._poll_loop,
            name="spotify-poller",
            daemon=True,
        )
        self._poller_thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop background polling cleanly."""
        self._stop_event.set()
        self._wake_event.set()
        if self._poller_thread is not None and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=2.0)

    def _read_live_store_settings(self) -> Optional[dict[str, Any]]:
        for mod_name in ("server.main", "__main__"):
            mod = sys.modules.get(mod_name)
            candidate = getattr(mod, "state", None) if mod is not None else None
            store = getattr(candidate, "store", None) if candidate is not None else None
            cfg = getattr(store, "config", None) if store is not None else None
            plugin_configs = getattr(cfg, "plugin_configs", None) if cfg is not None else None
            if isinstance(plugin_configs, dict):
                spotify_cfg = plugin_configs.get(self.id) or plugin_configs.get("spotify")
                return dict(spotify_cfg) if isinstance(spotify_cfg, dict) else {}
        return None

    def _read_disk_settings(self) -> dict[str, Any]:
        cfg_path = _resolve_data_dir() / "config.json"
        if not cfg_path.is_file():
            return {}
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        plugin_configs = raw.get("plugin_configs") if isinstance(raw, dict) else None
        if isinstance(plugin_configs, dict):
            spotify_cfg = plugin_configs.get(self.id) or plugin_configs.get("spotify")
            if isinstance(spotify_cfg, dict):
                return dict(spotify_cfg)
        return {}

    def _resolve_saved_settings(self) -> dict[str, Any]:
        """Resolve latest user settings from live store, disk config, or evaluate cache."""
        merged = self.merge_settings(None)
        live_cfg = self._read_live_store_settings()

        with self._lock:
            last_settings = dict(self._last_settings) if self._last_settings is not None else None
            last_live = dict(self._last_live_cfg) if self._last_live_cfg is not None else None

            if live_cfg is not None:
                if last_settings is not None and last_live == live_cfg:
                    merged.update(live_cfg)
                    merged.update(last_settings)
                else:
                    self._last_live_cfg = dict(live_cfg)
                    merged.update(live_cfg)
                merged["redirectUri"] = _normalize_redirect_uri(merged.get("redirectUri"))
                return merged

        disk_cfg = self._read_disk_settings()
        if disk_cfg:
            merged.update(disk_cfg)
        if last_settings is not None:
            merged.update(last_settings)
        merged["redirectUri"] = _normalize_redirect_uri(merged.get("redirectUri"))
        return merged

    def _has_tokens(self) -> bool:
        with self._lock:
            if self._tokens is None:
                disk_tokens = self._load_tokens_from_disk()
                if disk_tokens is not None:
                    self._tokens = disk_tokens
            return bool(
                self._tokens
                and (self._tokens.get("access_token") or self._tokens.get("refresh_token"))
            )

    def _token_request(self, form_data: dict[str, str], client_id: str, client_secret: str) -> dict[str, Any]:
        """POST a token exchange or refresh request to Spotify Accounts API."""
        encoded_body = urlencode(form_data).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "STANCE-HRZN-LINK/1.0",
        }
        if client_id and client_secret:
            basic_raw = f"{client_id}:{client_secret}".encode("utf-8")
            basic_b64 = base64.b64encode(basic_raw).decode("ascii")
            headers["Authorization"] = f"Basic {basic_b64}"

        req = Request(SPOTIFY_TOKEN_URL, data=encoded_body, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ValueError("Spotify token response missing access_token")
        return payload

    def _store_token_payload(
        self,
        payload: dict[str, Any],
        existing_refresh_token: Optional[str] = None,
    ) -> dict[str, Any]:
        expires_in = 3600
        try:
            expires_in = max(60, int(payload.get("expires_in") or 3600))
        except (TypeError, ValueError):
            expires_in = 3600

        refresh_token = payload.get("refresh_token") or existing_refresh_token or ""
        token_record = {
            "access_token": str(payload.get("access_token") or ""),
            "refresh_token": str(refresh_token),
            "token_type": str(payload.get("token_type") or "Bearer"),
            "scope": str(payload.get("scope") or SPOTIFY_SCOPES),
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._tokens = token_record
        self._save_tokens_to_disk(token_record)
        return token_record

    def _refresh_access_token(self) -> bool:
        """Refresh the Spotify access token using the persisted refresh_token."""
        with self._lock:
            tokens = dict(self._tokens) if self._tokens else None
        if not tokens or not tokens.get("refresh_token"):
            return False

        settings = self._resolve_saved_settings()
        client_id = str(settings.get("clientId") or "").strip()
        client_secret = str(settings.get("clientSecret") or "").strip()
        if not client_id or not client_secret:
            with self._lock:
                self._playback["error"] = "Missing Client ID or Client Secret for token refresh."
            return False

        try:
            payload = self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": str(tokens["refresh_token"]),
                },
                client_id=client_id,
                client_secret=client_secret,
            )
            self._store_token_payload(payload, existing_refresh_token=str(tokens["refresh_token"]))
            with self._lock:
                self._playback["error"] = None
            return True
        except HTTPError as exc:
            detail = self._read_http_error(exc)
            with self._lock:
                self._playback["error"] = f"Token refresh failed ({exc.code}): {detail}"
                if exc.code in (400, 401) and "invalid_grant" in detail.lower():
                    self._tokens = None
                    self._delete_tokens_from_disk()
                    self._playback["is_playing"] = False
                    self._playback["track_id"] = None
                    self._playback["title"] = None
            return False
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            with self._lock:
                self._playback["error"] = f"Token refresh error: {exc}"
            return False

    @staticmethod
    def _read_http_error(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                err = parsed.get("error_description") or parsed.get("error")
                if isinstance(err, dict):
                    return str(err.get("message") or err)
                if err:
                    return str(err)
            return raw[:200]
        except Exception:
            return str(exc)

    def _poll_once(self) -> float:
        """Poll Spotify `currently-playing` once and return recommended sleep seconds."""
        if not self._has_tokens():
            return POLL_INTERVAL_IDLE_S

        now_mono = time.monotonic()
        with self._lock:
            backoff_remaining = self._backoff_until - now_mono
            tokens = dict(self._tokens) if self._tokens else None

        if backoff_remaining > 0:
            return min(backoff_remaining, 30.0)

        if not tokens:
            return POLL_INTERVAL_IDLE_S

        expires_at = float(tokens.get("expires_at") or 0.0)
        if not tokens.get("access_token") or (expires_at > 0 and time.time() >= expires_at - TOKEN_REFRESH_MARGIN_S):
            if not self._refresh_access_token():
                return ERROR_BACKOFF_S
            with self._lock:
                tokens = dict(self._tokens) if self._tokens else None
            if not tokens or not tokens.get("access_token"):
                return ERROR_BACKOFF_S

        for attempt in range(2):
            access_token = str(tokens.get("access_token") or "")
            req = Request(
                SPOTIFY_CURRENTLY_PLAYING_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "STANCE-HRZN-LINK/1.0",
                },
                method="GET",
            )
            try:
                with urlopen(req, timeout=6.0) as resp:
                    status_code = getattr(resp, "status", 200)
                    raw_body = resp.read().decode("utf-8") if status_code != 204 else ""

                now_utc = datetime.now(timezone.utc).isoformat()
                poll_mono = time.monotonic()

                if status_code == 204 or not raw_body.strip():
                    with self._lock:
                        self._playback.update(
                            {
                                "is_playing": False,
                                "track_id": None,
                                "title": None,
                                "artist": None,
                                "album": None,
                                "progress_ms": 0,
                                "duration_ms": 0,
                                "poll_mono": poll_mono,
                                "last_poll_at": now_utc,
                                "error": None,
                            }
                        )
                    return POLL_INTERVAL_IDLE_S

                payload = json.loads(raw_body)
                if not isinstance(payload, dict):
                    return POLL_INTERVAL_IDLE_S

                fields = _extract_track_fields(payload)
                with self._lock:
                    self._playback.update(fields)
                    self._playback["poll_mono"] = poll_mono
                    self._playback["last_poll_at"] = now_utc
                    self._playback["error"] = None
                return POLL_INTERVAL_PLAYING_S if fields["is_playing"] else POLL_INTERVAL_IDLE_S

            except HTTPError as exc:
                if exc.code == 401 and attempt == 0 and self._refresh_access_token():
                    with self._lock:
                        tokens = dict(self._tokens) if self._tokens else None
                    if tokens:
                        continue

                if exc.code == 429:
                    raw_retry = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        retry_s = max(1.0, min(120.0, float(raw_retry or 5.0)))
                    except (TypeError, ValueError):
                        retry_s = 5.0
                    with self._lock:
                        self._backoff_until = time.monotonic() + retry_s
                        self._playback["error"] = f"Rate limited by Spotify (retry in {int(retry_s)}s)"
                    return retry_s

                detail = self._read_http_error(exc)
                with self._lock:
                    self._backoff_until = time.monotonic() + ERROR_BACKOFF_S
                    self._playback["error"] = f"Spotify API error ({exc.code}): {detail}"
                return ERROR_BACKOFF_S

            except (URLError, TimeoutError, OSError, ValueError) as exc:
                with self._lock:
                    self._backoff_until = time.monotonic() + ERROR_BACKOFF_S
                    self._playback["error"] = f"Spotify poll failed: {exc}"
                return ERROR_BACKOFF_S

        return ERROR_BACKOFF_S

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            wait_s = POLL_INTERVAL_IDLE_S
            if self._has_tokens():
                try:
                    wait_s = self._poll_once()
                except Exception as exc:
                    with self._lock:
                        self._playback["error"] = f"Unexpected poller error: {exc}"
                    wait_s = ERROR_BACKOFF_S
            self._wake_event.wait(timeout=max(0.5, wait_s))
            self._wake_event.clear()

    def _compute_interpolated_progress_ms(
        self,
        playback: dict[str, Any],
        now_mono: Optional[float] = None,
    ) -> int:
        base_ms = max(0, int(playback.get("progress_ms") or 0))
        duration_ms = max(0, int(playback.get("duration_ms") or 0))
        if not playback.get("is_playing"):
            return min(base_ms, duration_ms) if duration_ms > 0 else base_ms

        poll_mono = float(playback.get("poll_mono") or 0.0)
        if poll_mono <= 0.0:
            return min(base_ms, duration_ms) if duration_ms > 0 else base_ms

        current_mono = time.monotonic() if now_mono is None else now_mono
        elapsed_ms = max(0.0, (current_mono - poll_mono) * 1000.0)
        interpolated = int(base_ms + elapsed_ms)
        return min(interpolated, duration_ms) if duration_ms > 0 else interpolated

    def _notify_main_layout_refresh(self) -> None:
        mod = sys.modules.get("server.main")
        state_obj = getattr(mod, "state", None) if mod is not None else None
        if state_obj is not None and hasattr(state_obj, "refresh_layout"):
            try:
                state_obj.refresh_layout()
            except Exception:
                pass

    def _clear_layout_hold(self, force: bool = False) -> None:
        """Clear hold cooldown on active LayoutEngine(s) so pausing hides Spotify immediately."""
        engines: list[Any] = []
        mod = sys.modules.get("server.main")
        state_obj = getattr(mod, "state", None) if mod is not None else None
        main_engine = getattr(state_obj, "layout_engine", None) if state_obj is not None else None
        if main_engine is not None:
            engines.append(main_engine)

        frame = inspect.currentframe()
        try:
            cursor = frame.f_back if frame is not None else None
            while cursor is not None:
                local_self = cursor.f_locals.get("self")
                if (
                    local_self is not None
                    and local_self not in engines
                    and hasattr(local_self, "_last_triggered_at")
                    and hasattr(local_self, "_test_triggered_at")
                ):
                    engines.append(local_self)
                cursor = cursor.f_back
        finally:
            del frame

        for engine in engines:
            last_map = getattr(engine, "_last_triggered_at", None)
            test_map = getattr(engine, "_test_triggered_at", None)
            if not isinstance(last_map, dict):
                continue
            last_ts = last_map.get(self.id)
            if last_ts is None:
                continue
            test_ts = test_map.get(self.id) if isinstance(test_map, dict) else None
            if force or test_ts is None or last_ts != test_ts:
                last_map.pop(self.id, None)
                if force and isinstance(test_map, dict):
                    test_map.pop(self.id, None)

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        _ = now
        _ensure_plugin_routes_before_catchall()
        merged = self.merge_settings(settings)
        authenticated = self._has_tokens()
        configured = bool(
            str(merged.get("clientId") or "").strip()
            and str(merged.get("clientSecret") or "").strip()
        )

        trigger_on_track_change = bool(merged.get("triggerOnTrackChange", True))
        trigger_on_play_start = bool(merged.get("triggerOnPlayStart", True))
        trigger_while_playing = bool(merged.get("triggerWhilePlaying", True))

        with self._lock:
            self._last_settings = dict(merged)
            playback = dict(self._playback)
            progress_ms = self._compute_interpolated_progress_ms(playback)
            duration_ms = max(0, int(playback.get("duration_ms") or 0))
            is_playing = bool(authenticated and playback.get("is_playing"))
            track_id = playback.get("track_id") if authenticated else None
            title = playback.get("title") if authenticated else None
            artist = playback.get("artist") if authenticated else None
            album = playback.get("album") if authenticated else None

            prev_track_id = self._last_evaluated_track_id
            prev_is_playing = self._last_evaluated_is_playing

            track_changed = (
                is_playing
                and bool(track_id)
                and prev_track_id is not None
                and track_id != prev_track_id
            )
            play_started = is_playing and (not prev_is_playing)
            paused_or_stopped = prev_is_playing and (not is_playing)

            self._last_evaluated_is_playing = is_playing
            if track_id is not None:
                self._last_evaluated_track_id = str(track_id)
            elif not authenticated:
                self._last_evaluated_track_id = None

        if trigger_while_playing and not is_playing:
            self._clear_layout_hold(force=paused_or_stopped)

        active_reasons: list[str] = []
        track_label = f"{title} — {artist}" if (title and artist) else (title or "Track")
        if trigger_on_track_change and track_changed:
            active_reasons.append(f"Track changed: {track_label}")
        if trigger_on_play_start and play_started:
            active_reasons.append(f"Playback started: {track_label}")
        if trigger_while_playing and is_playing and not active_reasons:
            active_reasons.append(f"Playing: {track_label}")

        event_triggered = len(active_reasons) > 0
        if event_triggered:
            reason = " · ".join(active_reasons)
        elif not authenticated:
            reason = "Spotify auth required"
        elif is_playing and title:
            reason = f"Playing: {track_label}"
        elif title:
            reason = f"Paused: {track_label}"
        else:
            reason = "Spotify idle"

        progress_pct = round((progress_ms / duration_ms) * 100.0, 2) if duration_ms > 0 else 0.0

        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=event_triggered,
            reason=reason,
            data={
                "authenticated": authenticated,
                "configured": configured,
                "is_playing": is_playing,
                "track_id": track_id,
                "title": title,
                "artist": artist,
                "album": album,
                "progress_ms": progress_ms,
                "duration_ms": duration_ms,
                "progress_pct": progress_pct,
                "event_triggered": event_triggered,
                "fetched_at": playback.get("last_poll_at"),
                "error": playback.get("error"),
            },
        )

    def get_router(self) -> APIRouter:
        """Expose OAuth and connection status routes mounted at `/api/plugins/spotify`."""
        timer = threading.Timer(0.02, _ensure_plugin_routes_before_catchall)
        timer.daemon = True
        timer.start()

        router = APIRouter()

        @router.get("/auth/url")
        async def get_auth_url(
            client_id: Optional[str] = None,
            redirect_uri: Optional[str] = None,
        ) -> dict[str, Any]:
            settings = self._resolve_saved_settings()
            resolved_client_id = str(client_id or settings.get("clientId") or "").strip()
            resolved_redirect_uri = _normalize_redirect_uri(
                redirect_uri or settings.get("redirectUri")
            )

            if not resolved_client_id:
                raise HTTPException(
                    status_code=400,
                    detail="Spotify Client ID is not configured. Save your Client ID first.",
                )

            oauth_state = secrets.token_urlsafe(16)
            with self._lock:
                if len(self._pending_oauth_states) > 32:
                    self._pending_oauth_states.clear()
                self._pending_oauth_states.add(oauth_state)

            params = urlencode(
                {
                    "client_id": resolved_client_id,
                    "response_type": "code",
                    "redirect_uri": resolved_redirect_uri,
                    "scope": SPOTIFY_SCOPES,
                    "state": oauth_state,
                }
            )
            auth_url = f"{SPOTIFY_AUTH_URL}?{params}"
            return {
                "url": auth_url,
                "auth_url": auth_url,
                "redirect_uri": resolved_redirect_uri,
                "scope": SPOTIFY_SCOPES,
            }

        @router.get("/callback", response_class=HTMLResponse)
        async def oauth_callback(
            code: Optional[str] = None,
            error: Optional[str] = None,
            state: Optional[str] = None,
        ) -> HTMLResponse:
            if error:
                return HTMLResponse(
                    content=_render_callback_html(
                        success=False,
                        headline="Spotify Authorization Cancelled",
                        detail=f"Spotify returned an error: {error}",
                    ),
                    status_code=400,
                )

            if not code:
                return HTMLResponse(
                    content=_render_callback_html(
                        success=False,
                        headline="Missing Authorization Code",
                        detail="No authorization code was included in the Spotify callback URL.",
                    ),
                    status_code=400,
                )

            if state:
                with self._lock:
                    self._pending_oauth_states.discard(state)

            settings = self._resolve_saved_settings()
            client_id = str(settings.get("clientId") or "").strip()
            client_secret = str(settings.get("clientSecret") or "").strip()
            redirect_uri = _normalize_redirect_uri(settings.get("redirectUri"))

            if not client_id or not client_secret:
                return HTMLResponse(
                    content=_render_callback_html(
                        success=False,
                        headline="Spotify Credentials Missing",
                        detail=(
                            "Client ID and Client Secret must be saved in Spotify plugin settings "
                            "before completing authorization."
                        ),
                    ),
                    status_code=400,
                )

            def _exchange_code() -> dict[str, Any]:
                return self._token_request(
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    client_id=client_id,
                    client_secret=client_secret,
                )

            try:
                token_payload = await asyncio.to_thread(_exchange_code)
            except HTTPError as exc:
                detail = self._read_http_error(exc)
                return HTMLResponse(
                    content=_render_callback_html(
                        success=False,
                        headline="Token Exchange Failed",
                        detail=f"Spotify token endpoint returned HTTP {exc.code}: {detail}",
                    ),
                    status_code=502,
                )
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                return HTMLResponse(
                    content=_render_callback_html(
                        success=False,
                        headline="Token Exchange Error",
                        detail=f"Unable to reach Spotify token endpoint: {exc}",
                    ),
                    status_code=502,
                )

            self._store_token_payload(token_payload)
            with self._lock:
                self._backoff_until = 0.0
                self._playback["error"] = None
            self._wake_event.set()
            await asyncio.to_thread(self._poll_once)
            self._notify_main_layout_refresh()

            return HTMLResponse(
                content=_render_callback_html(
                    success=True,
                    headline="Spotify Linked to HRZN-LINK",
                    detail="Authorization complete. Live playback telemetry is now active; this window will close automatically.",
                ),
                status_code=200,
            )

        @router.get("/status")
        async def get_status() -> dict[str, Any]:
            settings = self._resolve_saved_settings()
            configured = bool(
                str(settings.get("clientId") or "").strip()
                and str(settings.get("clientSecret") or "").strip()
            )
            authenticated = self._has_tokens()
            with self._lock:
                playback = dict(self._playback)
                progress_ms = self._compute_interpolated_progress_ms(playback)
                duration_ms = max(0, int(playback.get("duration_ms") or 0))
            return {
                "authenticated": authenticated,
                "configured": configured,
                "redirect_uri": _normalize_redirect_uri(settings.get("redirectUri")),
                "is_playing": bool(authenticated and playback.get("is_playing")),
                "track_id": playback.get("track_id") if authenticated else None,
                "title": playback.get("title") if authenticated else None,
                "artist": playback.get("artist") if authenticated else None,
                "album": playback.get("album") if authenticated else None,
                "progress_ms": progress_ms if authenticated else 0,
                "duration_ms": duration_ms if authenticated else 0,
                "last_poll_at": playback.get("last_poll_at"),
                "error": playback.get("error"),
            }

        @router.post("/disconnect")
        async def disconnect() -> dict[str, Any]:
            with self._lock:
                self._tokens = None
                self._backoff_until = 0.0
                self._last_evaluated_track_id = None
                self._last_evaluated_is_playing = False
                self._playback.update(
                    {
                        "is_playing": False,
                        "track_id": None,
                        "title": None,
                        "artist": None,
                        "album": None,
                        "progress_ms": 0,
                        "duration_ms": 0,
                        "poll_mono": 0.0,
                        "last_poll_at": None,
                        "error": None,
                    }
                )
            self._delete_tokens_from_disk()
            self._notify_main_layout_refresh()
            return {"authenticated": False, "status": "disconnected"}

        return router


Provider = SpotifyPluginProvider
