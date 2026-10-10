import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path
url = 'https://github.com/jmhq20120212-cmd/CounterFlame-WebPort/releases/download/web-1791591234/counterflame-web-1791591234.zip'
expected = '4e564bd5d503ed4d9b41c32893255b9fc1a6d88b0f5f71521772571f3185c464'
archive = Path('/tmp/counterflame.zip')
h = hashlib.sha256()
with urllib.request.urlopen(url, timeout=120) as response, archive.open('wb') as output:
    while chunk := response.read(1024 * 1024):
        output.write(chunk)
        h.update(chunk)
if h.hexdigest() != expected:
    raise RuntimeError('Build checksum mismatch')
root = Path('/app').resolve()
with zipfile.ZipFile(archive) as z:
    for item in z.infolist():
        target = (root / item.filename).resolve()
        if not target.is_relative_to(root):
            raise RuntimeError('Invalid archive path')
    z.extractall(root)
archive.unlink()
print('Verified and extracted CounterFlame build 1791591234')
