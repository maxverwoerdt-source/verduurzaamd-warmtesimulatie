#!/bin/sh
set -eu
: "${APP_SECRET_PATH:?APP_SECRET_PATH must be set to a random path token of at least 20 characters}"
UNO_PORT="${UNO_PORT:-2002}"
export UNO_PORT
mkdir -p /tmp/lo-profile
soffice -env:UserInstallation=file:///tmp/lo-profile \
  --headless \
  --accept="socket,host=127.0.0.1,port=${UNO_PORT};urp;StarOffice.ServiceManager" \
  --norestore --nofirststartwizard >/tmp/soffice.log 2>&1 &

python - <<'PY'
import os, sys, time
sys.path.extend(['/usr/lib/python3/dist-packages','/usr/lib/libreoffice/program'])
import uno
ctx=uno.getComponentContext()
resolver=ctx.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',ctx)
url=f"uno:socket,host=127.0.0.1,port={os.environ.get('UNO_PORT','2002')};urp;StarOffice.ComponentContext"
for _ in range(60):
    try:
        resolver.resolve(url)
        print('LibreOffice persistent calculation service ready', flush=True)
        break
    except Exception:
        time.sleep(.5)
else:
    raise SystemExit('LibreOffice UNO service did not start')
PY
exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 180 app:app
