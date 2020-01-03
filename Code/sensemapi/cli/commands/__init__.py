# system modules
import pkg_resources
import warnings

# internal modules
import sensemapi.cli.commands.main

# load extra commands
for entry_point in pkg_resources.iter_entry_points("sensemapi.commands"):
    try:
        entry_point.load()
    except pkg_resources.DistributionNotFound:
        continue

# external modules
