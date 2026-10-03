# Waiting on Iqbal

Delete an entry when it is answered, and write the answer where the work is.

## Blocking 0.7

- **A Slack bot token in a test workspace.** Share-to-Slack is driven against
  a stub of Slack's Web API, which covers the three-step upload, the
  pagination and the error translation — but not whether a real Slack renders
  the blocks as intended.
- **The OAuth consent page walked once in a browser.** Everything else about
  OAuth 2.1 for MCP is tested; the page itself needs a human session, and
  entering credentials to look at a page is not something to do.

## Decisions taken, recorded so they are not re-opened

- **Kafka ships in 0.7**, overriding a recommendation to defer it to 0.8.
- **Locked folders are changeable by administrators**, not frozen for
  everyone. The first design made them read-only even for admins; that was
  wrong.
- **A dashboard shows streams or saved queries, never both**, because a
  dashboard has one refresh interval. Streaming ones are offered seconds:
  2, 5, 10, 20, 30, 60, 120 — no hours, no days.
- **Running Streams stayed in the Kafka Streams menu** as a fourth item,
  although the list Iqbal gave had three. Removing it would hide the page from
  anyone who is not an administrator. Flagged, not yet confirmed.
- **MCP stayed in the Admin menu** for the same reason — it was not on the
  list, and dropping it makes the page unreachable.
- **`main` has not had 0.6 merged into it.** Offered; the answer was to carry
  on, so it waits for 0.7.

## Known-open, found but not fixed

- `HelpTrigger.jsx` builds 22 help links from
  `DOMAIN = "https://sqldesk.github.io/sqldesk"`. The site is at
  **bot-netizen**.github.io. Fixing it means deciding what the help system is
  for, not correcting a typo.
- `FEATURE_EXTENDED_ALERT_OPTIONS` is shipped to the client as
  `extendedAlertOptions` and read by nothing.
- `dashboards.schedule` and migration `f4b2c8d1e903` are vestigial —
  dashboard schedules were added in 0.2.0 and removed in 0.3.2 by request.
