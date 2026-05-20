from quantuum.common.ids import url_safe_token
from quantuum.logging_setup import get_logger
from quantuum.redis_client import get_redis
from quantuum.settings import get_settings

logger = get_logger("magic_link")
_PREFIX = "magic:"


async def create_magic_token(email: str) -> str:
    settings = get_settings()
    token = url_safe_token()
    await get_redis().set(f"{_PREFIX}{token}", email, ex=settings.magic_link_ttl_seconds)
    link = f"{settings.api_host}/auth/magic/consume?token={token}"
    await send_magic_email(email, link)
    return token


async def consume_magic_token(token: str) -> str | None:
    redis = get_redis()
    key = f"{_PREFIX}{token}"
    email = await redis.get(key)
    if email is None:
        return None
    await redis.delete(key)
    return email


async def send_magic_email(to_email: str, link: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("magic_link_email_stub", to=to_email, link=link)
        return
    import aiosmtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = "Your Quantuum sign-in link"
    message.set_content(f"Sign in: {link}")
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
