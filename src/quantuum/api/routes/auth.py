from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session
from quantuum.api.schemas import MagicRequestIn, MagicRequestOut, RefreshIn, TokenOut
from quantuum.auth import jwt_tokens, magic_link
from quantuum.auth.identity import find_or_create_account_by_email
from quantuum.common.exceptions import NotFoundError
from quantuum.domain.tenants import get_default_tenant_id

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/magic/request", response_model=MagicRequestOut)
async def magic_request(body: MagicRequestIn) -> MagicRequestOut:
    await magic_link.create_magic_token(body.email)
    return MagicRequestOut(sent=True)


@router.get("/magic/consume", response_model=TokenOut)
async def magic_consume(token: str, session: AsyncSession = Depends(get_session)) -> TokenOut:
    email = await magic_link.consume_magic_token(token)
    if email is None:
        raise HTTPException(status_code=400, detail="invalid or expired token")
    tenant_id = await get_default_tenant_id(session)
    account = await find_or_create_account_by_email(session, tenant_id=tenant_id, email=email)
    access = jwt_tokens.issue_access_token(account.id, tenant_id)
    refresh = await jwt_tokens.issue_refresh_token(session, account.id)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        account = await jwt_tokens.consume_refresh_token(session, body.refresh_token)
    except NotFoundError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    access = jwt_tokens.issue_access_token(account.id, account.tenant_id)
    return TokenOut(access_token=access, refresh_token=body.refresh_token)


@router.post("/logout")
async def logout(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict:
    await jwt_tokens.revoke_refresh_token(session, body.refresh_token)
    return {"ok": True}
