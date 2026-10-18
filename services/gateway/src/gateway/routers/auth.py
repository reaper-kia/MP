import time
from typing import Annotated

from auth.v1 import auth_service_pb2 as pb
from fastapi import APIRouter, Cookie, Response, status

from gateway.config import Settings
from gateway.dependencies import AnonCtx, AppSettings, Clients
from gateway.errors import ApiError
from gateway.schemas.auth import AuthOut, LoginIn, RegisterIn, TokenOut, UserOut
from gateway.schemas.common import ERRORS, ts

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], responses=ERRORS)

# refresh-токен живёт только в HttpOnly cookie — JS фронта его не видит
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def set_refresh_cookie(response: Response, settings: Settings, tokens: pb.TokenPair) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max(1, tokens.refresh_expires_at.seconds - int(time.time())),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def token_out(tokens: pb.TokenPair) -> TokenOut:
    return TokenOut(
        access_token=tokens.access_token, access_expires_at=ts(tokens.access_expires_at)
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, response: Response, ctx: AnonCtx, clients: Clients, settings: AppSettings
) -> AuthOut:
    result = await clients.auth.Register(
        pb.RegisterRequest(context=ctx, email=body.email, name=body.name, password=body.password)
    )
    set_refresh_cookie(response, settings, result.tokens)
    return AuthOut(**token_out(result.tokens).model_dump(), user=UserOut.from_proto(result.user))


@router.post("/login")
async def login(
    body: LoginIn, response: Response, ctx: AnonCtx, clients: Clients, settings: AppSettings
) -> AuthOut:
    result = await clients.auth.Login(
        pb.LoginRequest(context=ctx, email=body.email, password=body.password)
    )
    set_refresh_cookie(response, settings, result.tokens)
    return AuthOut(**token_out(result.tokens).model_dump(), user=UserOut.from_proto(result.user))


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
    result = await clients.auth.Refresh(pb.RefreshRequest(context=ctx, refresh_token=refresh_token))
    set_refresh_cookie(response, settings, result.tokens)
    return token_out(result.tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, ctx: AnonCtx, clients: Clients, refresh_token: RefreshCookie = None
) -> None:
    if refresh_token:
        await clients.auth.Logout(pb.LogoutRequest(context=ctx, refresh_token=refresh_token))
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
