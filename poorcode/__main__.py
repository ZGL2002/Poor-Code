"""PoorCode 程序入口."""

import asyncio
import sys


def main() -> None:
    """启动 PoorCode."""
    from poorcode.chat import run

    try:
        exit_code = asyncio.run(run())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
