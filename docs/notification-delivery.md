# Notification delivery

When an activity is created, every user it involves (mentioned, watching, related
to the entity) is announced with an `inbox.message` event, and the same activities
fill the user's inbox, split into an important part and the rest.
`NotificationDelivery` (`ayon_server/activities/notification_delivery.py`) lets an
addon take part. Without one, AYON behaves as before.

An addon replaces the class methods when it is installed, and puts the originals
back when it is removed:

- `get_channels(notification)` is called once per created activity, after it was
  committed, with the recipients, the reference type that brings the activity to
  each of them, and the role of those who are related to the entity (`assignee`,
  `author` of the version). It returns `NotificationChannels` per recipient:
  `important` says whether the message is announced as important (`isImportant`
  in the event summary), `desktop` tells the client whether it may show a system
  notification or toast (`desktopEnabled`, absent when `None`). `None` keeps
  AYON's own rule. It can also deliver through channels of its own. Exceptions
  are logged and lead to the defaults.
- `get_inbox_importance(user_name)` returns the SQL condition that is true for the
  important rows of the user's inbox. Rows are never left out: what is not
  important is in the other part. The condition is evaluated on `activity_feed`
  (one row per activity reference) read as `t`, by the inbox query and by the
  endpoint that marks a part of the inbox as read or cleared, and has to agree
  with `important` above. Exceptions are logged and lead to AYON's rule: mentions
  and watched entities are important, status changes are not.

A user has one reference per activity: a mention wins over watching, watching over
a relation. So that the relation is not lost, the reference of a related user keeps
the role whatever its type, in `t.reference_data->>'role'`.

`send_mail(..., raise_on_error=True)` raises when sending fails, for callers that
retry.
