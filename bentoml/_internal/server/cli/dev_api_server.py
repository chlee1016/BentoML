import socket
import typing as t
from urllib.parse import urlparse

import click
import psutil

from bentoml import load

from ...log import LOGGING_CONFIG
from ...trace import ServiceContext


@click.command()
@click.argument("bento_identifier", type=click.STRING, required=False, default=".")
@click.option("--bind", type=click.STRING, required=True)
@click.option("--backlog", type=click.INT, default=2048)
@click.option("--working-dir", required=False, type=click.Path(), default=None)
@click.option("--reload", required=False, type=click.BOOL, is_flag=True, default=False)
@click.option("--reload-delay", required=False, type=click.FLOAT, default=None)
def main(
    bento_identifier: str,
    bind: str,
    working_dir: t.Optional[str],
    reload: bool,
    reload_delay: t.Optional[float],
    backlog: int,
):
    import uvicorn  # type: ignore

    from ...configuration import get_debug_mode

    ServiceContext.component_name_var.set("dev_api_server")

    parsed = urlparse(bind)

    if parsed.scheme == "fd":
        fd = int(parsed.netloc)
        sock = socket.socket(fileno=fd)
        log_level = "debug" if get_debug_mode() else "info"
        svc = load(bento_identifier, working_dir=working_dir, change_global_cwd=True)
        uvicorn_options = {
            "log_level": log_level,
            "backlog": backlog,
            "reload": reload,
            "reload_delay": reload_delay,
            "log_config": LOGGING_CONFIG,
            "workers": 1,
        }
        if psutil.WINDOWS:
            uvicorn_options["loop"] = "asyncio"
            import asyncio

            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore

        if reload:
            # When reload=True, the app parameter in uvicorn.run(app) must be the import str
            asgi_app_import_str = f"{svc._import_str}.asgi_app"  # type: ignore[reportPrivateUsage]
            # TODO: use svc.build_args.include/exclude as default files to watch
            # TODO: watch changes in model store when "latest" model tag is used
            config = uvicorn.Config(asgi_app_import_str, **uvicorn_options)
            server = uvicorn.Server(config)

            from uvicorn.supervisors import ChangeReload  # type: ignore

            ChangeReload(config, target=server.run, sockets=[sock]).run()
        else:
            config = uvicorn.Config(svc.asgi_app, **uvicorn_options)
            uvicorn.Server(config).run(sockets=[sock])
    else:
        raise ValueError(f"Unsupported bind scheme: {bind}")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
