import time
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from contracts.auth.v1 import auth_pb2 as pb
from gateway.config import Settings
from gateway.dependencies import AnonCtx, AppSettings, Clients
from gateway.errors import ApiError
from gateway.rate_limit import rate_limit
from gateway.schemas.auth import AuthOut, LoginIn, RegisterIn, TokenOut, UserOut
from gateway.schemas.common import ERRORS

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], responses=ERRORS)

REFRESH_COOKIE = "refresh_token"
login_limit = rate_limit("login", lambda s: (s.login_rate_limit, s.login_rate_window_seconds))
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, settings: Settings, tokens: pb.TokenPair) -> None:
    """Refresh-токен живёт только в HttpOnly cookie — JS фронта его не видит."""
    max_age = max(1, tokens.refresh_expires_at.seconds - int(time.time()))
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.refresh_cookie_path,
    )


def _auth_out(user: pb.User, tokens: pb.TokenPair) -> AuthOut:
    base = TokenOut.from_pb(tokens)
    return AuthOut(**base.model_dump(), user=UserOut.from_pb(user))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, response: Response, ctx: AnonCtx, clients: Clients, settings: AppSettings
) -> AuthOut:
    resp = await clients.auth.Register(
        pb.RegisterRequest(context=ctx, email=body.email, name=body.name, password=body.password)
    )
    _set_refresh_cookie(response, settings, resp.tokens)
    return _auth_out(resp.user, resp.tokens)


@router.post("/login", dependencies=[Depends(login_limit)])
async def login(
    body: LoginIn, response: Response, ctx: AnonCtx, clients: Clients, settings: AppSettings
) -> AuthOut:
    resp = await clients.auth.Login(
        pb.LoginRequest(context=ctx, email=body.email, password=body.password)
    )
    _set_refresh_cookie(response, settings, resp.tokens)
    return _auth_out(resp.user, resp.tokens)


@router.post("/refresh")
async def refresh(
    response: Response,
    ctx: AnonCtx,
    clients: Clients,
    settings: AppSettings,
    refresh_token: RefreshCookie = None,
) -> TokenOut:
    if not refresh_token:
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "Refresh cookie is missing")
    resp = await clients.auth.Refresh(pb.RefreshRequest(context=ctx, refresh_token=refresh_token))
    _set_refresh_cookie(response, settings, resp.tokens)
    return TokenOut.from_pb(resp.tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    ctx: AnonCtx,
    clients: Clients,
    settings: AppSettings,
    refresh_token: RefreshCookie = None,
) -> None:
    if refresh_token:
        await clients.auth.Logout(pb.LogoutRequest(context=ctx, refresh_token=refresh_token))
    response.delete_cookie(REFRESH_COOKIE, path=settings.refresh_cookie_path)
