from ayon_server.background.log_collector import log_collector
from ayon_server.version import __version__

# We need to import log_collector before everything,
# since it is used to collect the logs during the startup.

assert log_collector  # silence linter
assert __version__
