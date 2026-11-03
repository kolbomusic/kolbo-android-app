"""Offline media input checks with no production database."""
import io
import os
import sys
from pathlib import Path
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL",None)
import app as site

def upload(data, content_type, filename="upload"):
    return FileStorage(stream=io.BytesIO(data), filename=filename, content_type=content_type)

with site.app.test_request_context("/new"):
    oversized=upload(b"X"*(8*1024*1024+1), "image/png")
    try:
        site.image_or_video(oversized)
        raise AssertionError("oversized upload accepted")
    except RequestEntityTooLarge:
        pass
    try:
        site.image_or_video(upload(b"not an image","image/png"))
        raise AssertionError("invalid image accepted")
    except BadRequest:
        pass
    im=Image.new("RGB",(16,16),"white")
    output=io.BytesIO()
    im.save(output,format="PNG")
    mime,kind,clean=site.image_or_video(upload(output.getvalue(),"image/png"))
    assert mime=="image/jpeg" and kind=="image" and clean.startswith(b"\\xff\\xd8")
    assert len(clean)<8*1024*1024
print("PASS: upload size and file integrity checks")
