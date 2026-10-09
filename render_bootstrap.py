"""Build-time restore of the reviewed 2.5.0 Python runtime sources."""
import base64,hashlib,io,pathlib,zipfile
source=pathlib.Path('kolbo-grid-v25-runtime.src.b64')
data=base64.b64decode(source.read_text(encoding='ascii'),validate=True)
assert hashlib.sha256(data).hexdigest()=='9200f62e9ab97ab0a8c3c92e6eca850b4fe45950fe1e72180143531055e4481a', 'Runtime checksum mismatch'
root=pathlib.Path('.').resolve()
with zipfile.ZipFile(io.BytesIO(data)) as z:
    assert z.testzip() is None
    for info in z.infolist():
        target=(root / info.filename).resolve()
        assert target.is_relative_to(root) and not info.is_dir(), 'Unexpected archive entry'
    z.extractall(root)
print('Restored 25 reviewed runtime files and verified SHA-256')
