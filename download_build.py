import hashlib
import urllib.request
import zipfile
from pathlib import Path
root=Path('/app').resolve()
releases=[
 ('https://github.com/jmhq20120212-cmd/CounterFlame-WebPort/releases/download/web-1791591234/counterflame-web-1791591234.zip','4e564bd5d503ed4d9b41c32893255b9fc1a6d88b0f5f71521772571f3185c464'),
 ('https://github.com/jmhq20120212-cmd/CounterFlame-WebPort/releases/download/arena-1791616589/counterflame-persistent-1791616589.zip','61d7a42c1c5114c8a3d3df3027f7b559cf63c9b3d80cc724b3c29655ce7d6858'),
 ('https://github.com/jmhq20120212-cmd/CounterFlame-WebPort/releases/download/comms-20261010/counterflame-persistent-1791687147.zip','4bcadd3276b3395d67107dbeee2d0f2892aaa6385fa2ffa47e2330685e52d2ee')
]
for index,(url,expected) in enumerate(releases):
 archive=Path('/tmp')/('counterflame-'+str(index)+'.zip')
 h=hashlib.sha256()
 with urllib.request.urlopen(url,timeout=120) as response,archive.open('wb') as output:
  while chunk:=response.read(1024*1024):output.write(chunk);h.update(chunk)
 if h.hexdigest()!=expected:raise RuntimeError('Build checksum mismatch')
 with zipfile.ZipFile(archive) as z:
  for item in z.infolist():
   if not (root/item.filename).resolve().is_relative_to(root):raise RuntimeError('Invalid archive path')
  z.extractall(root)
 archive.unlink()
print('Verified CounterFlame communications build 1791687147')

