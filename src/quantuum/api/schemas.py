from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class MagicRequestIn(BaseModel):
    email: EmailStr


class MagicRequestOut(BaseModel):
    sent: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(BaseModel):
    account_id: int
    tenant_id: int | None


class NatalProfileIn(BaseModel):
    full_name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    for_year: int | None = None


class NatalProfileOut(NatalProfileIn):
    id: int


class BlueprintOut(BaseModel):
    id: int
    status: str
    created_at: str
    completed_at: str | None = None


class BlueprintCreatedOut(BaseModel):
    id: int
    status: str
