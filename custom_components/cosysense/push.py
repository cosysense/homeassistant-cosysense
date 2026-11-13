"""Live readings pushed over MQTT (AWS IoT Core), when the site has push on.

The sensors route names the broker, the custom authorizer and the site's topic.
One connection per site: TLS on port 443 with ALPN "mqtt", the authorizer named
in the username and the Cognito ID token as the password. The broker drops the
session after an hour, and we reconnect sooner with a fresh token, so a revoked
user stops receiving within the hour. Each message lists the points that changed:
{"readings": [{"stream_id", "value", "updated_at"}]}.

paho-mqtt runs its network loop in its own thread; every callback hops back to
the event loop. While connected, the coordinator only polls hourly to reconcile.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import ssl
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant

from .api import CosysenseApi, CosysenseError

_LOGGER = logging.getLogger(__name__)

PORT = 443
KEEPALIVE = 300
SESSION = 50 * 60  # reconnect with a fresh token before the broker's 60 min cut
BACKOFF_MIN, BACKOFF_MAX = 30, 15 * 60


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.set_alpn_protocols(["mqtt"])
    return ctx


class CosysensePush:
    """Keeps one MQTT subscription to a site's readings topic alive."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CosysenseApi,
        config: dict[str, Any],
        client_tag: str,
        on_readings: Callable[[list[dict[str, Any]]], None],
        on_connected: Callable[[bool], None],
    ) -> None:
        self._hass = hass
        self._api = api
        self._host = config["host"]
        self._authorizer = config["authorizer"]
        self._topic = config["topic"]
        self._client_tag = client_tag[:40]
        self._on_readings = on_readings
        self._on_connected = on_connected
        self._task: asyncio.Task | None = None
        self.connected = False
        self.messages = 0

    def start(self) -> None:
        self._task = self._hass.async_create_background_task(self._run(), "cosysense push")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _set_connected(self, value: bool) -> None:
        if value != self.connected:
            self.connected = value
            self._on_connected(value)

    def _message(self, payload: bytes) -> None:
        try:
            readings = json.loads(payload).get("readings")
        except (ValueError, AttributeError):
            _LOGGER.debug("ignored a malformed push message")
            return
        if isinstance(readings, list):
            self.messages += 1
            self._on_readings(readings)

    async def _run(self) -> None:
        backoff = BACKOFF_MIN
        while True:
            client = None
            try:
                token = await self._api.id_token()
                client, closed = await self._connect(token)
                backoff = BACKOFF_MIN
                try:
                    await asyncio.wait_for(closed.wait(), SESSION)
                    _LOGGER.debug("push connection closed by the broker")
                except TimeoutError:
                    pass  # planned reconnect with a fresh token
            except asyncio.CancelledError:
                raise
            except (CosysenseError, OSError, ConnectionError, TimeoutError) as err:
                _LOGGER.info("push unavailable, polling instead: %s", err)
                self._set_connected(False)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue
            finally:
                if client is not None:
                    await self._hass.async_add_executor_job(self._close, client)
            self._set_connected(False)

    async def _connect(self, token: str):
        """Connect and subscribe; returns (client, event set when the link drops)."""
        import paho.mqtt.client as mqtt  # imported lazily: only push users load it

        loop = self._hass.loop
        closed = asyncio.Event()
        ready: asyncio.Future = loop.create_future()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                loop.call_soon_threadsafe(_resolve, ConnectionError(f"broker refused: {reason_code}"))
                return
            client.subscribe(self._topic, qos=0)

        def on_subscribe(client, userdata, mid, reason_codes, properties):
            failed = any(rc.is_failure for rc in reason_codes)
            loop.call_soon_threadsafe(_resolve, ConnectionError("subscription refused") if failed else None)

        def on_message(client, userdata, msg):
            loop.call_soon_threadsafe(self._message, msg.payload)

        def on_disconnect(client, userdata, flags, reason_code, properties):
            loop.call_soon_threadsafe(_resolve, ConnectionError(f"disconnected: {reason_code}"))
            loop.call_soon_threadsafe(closed.set)

        def _resolve(err: Exception | None) -> None:
            if not ready.done():
                ready.set_exception(err) if err else ready.set_result(None)

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"cosysense-ha-{self._client_tag}-{secrets.token_hex(4)}",
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(f"homeassistant?x-amz-customauthorizer-name={self._authorizer}", token)
        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        def blocking_connect() -> None:
            client.tls_set_context(_tls_context())
            client.connect(self._host, PORT, keepalive=KEEPALIVE)
            client.loop_start()

        await self._hass.async_add_executor_job(blocking_connect)
        try:
            await asyncio.wait_for(ready, 30)
        except BaseException:
            await self._hass.async_add_executor_job(self._close, client)
            raise
        self._set_connected(True)
        return client, closed

    @staticmethod
    def _close(client) -> None:
        try:
            client.disconnect()
        finally:
            client.loop_stop()
