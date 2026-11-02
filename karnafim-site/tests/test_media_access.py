"""Offline media authorization regression. Does not touch Neon or real accounts."""
import sys
from pathlib import Path
from flask import Flask, session
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import community_portal

MEDIA_BYTES = b"\xff\xd8\xff" + b"private-review-file"
state = {"approved_post": False}

def fake_sql(query, params=(), fetch=False):
    if "SELECT m.*,p.approved post_approved FROM community_media" in query:
        return [{
            "id": 50, "owner_id": 7, "post_id": 102,
            "recipient_id": None, "post_approved": state["approved_post"],
            "data": MEDIA_BYTES, "mime": "image/jpeg", "kind": "image",
        }]
    if fetch:
        raise AssertionError("Unexpected database read: " + query[:120])
    # Startup migrations are intentionally mocked with no production DB access.
    return None

def test():
    app = Flask("karnafim_media_access_test")
    app.secret_key = "offline-test-key-not-for-production"
    def current_member():
        uid = session.get("uid")
        return {"id": uid, "approved": session.get("approved",True)} if uid else None
    community_portal.install(
        app, fake_sql, lambda title, body: body, current_member,
        lambda u: u is not None and u["id"] == 42,
        lambda: None, lambda html: html, str,
    )
    client = app.test_client()
    assert client.get("/community-media/50").status_code == 403, "Anonymous must be denied"
    with client.session_transaction() as sess: sess["uid"] = 99
    assert client.get("/community-media/50").status_code == 403, "Held post must be private to ordinary members"
    with client.session_transaction() as sess: sess["uid"] = 42
    res = client.get("/community-media/50")
    assert res.status_code == 200 and res.data == MEDIA_BYTES, "Moderator must see held media for approval"
    assert "no-store" in res.headers["Cache-Control"]
    with client.session_transaction() as sess: sess["uid"] = 7
    assert client.get("/community-media/50").status_code == 200, "Author may inspect own pending media"
    with client.session_transaction() as sess: sess["approved"] = False
    assert client.get("/community-media/50").status_code == 200, "Unapproved author may see their own submitted media"
    with client.session_transaction() as sess: sess["uid"] = 99
    assert client.get("/community-media/50").status_code == 403, "Unapproved other member cannot inspect an author's pending media"
    with client.session_transaction() as sess: sess["approved"] = True
    state["approved_post"] = True
    with client.session_transaction() as sess: sess["uid"] = 99
    assert client.get("/community-media/50").status_code == 200, "Approved post media is visible to approved members"
    state["approved_post"] = False
    print("PASS: anonymous denied, held private, moderator review, owner view, approved member view")

if __name__ == "__main__":
    test()
