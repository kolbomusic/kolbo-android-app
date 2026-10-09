"""Build-time restore of the reviewed 2.2.0 Python runtime sources."""
import base64,hashlib,io,pathlib,zipfile
source=pathlib.Path('kolbo-grid-v24-runtime.src.b64')
data=base64.b64decode(source.read_text(encoding='ascii'),validate=True)
assert hashlib.sha256(data).hexdigest()=='eadc172688b9e08090232831e6b9b60b854002a8ee25b61369c718b199613672', 'Runtime checksum mismatch'
root=pathlib.Path('.').resolve()
with zipfile.ZipFile(io.BytesIO(data)) as z:
    assert z.testzip() is None
    for info in z.infolist():
        target=(root / info.filename).resolve()
        assert target.is_relative_to(root) and not info.is_dir(), 'Unexpected archive entry'
    z.extractall(root)
print('Restored 24 reviewed runtime files and verified SHA-256')
