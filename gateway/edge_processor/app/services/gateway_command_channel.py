from __future__ import annotations

import json
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.settings import RuntimeSettings

try:
    from websockets.asyncio.client import connect
except ImportError:  # pragma: no cover
    from websockets.client import connect  # type: ignore[no-redef]


class GatewayCommandChannel:
    """Listen for backend command-ready notifications over WebSocket."""

    def __init__(self, settings: RuntimeSettings) -> None:
        """Create a command channel client.

        :param settings: Runtime settings containing backend command WebSocket config.
        """
        self._settings = settings

    async def listen(self, on_command_ready) -> None:
        """Run the command notification loop until the WebSocket disconnects.

        :param on_command_ready: Awaitable callback that pulls pending commands.
            It is invoked once after connecting and again for matching
            ``command_ready`` messages.
        :return: This coroutine returns only when the connection closes or fails.
        :raises RuntimeError: If the shared gateway command token is missing.
        """
        token = self._settings.backend.gateway_command_channel_token
        if not token:
            raise RuntimeError("gateway command channel token is not configured")

        async with connect(self._build_ws_url()) as websocket:
            await on_command_ready()
            async for raw_message in websocket:
                if not isinstance(raw_message, str):
                    continue
                try:
                    payload = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") != "command_ready":
                    continue
                data = payload.get("data", {})
                if isinstance(data, dict) and data.get("gateway_id") != self._settings.gateway_id:
                    continue
                await on_command_ready()

    def _build_ws_url(self) -> str:
        """Build the backend command WebSocket URL with the shared token."""
        backend = self._settings.backend
        base_url = urlsplit(backend.base_url)
        scheme = "wss" if base_url.scheme == "https" else "ws"
        path = (
            base_url.path.rstrip("/")
            + backend.gateway_command_ws_path.format(gateway_id=self._settings.gateway_id)
        )
        query = urlencode({"token": backend.gateway_command_channel_token or ""})
        return urlunsplit((scheme, base_url.netloc, path, query, ""))
