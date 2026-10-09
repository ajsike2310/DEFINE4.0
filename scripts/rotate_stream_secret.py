"""Generate a new EXOTEL_WEBHOOK_TOKEN and rewrite the secret inside EXOTEL_STREAM_URL in .env.
Prints nothing secret. Restart the server afterwards.

    python -m scripts.rotate_stream_secret
"""
import re
import secrets
from pathlib import Path

env = Path(".env")
lines = env.read_text(encoding="utf-8").splitlines()
new = secrets.token_urlsafe(32)
out, saw_token, saw_url = [], False, False
for line in lines:
    if line.startswith("EXOTEL_WEBHOOK_TOKEN="):
        line, saw_token = f"EXOTEL_WEBHOOK_TOKEN={new}", True
    elif line.startswith("EXOTEL_STREAM_URL="):
        base = re.sub(r"/live/exotel(/[^/?\s]*)?(\?.*)?$", "", line.split("=", 1)[1].strip())
        line, saw_url = f"EXOTEL_STREAM_URL={base}/live/exotel/{new}", True
    out.append(line)
if not saw_token:
    out.append(f"EXOTEL_WEBHOOK_TOKEN={new}")
env.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"Rotated. EXOTEL_WEBHOOK_TOKEN {'replaced' if saw_token else 'added'}; "
      f"EXOTEL_STREAM_URL {'updated' if saw_url else 'NOT found, set it yourself'}. Restart the server.")
