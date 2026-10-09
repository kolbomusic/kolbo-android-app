"""Build-time restore of the reviewed 2.6.0 Python runtime sources."""
import base64,hashlib,io,pathlib,zipfile
source=pathlib.Path('kolbo-grid-v26-runtime.src.b64')
data=base64.b64decode(source.read_text(encoding='ascii'),validate=True)
assert hashlib.sha256(data).hexdigest()=='0482b0be75505adcca124de53eb17e9989fc3080590e13cf677439cf822aaaf2', 'Runtime checksum mismatch'
root=pathlib.Path('.').resolve()
with zipfile.ZipFile(io.BytesIO(data)) as z:
    assert z.testzip() is None
    for info in z.infolist():
        target=(root / info.filename).resolve()
        assert target.is_relative_to(root) and not info.is_dir(), 'Unexpected archive entry'
    z.extractall(root)
print('Restored 28 reviewed runtime files and verified SHA-256')
