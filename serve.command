#!/bin/bash
# Double-click on the Mac to run the stream desk locally at http://localhost:8787
cd "$(dirname "$0")"
git pull --quiet 2>/dev/null
echo "Stream desk running at http://localhost:8787  (scenes: http://localhost:8787/obs.html)"
echo "Leave this window open while you stream. Close it to stop."
python3 -m http.server 8787 --bind 127.0.0.1
