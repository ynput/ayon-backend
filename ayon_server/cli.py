import asyncio
import inspect
import sys
from functools import partial, wraps

from typer import Typer


class AsyncTyper(Typer):
    @staticmethod
    def maybe_run_async(decorator, f):
        if inspect.iscoroutinefunction(f):

            @wraps(f)
            def runner(*args, **kwargs):
                coro = f(*args, **kwargs)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return asyncio.run(coro)
                else:
                    return loop.create_task(coro)

            decorator(runner)
        else:
            decorator(f)
        return f

    def callback(self, *args, **kwargs):
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args, **kwargs):
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)


app = AsyncTyper()


@app.command()
def version() -> None:
    """Print the AYON server version"""
    from ayon_server import __version__

    print(
        f"{__version__}",
        file=sys.stderr,
        flush=True,
        end="",
    )
