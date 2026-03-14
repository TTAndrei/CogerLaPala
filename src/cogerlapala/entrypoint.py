from __future__ import annotations

import sys


def _pop_option_value(args: list[str], option: str) -> str | None:
    if option not in args:
        return None

    index = args.index(option)
    if index + 1 >= len(args):
        return None

    value = args[index + 1]
    del args[index : index + 2]
    return value


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])

    if "--api" in args:
        args.remove("--api")
        import uvicorn

        uvicorn.run("cogerlapala.main:app", host="0.0.0.0", port=8000, reload=True)
        return 0

    if "--cli" in args:
        args.remove("--cli")
        from cogerlapala.launcher import main as cli_main

        old_argv = sys.argv
        try:
            sys.argv = [old_argv[0], *args]
            return cli_main()
        finally:
            sys.argv = old_argv

    gui_request = _pop_option_value(args, "--request")
    from cogerlapala.gui_app import run_gui

    return run_gui(initial_request_path=gui_request)
