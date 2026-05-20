from quantuum.auth import magic_link


async def test_request_and_consume(monkeypatch, default_tenant):
    sent = {}

    async def fake_send(to_email, link):
        sent["to"] = to_email
        sent["link"] = link

    monkeypatch.setattr(magic_link, "send_magic_email", fake_send)

    token = await magic_link.create_magic_token("user@example.com")
    assert "user@example.com" in sent["link"] or token in sent["link"]

    email = await magic_link.consume_magic_token(token)
    assert email == "user@example.com"


async def test_consume_invalid_returns_none():
    assert await magic_link.consume_magic_token("nope") is None
