"""
Taking yourself off a dashboard subscription, from the email itself.

Somebody who did not ask to be subscribed should not have to find the
dashboard, work out who set it up, and ask them. The link in the footer is
theirs alone: it names one subscription and one person, and removing them
leaves everybody else on it.

**Why the link does not act on a GET.** Mail clients and security scanners
fetch the links in a message before anybody has read it -- so a GET that
unsubscribed would unsubscribe people who never clicked anything, and the
symptom would be a subscription that quietly loses its recipients. The link
opens a page with a button; the button posts.

The one exception is the mail client's own Unsubscribe button, which RFC 8058
defines as a POST to the address in `List-Unsubscribe`. That is a deliberate
action by a person, and it arrives as a POST, so it goes through the same
door as the button.

The token has no expiry. An email stays in a mailbox for years and the link in
it should still work; what it can do is bounded instead -- one subscription,
one person, one direction. It stops working when the subscription is deleted.
"""

import logging

from itsdangerous import BadSignature, URLSafeSerializer

from sqldesk import models, settings

logger = logging.getLogger(__name__)

#: Its own salt, so an unsubscribe link is not a password reset and cannot be
#: presented anywhere else a signed token is accepted.
SALT = "sqldesk-unsubscribe"


def _serializer():
    return URLSafeSerializer(settings.SECRET_KEY, salt=SALT)


def token_for(subscription, user):
    """The link that takes this person off this subscription, and nobody else."""
    return _serializer().dumps({"s": subscription.id, "u": user.id})


def link_for(subscription, user, base):
    return "{}/unsubscribe/{}".format(base.rstrip("/"), token_for(subscription, user))


def load(token):
    """
    The (subscription, user) this token names, or (None, None).

    Every reason to refuse gives the same answer: a bad signature, a
    subscription since deleted, a person who is no longer on it.
    """
    try:
        payload = _serializer().loads(token)
    except BadSignature:
        return None, None

    if not isinstance(payload, dict):
        return None, None

    subscription = models.DashboardSubscription.query.get(payload.get("s"))
    if subscription is None:
        return None, None

    user = models.User.query.get(payload.get("u"))
    if user is None or user.org_id != subscription.org_id:
        return None, None

    return subscription, user


def remove(subscription, user):
    """
    Take this person off, and say whether anything changed.

    Idempotent: somebody who clicks the link twice, or whose mail client
    clicked it for them, gets the same answer as the first time rather than an
    error about not being subscribed.
    """
    recipients = list(subscription.recipient_ids or [])
    if user.id not in recipients:
        return False

    recipients.remove(user.id)
    subscription.recipient_ids = recipients

    # A subscription with nobody on it has nothing to do. Left active it would
    # wake every interval, draw a dashboard and mail it to nobody.
    if not recipients:
        subscription.active = False
        subscription.last_error = "Everybody unsubscribed, so this is no longer sending."

    return True
