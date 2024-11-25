from .auto_update import AutoUpdate
from .push_metrics import PushMetrics
from .remove_old_events import RemoveOldEvents
from .remove_old_logs import RemoveOldLogs
from .remove_unused_activities import RemoveUnusedActivities
from .remove_unused_files import RemoveUnusedFiles
from .remove_unused_thumbnails import RemoveUnusedThumbnails
from .vacuum_db import VacuumDB

task_sequence = [
    AutoUpdate,
    RemoveOldLogs,
    RemoveOldEvents,
    RemoveUnusedActivities,
    RemoveUnusedFiles,
    RemoveUnusedThumbnails,
    VacuumDB,
    PushMetrics,
]
