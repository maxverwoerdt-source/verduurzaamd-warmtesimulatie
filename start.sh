#!/bin/sh
set -eu
: "${APP_SECRET_PATH:?APP_SECRET_PATH must be set to a random path token of at least 20 characters}"
mkdir -p /tmp/lo-profile
soffice -env:UserInstallation=file:///tmp/lo-profile \
  --headless \
  --accept="socket,host=127.0.0.1,port=${UNO_PORT:-2002};urp;StarOffice.ServiceManager" \
  --norestore --nofirststartwizard >/tmp/soffice.log 2>&1 &

# Wait for the UNO listener to become available before starting the web server.
python - <<'PY'
import os, sys, time
sys.path.extend(['/usr/lib/python3/dist-packages','/usr/lib/libreoffice/program'])
import uno
from com.sun.star.beans import PropertyValue
ctx=uno.getComponentContext()
resolver=ctx.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',ctx)
url=f"uno:socket,host=127.0.0.1,port={os.environ.get('UNO_PORT','2002')};urp;StarOffice.ComponentContext"
for _ in range(40):
    try:
        resolver.resolve(url)
        print('LibreOffice calculation service ready', flush=True)
        break
    except Exception:
        time.sleep(.5)
else:
    raise SystemExit('LibreOffice UNO service did not start')
PY

exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 180 app:app
