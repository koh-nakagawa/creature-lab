from pathlib import Path
import urllib.request,tarfile,io,hashlib,json
root=Path(__file__).resolve().parent
url='https://registry.npmjs.org/three/-/three-0.180.0.tgz'
data=urllib.request.urlopen(url,timeout=30).read()
dest=root/'frontend/vendor/three-0.180.0';dest.mkdir()
names=['build/three.module.js','build/three.core.js','examples/jsm/controls/OrbitControls.js','examples/jsm/loaders/STLLoader.js','LICENSE']
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
    for name in names:
        blob=archive.extractfile('package/'+name).read()
        path=dest/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as out:out.write(blob)
record=dict(source=url,archive_bytes=len(data),archive_sha256=hashlib.sha256(data).hexdigest(),files=names)
with (dest/'provenance.json').open('x') as out:json.dump(record,out,indent=2)
with (root/'note.txt').open('a') as out:out.write('\nVendor acquisition: '+json.dumps(record)+'\n')
print('VENDORED',len(data),'bytes',record['archive_sha256'])
