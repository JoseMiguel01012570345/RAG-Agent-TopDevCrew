import json

from tests.paths import EVAL_DIR


def test_eval_set_recalls_expected_citations_and_abstains(client):
    """Mide recall de la cita esperada y acierto de abstención.

    No mide la redacción ni penaliza citas extra. El conjunto es sintético y pequeño.
    """
    spec = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
    created = client.post(
        "/communities",
        headers={"X-User-Id": "evaluador"},
        json={"name": "Conjunto de evaluación"},
    )
    assert created.status_code == 201, created.text
    community_id = created.json()["id"]
    for document in spec["documents"]:
        payload = (EVAL_DIR / "fixtures" / document["filename"]).read_bytes()
        response = client.post(
            f"/communities/{community_id}/documents",
            headers={"X-User-Id": "evaluador"},
            files={"file": (document["filename"], payload, "text/plain")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "ready"

    hits = 0
    for case in spec["cases"]:
        response = client.post(
            f"/communities/{community_id}/questions",
            headers={"X-User-Id": "evaluador"},
            json={"question": case["question"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sufficient_evidence"] is case["sufficient_evidence"], case["id"]
        cited = {(item["document_name"], item["page"]) for item in body["citations"]}
        expected = {(item["filename"], item["page"]) for item in case["expected_citations"]}
        assert expected <= cited, case["id"]
        if case["sufficient_evidence"]:
            hits += 1
        else:
            assert body["citations"] == []
    assert hits == 3
