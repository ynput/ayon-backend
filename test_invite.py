#!/usr/bin/env python3

from ayon_server.auth.tokenauth import send_invite_email
from ayon_server.initialize import ayon_init

from .app import app

BODY_TEMPLATE = """
<h3>Hey {full_name}</h3>

<p>
Someone has invited you to join their Ayon instance.
To accept the invitation, please click the link below:
</p>

<p>
<a clicktracking=off href="{invite_link}">Accept Invitation</a>
</p>

<p>
After clicking the link, you should be redirected to {redirect_url}.
As that is the page that was shared with you and you won't have
access almost nowere else.
</p>

<p>
Normally we won't show the full link there, but we're just testing stuff here.
Also, this body and subject are customizable per addon.
</p>


Cheers
"""


@app.command()
async def invite(base_url: str, email: str, full_name: str) -> None:
    await ayon_init(extensions=False)

    await send_invite_email(
        email=email,
        base_url=base_url,
        full_name=full_name,
        body_template=BODY_TEMPLATE,
        external=True,
        redirect_url="/inbox/cleared",
    )
