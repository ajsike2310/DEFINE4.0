"""Start the live-call dev server with access logging off (the access line would print the stream secret).

    python -m scripts.run_live [port]
"""
import sys

import uvicorn

if __name__ == "__main__":
    uvicorn.run("member3.live.dev_server:app", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000,
                access_log=False, log_config=None)
