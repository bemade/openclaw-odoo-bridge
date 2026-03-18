import asyncio
import logging
import signal

from .bridge import Bridge
from .config import Config


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    bridge = Bridge(config)
    loop = asyncio.new_event_loop()

    def _shutdown(sig: signal.Signals) -> None:
        logging.getLogger(__name__).info("Received %s, shutting down...", sig.name)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        loop.run_until_complete(bridge.run())
    except asyncio.CancelledError:
        pass
    finally:
        loop.run_until_complete(bridge.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
