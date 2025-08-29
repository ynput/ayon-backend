__all__ = ["task_sequence"]

from .auto_update import AutoUpdate
from .push_metrics import PushMetrics
from .remove_inactive_workers import RemoveInactiveWorkers
from .remove_old_action_configs import RemoveOldActionConfigs
from .remove_old_events import RemoveOldEvents
from .remove_old_logs import RemoveOldLogs
from .remove_unused_activities import RemoveUnusedActivities
from .remove_unused_files import RemoveUnusedFiles
from .remove_unused_settings import RemoveUnusedSettings
from .remove_unused_thumbnails import RemoveUnusedThumbnails

# from .vacuum_db import VacuumDB

task_sequence = [
    AutoUpdate,
    RemoveInactiveWorkers,
    RemoveOldActionConfigs,
    RemoveOldLogs,
    RemoveOldEvents,
    RemoveUnusedActivities,
    RemoveUnusedFiles,
    RemoveUnusedSettings,
    RemoveUnusedThumbnails,
    # VacuumDB, -- too expensive. maybe run it manually?
    PushMetrics,
]
