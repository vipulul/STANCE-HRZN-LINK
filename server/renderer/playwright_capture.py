"""Headless Chromium (Playwright) capture manager for the bare `/hud-render` route."""

from __future__ import annotations

import asyncio
import io
import os
import sys
import threading
import time
from typing import Any, Optional

from PIL import Image


def _with_headless_query(url: str) -> str:
    if "headless=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}headless=1"


class PlaywrightHudCapture:
    """Manages a headless Chromium page on a dedicated ProactorEventLoop worker thread."""

    def __init__(
        self,
        render_url: Optional[str] = None,
        retry_cooldown_s: float = 3.0,
    ) -> None:
        port = int(os.getenv("HRZN_PORT", "8080"))
        env_url = os.getenv("HRZN_RENDER_URL")
        primary = render_url or env_url or f"http://127.0.0.1:{port}/hud-render"
        self.render_url = _with_headless_query(primary)
        self._candidate_urls = [self.render_url]
        if not render_url and not env_url:
            vite_url = "http://127.0.0.1:5173/hud-render?headless=1"
            if vite_url not in self._candidate_urls:
                self._candidate_urls.append(vite_url)

        self._retry_cooldown_s = retry_cooldown_s
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._viewport: tuple[int, int] = (0, 0)
        self._page_ready: bool = False
        self._last_attempt_ts: float = 0.0
        self.last_error: Optional[str] = None
        self.disabled: bool = False

        self._thread_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_ready = threading.Event()
        self._worker_async_lock: Optional[asyncio.Lock] = None

    @property
    def is_ready(self) -> bool:
        """True when Playwright Chromium has loaded `/hud-render` and is actively capturing."""
        return self._page is not None and self._page_ready and not self.disabled

    def _run_worker_loop(self) -> None:
        if sys.platform == "win32":
            loop: asyncio.AbstractEventLoop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._worker_loop = loop
        self._worker_async_lock = asyncio.Lock()
        self._worker_ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def _ensure_worker_loop(self) -> asyncio.AbstractEventLoop:
        with self._thread_lock:
            if (
                self._worker_loop is None
                or self._worker_loop.is_closed()
                or self._worker_thread is None
                or not self._worker_thread.is_alive()
            ):
                self._worker_ready.clear()
                self._worker_thread = threading.Thread(
                    target=self._run_worker_loop,
                    name="hrzn-playwright-worker",
                    daemon=True,
                )
                self._worker_thread.start()
        if not self._worker_ready.wait(timeout=5.0) or self._worker_loop is None:
            raise RuntimeError("Timed out starting Playwright worker event loop")
        return self._worker_loop

    async def _ensure_browser(self, width: int, height: int) -> bool:
        if self.disabled:
            return False

        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                ],
            )

        if self._context is None:
            self._context = await self._browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            self._viewport = (width, height)

        if self._page is None:
            self._page = await self._context.new_page()
            self._page_ready = False

        if self._viewport != (width, height):
            await self._page.set_viewport_size({"width": width, "height": height})
            self._viewport = (width, height)

        if not self._page_ready:
            last_exc: Optional[Exception] = None
            loaded = False
            for url in self._candidate_urls:
                try:
                    response = await self._page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=8000,
                    )
                    if response is None or response.status >= 400:
                        status = response.status if response else "no-response"
                        raise RuntimeError(f"GET {url} returned {status}")

                    await self._page.wait_for_selector("#hud-render-root", timeout=5000)
                    await self._page.evaluate(
                        "() => (document.fonts ? document.fonts.ready : Promise.resolve())"
                    )
                    loaded = True
                    break
                except Exception as exc:
                    last_exc = exc

            if not loaded:
                raise last_exc or RuntimeError("Unable to load /hud-render in headless Chromium")

            self._page_ready = True
            self.last_error = None

        return True

    async def _capture_frame_on_worker(
        self,
        width: int,
        height: int,
        state_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[Image.Image]:
        if self.disabled or self._worker_async_lock is None:
            return None

        async with self._worker_async_lock:
            now = time.monotonic()
            if not self._page_ready and (now - self._last_attempt_ts) < self._retry_cooldown_s:
                return None

            try:
                self._last_attempt_ts = now
                ready = await self._ensure_browser(width, height)
                if not ready or self._page is None:
                    return None

                if state_payload is not None:
                    await self._page.evaluate(
                        """async (payload) => {
                            if (typeof window.__HRZN_APPLY_STATE__ === 'function') {
                                await window.__HRZN_APPLY_STATE__(payload);
                            }
                            return new Promise((resolve) =>
                                requestAnimationFrame(() => requestAnimationFrame(resolve))
                            );
                        }""",
                        state_payload,
                    )

                png_bytes = await self._page.screenshot(
                    type="png",
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                )
                with Image.open(io.BytesIO(png_bytes)) as img:
                    return img.convert("RGB")
            except Exception as exc:
                self.last_error = str(exc)
                self._page_ready = False
                if self._page is not None:
                    try:
                        await self._page.close()
                    except Exception:
                        pass
                    self._page = None
                return None

    async def capture_frame(
        self,
        width: int,
        height: int,
        state_payload: Optional[dict[str, Any]] = None,
    ) -> Optional[Image.Image]:
        """Synchronize HUD state into `/hud-render` and capture an RGB frame."""
        if self.disabled:
            return None

        try:
            loop = self._ensure_worker_loop()
            future = asyncio.run_coroutine_threadsafe(
                self._capture_frame_on_worker(width, height, state_payload),
                loop,
            )
            return await asyncio.wrap_future(future)
        except Exception as exc:
            self.last_error = str(exc)
            return None

    async def _stop_on_worker(self) -> None:
        if self._worker_async_lock is not None:
            async with self._worker_async_lock:
                await self._close_resources()
        else:
            await self._close_resources()

    async def _close_resources(self) -> None:
        self._page_ready = False
        for resource in (self._page, self._context, self._browser):
            if resource is not None:
                try:
                    await resource.close()
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def stop(self) -> None:
        """Close the headless Chromium page, browser, Playwright driver, and worker thread."""
        with self._thread_lock:
            loop = self._worker_loop
            thread = self._worker_thread

        if loop is not None and not loop.is_closed() and loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._stop_on_worker(), loop)
                await asyncio.wrap_future(fut)
            except Exception:
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)

        with self._thread_lock:
            self._worker_loop = None
            self._worker_thread = None
            self._worker_async_lock = None
