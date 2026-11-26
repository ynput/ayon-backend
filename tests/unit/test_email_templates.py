from typing import Any

import pytest
from markupsafe import Markup

from ayon_server.helpers import email
from ayon_server.helpers.email import EmailTemplate
from ayon_server.helpers.email_text import html_to_text

CONTEXT = {
    "full_name": "Carol Test",
    "email": "carol@example.com",
    "studio_name": "Studio",
    "user_name": "carol",
    "password_enabled": True,
    "accept_link": "https://ayon.test/invite?t=1&x=2",
    "reset_url": "https://ayon.test/reset?t=1",
    "invite_link": "https://ayon.test/login/_token?q=abc",
}

WITH_COMPONENTS = """{% extends "base.jinja" %}
{% block content %}
  {{ ui.preheader(preview) }}
  {{ ui.heading(title) }}
  {% call ui.quote() %}{{ comment }}{% endcall %}
{% endblock %}
{% block call_to_action %}
  {{ ui.call_to_action("Open", url) }}
  {{ ui.details(rows) }}
{% endblock %}
{% block footer %}Why you got this.{% endblock %}
"""


@pytest.mark.anyio
async def test_the_text_version_comes_from_the_plain_form_of_the_blocks() -> None:
    text = await EmailTemplate().render_template(
        "password_reset.jinja", {**CONTEXT, "full_name": "<b>Carol</b>"}, plain=True
    )
    assert text == "\n".join(
        [
            "Hi <b>Carol</b>",
            "",
            (
                "It seems that you have requested a password reset"
                " for your account for Ayon."
            ),
            "",
            "Please click the button below to reset your password.",
            "",
            "Reset password: https://ayon.test/reset?t=1",
            "",
            "If you did not request a password reset, please ignore this email.",
        ]
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "template",
    ["user_invite.jinja", "password_reset.jinja", "token_renew.jinja"],
)
async def test_every_email_has_a_text_version_with_its_link(template: str) -> None:
    text = await EmailTemplate().render_template(template, CONTEXT, plain=True)
    link = next(
        CONTEXT[k]
        for k in ("accept_link", "reset_url", "invite_link")
        if CONTEXT[k] in text
    )
    assert link
    assert "<" not in text
    assert "AYON Logo" not in text


@pytest.mark.anyio
async def test_values_are_escaped() -> None:
    html = await EmailTemplate().render_template(
        "password_reset.jinja", {**CONTEXT, "full_name": "<b>Carol</b>"}
    )
    assert "&lt;b&gt;Carol&lt;/b&gt;" in html
    assert "<b>Carol</b>" not in html

    html = await EmailTemplate().render(
        '{% extends "base.jinja" %}{% block content %}{{ a }} {{ b }}{% endblock %}',
        {"a": "<img src=x>", "b": Markup("<em>ok</em>")},
    )
    assert "&lt;img src=x&gt;" in html
    assert "<em>ok</em>" in html


@pytest.mark.anyio
async def test_the_building_blocks() -> None:
    values = {
        "preview": "Shown in the list",
        "title": "Alice commented",
        "comment": "Looks <good>\nsecond line",
        "url": "https://ayon.test/a?b=1&c=2",
        "rows": [("Project", "demo"), ("Task", "comp")],
    }
    html = await EmailTemplate().render(WITH_COMPONENTS, values)
    assert "Looks &lt;good&gt;" in html
    assert 'href="https://ayon.test/a?b=1&amp;c=2"' in html
    text = await EmailTemplate().render(WITH_COMPONENTS, values, plain=True)
    assert text == "\n".join(
        [
            "Alice commented",
            "",
            "> Looks <good>",
            "> second line",
            "",
            "Open: https://ayon.test/a?b=1&c=2",
            "",
            "Project: demo",
            "Task: comp",
            "",
            "Why you got this.",
        ]
    )


def test_text_of_html() -> None:
    html = """<html><head><title>AYON</title><style>p {color: red}</style></head>
    <body><div style="display: none">preview</div>
    <p>Hello <strong>Carol</strong>,<br>line two &amp; more</p>
    <p><a href="https://ayon.test/x">https://ayon.test/x</a>
    and <a href="#top">top</a></p>
    <ul><li>one</li><li>two</li></ul>
    <script>alert(1)</script><p>end</p></body></html>"""
    assert html_to_text(html) == "\n".join(
        [
            "Hello Carol,",
            "line two & more",
            "",
            "https://ayon.test/x and top",
            "",
            "one",
            "two",
            "",
            "end",
        ]
    )


@pytest.mark.anyio
async def test_send_mail_adds_the_text_version(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def smtp() -> str:
        return "smtp"

    def send(
        recipients: list[str], subject: str, text: str | None, html: str | None
    ) -> None:
        sent.update(text=text, html=html)

    monkeypatch.setattr(email, "is_mailing_enabled", smtp)
    monkeypatch.setattr(email, "send_smtp_email", send)

    await email.send_mail(["a@ayon.test"], "Hi", html="<p>Hello <b>you</b></p>")
    assert sent["text"] == "Hello you"

    await email.send_mail(["a@ayon.test"], "Hi", text="Own text", html="<p>x</p>")
    assert sent["text"] == "Own text"
