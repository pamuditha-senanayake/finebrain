# test_connections_manage.py: a connection can be renamed and deleted from the console; delete erases its keys too.
from app.pipeline import conn_call
from tests.test_connections import FOUNDER, KEY, MANIFEST, TENANT, answer_text, desk, drafted, post  # noqa: F401


def test_a_connection_can_be_renamed_and_deleted_with_its_keys(desk):
    client, lane = desk
    connection = drafted(client)
    path = f"/api/t/{TENANT}/connections/{connection['id']}"
    post(client, f"connections/{connection['id']}/deliver", {"answer": answer_text(MANIFEST)})
    assert conn_call.get_secret(lane, connection["id"], "api_key") == KEY

    renamed = client.patch(path, json={"name": "  Shop chat  "}, headers={"x-persona": FOUNDER})
    assert renamed.json()["name"] == "Shop chat"
    assert client.patch(path, json={"name": " "}, headers={"x-persona": FOUNDER}).status_code == 400

    assert client.delete(path, headers={"x-persona": FOUNDER}).json() == {"deleted": connection["id"]}
    assert conn_call.load(lane, connection["id"]) is None and conn_call.get_secret(lane, connection["id"], "api_key") is None
    assert client.delete(path, headers={"x-persona": FOUNDER}).status_code == 404
