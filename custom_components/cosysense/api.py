"""Async client for the Cosysense customer API.

Auth is a Cognito refresh token exchanged for a short-lived ID token with
REFRESH_TOKEN_AUTH, the same call the Cosysense Python SDK makes. The
coordinator refreshes on every poll, so a disabled user or a revoked token
fails at the next poll. Tokens are never logged.
"""
from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import DEFAULT_REGION

TIMEOUT = aiohttp.ClientTimeout(total=30)


class CosysenseError(Exception):
    """The API could not be reached or answered with an error."""


class CosysenseAuthError(CosysenseError):
    """The credentials were rejected, or the site is no longer granted."""


class CosysenseApi:
    """Reads one Cosysense account's sites, sensors and readings."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        client_id: str,
        refresh_token: str,
        base_url: str,
        region: str = DEFAULT_REGION,
        user_agent: str = "HomeAssistant-Cosysense",
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._base_url = base_url.rstrip("/")
        self._cognito = f"https://cognito-idp.{region}.amazonaws.com/"
        self._user_agent = user_agent
        self._id_token: str | None = None

    def __repr__(self) -> str:
        return f"CosysenseApi(base_url={self._base_url!r}, credentials=<redacted>)"

    async def refresh(self) -> None:
        """Exchange the refresh token for a fresh ID token."""
        body = json.dumps({
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": self._client_id,
            "AuthParameters": {"REFRESH_TOKEN": self._refresh_token},
        })
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        }
        try:
            async with self._session.post(self._cognito, data=body, headers=headers, timeout=TIMEOUT) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CosysenseError(f"could not reach the sign-in service: {type(err).__name__}") from None
        try:
            payload = json.loads(text) if text else {}
        except ValueError:
            payload = {}
        if status == 400 and payload.get("__type", "").endswith(
            ("NotAuthorizedException", "UserNotFoundException", "ResourceNotFoundException",
             "InvalidParameterException")
        ):
            raise CosysenseAuthError("the refresh token was rejected; it may be expired or revoked")
        if status != 200:
            raise CosysenseError(f"sign-in service answered HTTP {status}")
        token = (payload.get("AuthenticationResult") or {}).get("IdToken")
        if not token:
            raise CosysenseError("sign-in service returned no ID token")
        self._id_token = token

    async def id_token(self) -> str:
        """A fresh ID token, for the push connection's password."""
        await self.refresh()
        assert self._id_token is not None
        return self._id_token

    async def _get(self, path: str) -> Any:
        if self._id_token is None:
            await self.refresh()
        headers = {
            "Authorization": f"Bearer {self._id_token}",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        try:
            async with self._session.get(f"{self._base_url}{path}", headers=headers, timeout=TIMEOUT) as resp:
                if resp.status in (401, 403, 404):
                    raise CosysenseAuthError(f"access refused (HTTP {resp.status}) for {path}")
                if resp.status != 200:
                    raise CosysenseError(f"Cosysense answered HTTP {resp.status} for {path}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CosysenseError(f"could not reach Cosysense: {type(err).__name__}") from None

    async def sites(self) -> list[dict[str, str]]:
        """Sites this account can read, as {site_uuid, name}."""
        meta = await self._get("/api/dashboard/meta")
        return [
            {"site_uuid": s["siteUUID"], "name": s.get("name") or s["siteUUID"]}
            for s in meta.get("sites", [])
            if s.get("siteUUID")
        ]

    async def sensors(self, site_uuid: str) -> dict[str, Any]:
        """Equipment and points of one site."""
        return await self._get(f"/api/sites/{site_uuid}/sensors")

    async def readings(self, site_uuid: str) -> dict[str, Any]:
        """Latest value per point of one site."""
        return await self._get(f"/api/sites/{site_uuid}/readings")
