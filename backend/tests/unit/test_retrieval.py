import uuid

from app.services.retrieval import reciprocal_rank_fusion
from app.services.textutil import lexical_query


def test_rrf_prefers_items_present_in_both_lists():
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = reciprocal_rank_fusion([[first, second], [first, third]])
    assert fused[0][0] == first
    assert fused[0][1] > fused[1][1]


def test_lexical_query_drops_stopwords_and_joins_with_or():
    query = lexical_query("¿El ascensor de marzo?")
    assert query is not None
    assert "ascensor" in query
    assert "marzo" in query
    assert " | " in query
    assert query.split(" | ") == ["ascensor", "marzo"]
