from functools import lru_cache

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

KEYCLOAK_ISSUER = "https://keycloak.example.com/realms/cyberdefense"
JWKS_URL = f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
AUDIENCE = "cyber-multi-agent"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token", auto_error=False)


@lru_cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)


async def verify_token(token: str | None = Depends(oauth2_scheme)) -> dict:
    if settings.dev_disable_auth:
        # Local dev only -- grants every role so you can exercise all endpoints, including
        # the soc-lead-gated approval endpoint, without a real Keycloak realm running.
        return {
            "sub": settings.dev_fake_user_sub,
            "realm_access": {"roles": ["soc-analyst", "soc-lead", "admin"]},
        }

    if not token:
        raise HTTPException(401, "Missing bearer token")

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=AUDIENCE, issuer=KEYCLOAK_ISSUER)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    return payload


def require_role(role: str):
    async def checker(payload: dict = Depends(verify_token)) -> dict:
        roles = payload.get("realm_access", {}).get("roles", [])
        if role not in roles:
            raise HTTPException(403, f"Requires role: {role}")
        return payload
    return checker