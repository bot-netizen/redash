import hashlib
import logging

from flask import render_template
from itsdangerous import BadSignature, URLSafeTimedSerializer

from sqldesk import settings
from sqldesk.tasks import send_mail
from sqldesk.utils import base_url

logger = logging.getLogger(__name__)

#: The three links that carry a signed user id, each good for its own page only.
INVITE = "invite"
RESET = "reset"
VERIFY = "verify"

# One serializer per purpose. The salt is what keeps a link to its own page:
# without it the same token opened /invite, /reset and /verify alike, so an
# invite that /invite refused as already accepted was still a working
# password reset for a week.
_serializers = {
    purpose: URLSafeTimedSerializer(settings.SECRET_KEY, salt="sqldesk-" + purpose)
    for purpose in (INVITE, RESET, VERIFY)
}


class TokenUsed(BadSignature):
    """The password this link was issued for has changed: it was used, or overtaken by a newer link."""


def _password_fingerprint(user):
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def token_for(user, purpose):
    """
    A signed link to `purpose` for this user.

    Invite and reset links carry a fingerprint of the password as it is now,
    so setting a password through one kills it -- and every other link of its
    kind still in somebody's mailbox. A link is single-use without the server
    having to remember which it has seen.
    """
    payload = {"id": user.id}
    if purpose != VERIFY:
        payload["pw"] = _password_fingerprint(user)
    return _serializers[purpose].dumps(payload)


def invite_token(user):
    return token_for(user, INVITE)


def reset_token(user):
    return token_for(user, RESET)


def verify_link_for_user(user):
    return "{}/verify/{}".format(base_url(user.org), token_for(user, VERIFY))


def invite_link_for_user(user):
    return "{}/invite/{}".format(base_url(user.org), invite_token(user))


def reset_link_for_user(user):
    return "{}/reset/{}".format(base_url(user.org), reset_token(user))


def user_for_token(token, purpose, org):
    """
    The user a link is for, when the link is good for `purpose`, unexpired,
    unused, and for a user of this organization. Raises `SignatureExpired`,
    `TokenUsed`, `BadSignature` or `NoResultFound`.
    """
    from sqldesk import models

    payload = _serializers[purpose].loads(token, max_age=settings.INVITATION_TOKEN_MAX_AGE)
    user = models.User.get_by_id_and_org(payload["id"], org)
    if purpose != VERIFY and payload.get("pw") != _password_fingerprint(user):
        raise TokenUsed("the password this link was issued for has changed")
    return user


def send_verify_email(user, org):
    context = {"user": user, "verify_url": verify_link_for_user(user)}
    html_content = render_template("emails/verify.html", **context)
    text_content = render_template("emails/verify.txt", **context)
    subject = "{}, please verify your email address".format(user.name)

    send_mail.delay([user.email], subject, html_content, text_content)


def send_invite_email(inviter, invited, invite_url, org):
    context = dict(inviter=inviter, invited=invited, org=org, invite_url=invite_url)
    html_content = render_template("emails/invite.html", **context)
    text_content = render_template("emails/invite.txt", **context)
    subject = "{} invited you to join SQLDesk".format(inviter.name)

    send_mail.delay([invited.email], subject, html_content, text_content)


def send_password_reset_email(user):
    reset_link = reset_link_for_user(user)
    context = dict(user=user, reset_link=reset_link)
    html_content = render_template("emails/reset.html", **context)
    text_content = render_template("emails/reset.txt", **context)
    subject = "Reset your password"

    send_mail.delay([user.email], subject, html_content, text_content)
    return reset_link


def send_user_disabled_email(user):
    html_content = render_template("emails/reset_disabled.html", user=user)
    text_content = render_template("emails/reset_disabled.txt", user=user)
    subject = "Your SQLDesk account is disabled"

    send_mail.delay([user.email], subject, html_content, text_content)
