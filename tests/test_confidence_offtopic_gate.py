"""
Off-topic relevance gate for the LightRAG confidence scorer (2026-06-24).

Regression for the 加绒/两件套 hallucination: under the rag_query fast-path
(mt047A: mode=naive, only_need_context=True, enable_rerank=False) there is no
retrieval/rerank score, so confidence used the faithfulness-only formula which
never checked query↔chunk relevance. An off-topic-but-well-formed apparel
category list scored 0.92 "very_high", defeating the Q&A prompt's "<0.50 →
distrust" gate. The gate caps such off-topic chunks below the distrust line
while leaving genuinely on-topic answers trusted.
"""
import os

from knowledge.lightrag_confidence_scorer import LightRAGConfidenceScorer

CONTEXT_ONLY = {"only_need_context": True}

# The exact chunk that fed the hallucination (reference_id "2" in the ws110 log).
TAXONOMY = ("裤\n打底裤\n连衣裙\n公主裙\n纱裙\n套装\n两件套\n三件套\n睡衣\n"
            "家居服\n校服\n演出服\n汉服\n礼服\n【童装搜索关键词】")
# A genuinely on-topic returns-policy chunk for the same question.
POLICY = ("本店支持七天无理由退货，签收后七天内可申请，"
          "商品不影响二次销售即可，部分商品支持运费险。")


def _score(query, chunk, ref_id="1"):
    data = {
        "response": chunk,  # context-only: response is the chunk text
        "references": [{"reference_id": ref_id, "content": chunk}],
        "data": {"chunks": []},
    }
    return LightRAGConfidenceScorer().score(
        query=query, response_data=data, query_options=CONTEXT_ONLY
    )


def test_offtopic_taxonomy_is_capped_below_distrust_gate():
    c = _score("七天无理由退货吗", TAXONOMY)
    assert c.overall_score <= LightRAGConfidenceScorer.OFFTOPIC_SCORE_CAP
    assert c.overall_score < 0.50  # the Q&A prompt's distrust threshold
    assert c.retrieval.get("query_relevance") == 0.0
    assert "offtopic_cap" in c.retrieval.get("formula", "")


def test_material_question_vs_taxonomy_is_capped():
    # The 女童牛仔短裤 shape: asking material, only a category list retrieved.
    c = _score("这件女童牛仔短裤是什么材质成分", TAXONOMY)
    assert c.overall_score <= LightRAGConfidenceScorer.OFFTOPIC_SCORE_CAP


def test_ontopic_answer_stays_trusted():
    c = _score("七天无理由退货吗", POLICY)
    assert c.overall_score > 0.50  # must remain answerable
    assert c.retrieval.get("query_relevance") > 0.5
    assert "offtopic_cap" not in c.retrieval.get("formula", "")


def test_short_query_is_not_falsely_flagged():
    # Too few keywords to judge relevance -> no cap (relevance reported as None).
    c = _score("在吗", POLICY)
    assert c.retrieval.get("query_relevance") is None
    assert "offtopic_cap" not in c.retrieval.get("formula", "")


def test_env_disable_switch():
    os.environ["ECAN_RAG_RELEVANCE_GATE"] = "0"
    try:
        c = _score("七天无理由退货吗", TAXONOMY)
        # Gate off -> back to the un-capped (inflated) score.
        assert c.overall_score > 0.50
        assert "offtopic_cap" not in c.retrieval.get("formula", "")
    finally:
        del os.environ["ECAN_RAG_RELEVANCE_GATE"]


def _score_with(query, refs, chunks=None):
    data = {"response": "本店支持七天无理由退货，签收后七天内可申请。" * 2,
            "references": refs, "data": {"chunks": chunks or []}}
    return LightRAGConfidenceScorer().score(query=query, response_data=data)


def test_multiple_scored_references_do_not_crash_the_scorer():
    # Regression: statistics.pstdev was used without importing statistics, so
    # any response with >=2 scored chunks fell into the scoring_error branch
    # and was replaced by the no-answer message.
    refs = [{"reference_id": "1", "content": POLICY, "score": 0.82},
            {"reference_id": "2", "content": POLICY, "score": 0.64}]
    c = _score_with("七天无理由退货吗", refs)
    assert c.decision.get("no_answer_reason") != "scoring_error"
    assert c.decision.get("should_answer") is True
    assert c.retrieval.get("score_source") == "reference"


def test_passthrough_rerank_scores_are_ignored():
    # A disabled reranker returns relevance_score=1.0 for every chunk; that must
    # not be read as a perfect rerank signal.
    chunks = [{"content": POLICY, "rerank_score": 1.0},
              {"content": POLICY, "rerank_score": 1.0}]
    refs = [{"reference_id": "1", "content": POLICY, "score": 0.41},
            {"reference_id": "2", "content": POLICY, "score": 0.38}]
    c = _score_with("七天无理由退货吗", refs, chunks)
    assert c.retrieval.get("score_source") == "reference"
    assert c.retrieval.get("top1") < 0.5
