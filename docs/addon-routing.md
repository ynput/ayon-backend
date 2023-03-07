
Each addon can provide its own api routes. REST routes are prefixed with `/api/addons/{addon_name}/{addon_version}`
and they are defined in the `initialize` method of the addon. Since they are part of the /api namespace, they
are registerd and included to the router from `api/addon/__init.__.py` file  using `register_addon_endpoints` function.

Additionally, each addon can provide routes for serving static files. In this case, the entrypoint is not `/api/addons`
but just `/addons`. Three directories `public`, `private` and `frontend` are auto-discovered during server startup.
The implementation is in `ayon_server/api/server.py` file.





