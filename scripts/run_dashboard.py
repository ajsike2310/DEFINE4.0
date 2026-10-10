"""Start the campaign dashboard.

    python -m scripts.run_dashboard [port]      (default 8002, the port the ngrok tunnel in EXOTEL_STREAM_URL forwards to)

CALL_PROVIDER=demo (default) simulates calls, so the whole flow can be tried without placing any. Set CALL_PROVIDER=exotel
plus the EXOTEL_* / ELEVENLABS_* variables in .env for real calls (see .env.example). Run ONE worker.
"""
import logging
import sys

import uvicorn
from dotenv import load_dotenv

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

if __name__ == "__main__":
    from member3.live import logging_utils
    logging_utils.install()           # redacts the stream secret from logs
    from dashboard.main import create_app
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8002
    uvicorn.run(create_app(), host="127.0.0.1", port=port, access_log=False, log_config=None)
