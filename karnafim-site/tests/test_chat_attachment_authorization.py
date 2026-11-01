"""Isolated access-control test. Uses fake members and never reaches production."""
import sys
from pathlib import Path
from flask import Flask, session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import community_portal

state = {"connected": True}
payload = b"synthetic-file-payload"

def sql(query, params=(), fetch=False):
    if "SELECT m.*,p.approved post_approved FROM community_media" in query:
        if params[0] != 60:
            return []
        return [{"id": 60, "owner_id": 7, "recipient_id": 8,
                 "post_id": None, "post_approved": None,
                 "data": payload, "mime": "image/jpeg", "kind": "image"}]
    if "SELECT 1 FROM requests WHERE accepted=TRUE" in query:
        return [{"exists": 1}] if state["connected"] else []
    if fetch:
        raise AssertionError("Unexpected query")
    return None

def run():
    app = Flask("media_permissions_unit_test")
    app.secret_key = "test-only"
    def member():
        user_id = session.get("uid")
        return {"id": user_id, "approved": True} if user_id else None
    community_portal.install(
        app, sql, lambda title, body: body,
        member, lambda u: bool(u and u["id"] == 42),
        lambda: None, lambda x: x, str,
    )
    client = app.test_client()
    assert client.get("/community-media/60").status_code == 403
    for user_id, expected in ((42,403),(99,403),(7,200),(8,200)):
        with client.session_transaction() as sess:
            sess["uid"] = user_id
        response = client.get("/community-media/60")
        assert response.status_code == expected, (user_id,response.status_code)
        if expected == 200:
            assert response.data == payload
            assert "no-store" in response.headers["Cache-Control"]
    state["connected"] = False
    with client.session_transaction() as sess:
        sess["uid"] = 8
    assert client.get("/community-media/60").status_code == 403
    print("PASS: no anonymous, moderator or unrelated access to chat attachments")

if __name__ == "__main__":
    run()
