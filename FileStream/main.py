"""Legacy entrypoint compatibility.

Some deployments still run: python FileStream/main.py
This module proxies execution to FileStream.__main__.
"""

import logging
import traceback

from FileStream.__main__ import cleanup, loop, start_services


if __name__ == "__main__":
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.error(traceback.format_exc())
    finally:
        try:
            loop.run_until_complete(cleanup())
        except Exception:
            pass
        loop.stop()
        print("------------------------ Stopped Services ------------------------")
