# Notification delivery

When an activity is created, every user it involves (mentioned, watching, related
to the entity) is announced with an `inbox.message` event, and the same activities
fill the user's inbox. `NotificationDelivery`
(`ayon_server/activities/notification_delivery.py`) lets an addon take part. Without
one, AYON behaves as before.

An addon replaces the class methods when it is installed, and puts the originals
back when it is removed:

- `get_channels(notification)` is called once per created activity, after it was
  committed, with the recipients and the reference types that bring the activity
  to each of them. It returns `NotificationChannels` per recipient:
  `inbox=False` leaves the recipient out of the announcement, `desktop` tells the
  client whether it may show a system notification or toast (`desktopEnabled` in
  the event summary, absent when `None`). It can also deliver through channels of
  its own. Exceptions are logged and lead to the defaults.
- `get_inbox_filter(user_name)` returns an SQL condition added to the user's inbox
  query. The query reads `activity_feed` (one row per activity reference) as `t`.
  Exceptions are logged and show the whole inbox.

`send_mail(..., raise_on_error=True)` raises when sending fails, for callers that
retry.
