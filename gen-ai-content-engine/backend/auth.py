"""
Firebase Authentication — backend verification.

Verifies the Firebase ID token sent by the frontend as `Authorization: Bearer <token>`
and exposes `get_current_user` as a FastAPI dependency.

Verification path (first that applies):
  1. firebase-admin  — if FIREBASE_SERVICE_ACCOUNT_JSON / _PATH / GOOGLE_APPLICATION_CREDENTIALS
  2. google-auth     — if only FIREBASE_PROJECT_ID is set (no service account needed to
                       *verify* an ID token; checks Google's public keys + audience)
  3. dev-bypass      — no config at all: requests pass as a synthetic dev user

`AUTH_REQUIRED=true` makes a missing/invalid token a 401/503 instead of dev-bypass.
Even with AUTH_REQUIRED=false, a real Bearer token that IS present is still verified.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request

AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "").lower() in ("1", "true", "yes")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "").strip()

_DEV_USER = {"uid": "dev-user", "email": "dev@local", "dev": True}


@lru_cache(maxsize=1)
def _init_firebase_admin() -> bool:
    """Initialise firebase-admin once. Returns True only if a service account was found."""
    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    sa_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

    if not (sa_json or sa_path or gac):
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            return True
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
        elif sa_path:
            cred = credentials.Certificate(sa_path)
        else:
            cred = credentials.ApplicationDefault()
        opts = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
        firebase_admin.initialize_app(cred, opts)
        print("[auth] firebase-admin initialised — full ID-token verification.")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] firebase-admin init failed ({exc}).")
        return False


@lru_cache(maxsize=1)
def _auth_mode() -> str:
    if _init_firebase_admin():
        return "firebase-admin"
    if FIREBASE_PROJECT_ID:
        print(f"[auth] Verifying ID tokens via google-auth (project={FIREBASE_PROJECT_ID!r}).")
        return "google-auth"
    print("[auth] No Firebase config — dev-bypass mode.")
    return "dev-bypass"


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def _verify_firebase_admin(token: str) -> dict:
    from firebase_admin import auth as fb_auth

    decoded = fb_auth.verify_id_token(token)
    return {"uid": decoded["uid"], "email": decoded.get("email"), "name": decoded.get("name")}


def _verify_google_auth(token: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    decoded = google_id_token.verify_firebase_token(
        token, google_requests.Request(), audience=FIREBASE_PROJECT_ID
    )
    if not decoded:
        raise ValueError("Token did not verify against Firebase public keys.")
    uid = decoded.get("user_id") or decoded.get("sub") or decoded.get("uid")
    if not uid:
        raise ValueError("Token has no subject.")
    return {"uid": uid, "email": decoded.get("email"), "name": decoded.get("name")}


def get_current_user(request: Request) -> dict:
    """FastAPI dependency — returns {uid, email, name}. 401 on an invalid token;
    dev-bypass user when no token and auth isn't enforced."""
    mode = _auth_mode()
    token = _bearer_token(request)

    if not token:
        if AUTH_REQUIRED:
            raise HTTPException(status_code=401, detail="Missing bearer token.")
        if mode == "dev-bypass":
            return dict(_DEV_USER)
        # Auth is available but the caller sent no token and isn't forcing it.
        return dict(_DEV_USER)

    if mode == "dev-bypass":
        # A token was sent but we can't verify it; don't trust it.
        if AUTH_REQUIRED:
            raise HTTPException(status_code=503, detail="Auth required but Firebase is not configured.")
        return dict(_DEV_USER)

    try:
        if mode == "firebase-admin":
            return _verify_firebase_admin(token)
        return _verify_google_auth(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc


CurrentUser = Depends(get_current_user)
