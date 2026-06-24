"""
LightRAG Query Response Confidence Scorer

Scoring is built on two primary signals:
  1. Retrieval score  — how semantically similar is the query to the source chunks
                        (from LightRAG vector/rerank scores)
  2. Faithfulness     — do key facts in the answer actually appear in the chunk text?
                        (requires include_chunk_content=True on the query)

Two proxy signals contribute when primary signals are absent or as minor adjustments:
  3. Completeness     — does the answer adequately address the query's scope?
  4. Quality          — is the answer a refusal/error? (negative gate only)

Formula (weights depend on which primary signals are available):

  retrieval + faithfulness:  0.50·R + 0.30·F + 0.15·C + 0.05·Q
  retrieval only:            0.65·R + 0.25·C + 0.10·Q   (cap 0.80)
  faithfulness only:         0.50·F + 0.35·C + 0.15·Q
  neither (proxy fallback):  0.65·C + 0.35·Q             (cap 0.55)
"""

from __future__ import annotations

import math
import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ConfidenceScore:
    """Confidence score result with detailed breakdown."""

    overall_score: float        # 0.0 – 1.0
    reference_score: float      # 0.0 – 1.0  (retrieval quality)
    faithfulness_score: float   # 0.0 – 1.0  (fact grounding)
    content_quality_score: float  # 0.0 – 1.0  (refusal/error gate)
    relevance_score: float      # kept for API compatibility; mirrors faithfulness
    completeness_score: float   # 0.0 – 1.0

    # Detailed metrics
    reference_count: int = 0
    response_length: int = 0
    has_structured_content: bool = False
    keyword_match_ratio: float = 0.0

    confidence_level: str = "unknown"
    explanation: str = ""

    retrieval: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 3),
            "confidence_level": self.confidence_level,
            "breakdown": {
                "reference_score": round(self.reference_score, 3),
                "faithfulness_score": round(self.faithfulness_score, 3),
                "content_quality_score": round(self.content_quality_score, 3),
                "relevance_score": round(self.relevance_score, 3),
                "completeness_score": round(self.completeness_score, 3),
            },
            "metrics": {
                "reference_count": self.reference_count,
                "response_length": self.response_length,
                "has_structured_content": self.has_structured_content,
                "keyword_match_ratio": round(self.keyword_match_ratio, 3),
            },
            "signals": {
                "retrieval": self.retrieval,
            },
            "decision": self.decision,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class LightRAGConfidenceScorer:
    """Evaluate confidence/quality of LightRAG query responses."""

    # Thresholds
    RERANK_THRESHOLD = 0.50
    EMBED_THRESHOLD = 0.60

    # Off-topic gate (2026-06-24): under the rag_query fast-path (mt047A:
    # mode=naive, only_need_context=True, enable_rerank=False — default ON) there
    # is NO retrieval/rerank score, so confidence falls back to the
    # faithfulness-only formula which never checks whether the retrieved chunk is
    # RELEVANT to the query. A well-formed but off-topic chunk (e.g. an apparel
    # category/keyword list) then scores ~0.92 "very_high", defeating the Q&A
    # prompt's "<0.50 → distrust" gate and getting mined for fabricated facts
    # (the 加绒/两件套 hallucination). When the only relevance signal we DO have —
    # query↔chunk keyword overlap — is near-zero, cap the score below the gate.
    OFFTOPIC_RELEVANCE_MAX = 0.12   # query↔chunk keyword overlap at/below this = off-topic
    OFFTOPIC_SCORE_CAP = 0.30       # cap overall to "low" so the prompt distrusts it
    OFFTOPIC_MIN_QUERY_KW = 3       # need ≥ this many query keywords for the ratio to be meaningful

    def score(
        self,
        query: str,
        response_data: Dict[str, Any],
        query_options: Optional[Dict[str, Any]] = None,
    ) -> ConfidenceScore:
        try:
            response_text = response_data.get("response", "")
            raw_references = response_data.get("references", [])
            chunks = (
                response_data.get("data", {}).get("chunks", [])
                if isinstance(response_data.get("data"), dict)
                else []
            )

            # --- 1. Filter & deduplicate references ----------------------------
            references = self._filter_references(raw_references)

            # --- 2. Retrieval signal -------------------------------------------
            retrieval_score, score_source, retrieval_signal = self._get_retrieval_signal(
                references, chunks
            )

            # --- 3. Faithfulness signal ----------------------------------------
            chunk_texts = self._extract_chunk_texts(references, chunks)
            faithfulness_score, faith_signal = self._calculate_faithfulness_score(
                response_text, chunk_texts
            )
            retrieval_signal["faithfulness"] = faith_signal

            # query↔context relevance — the signal the formula otherwise ignores
            query_relevance = self._query_context_relevance(query, chunk_texts)
            retrieval_signal["query_relevance"] = (
                round(query_relevance, 3) if query_relevance is not None else None
            )

            # --- 4. Completeness (proxy) ---------------------------------------
            completeness_score = self._calculate_completeness_score(
                response_text, query, query_options
            )

            # --- 5. Quality gate (refusal / error detection) ------------------
            is_context_only = bool((query_options or {}).get("only_need_context"))
            if is_context_only and references:
                quality_score = 1.0
            else:
                quality_score = self._calculate_quality_score(response_text)

            # --- 6. Weighted overall score ------------------------------------
            overall, formula_used = self._calculate_overall(
                retrieval_score=retrieval_score,
                faithfulness_score=faithfulness_score,
                completeness_score=completeness_score,
                quality_score=quality_score,
                ref_count=len(references),
                response_text=response_text,
                query_relevance=query_relevance,
            )
            retrieval_signal["formula"] = formula_used

            # --- 7. Decision --------------------------------------------------
            is_refusal = quality_score <= 0.15
            should_answer, no_answer_reason = self._make_decision(
                overall=overall,
                retrieval_score=retrieval_score,
                faithfulness_score=faithfulness_score,
                ref_count=len(references),
                is_refusal=is_refusal,
            )

            decision: Dict[str, Any] = {
                "should_answer": bool(should_answer),
                "no_answer_reason": no_answer_reason,
            }

            confidence_level = self._determine_confidence_level(overall)

            r_str = f"{retrieval_score:.2f}" if retrieval_score is not None else "n/a"
            f_str = f"{faithfulness_score:.2f}" if faithfulness_score is not None else "n/a"
            rel_str = f"{query_relevance:.2f}" if query_relevance is not None else "n/a"
            logger.info(
                f"📊 Confidence: {overall:.2f} ({confidence_level}) | "
                f"retrieval={r_str} faith={f_str} relevance={rel_str} "
                f"complete={completeness_score:.2f} quality={quality_score:.2f} "
                f"formula={formula_used} | "
                f"answer={should_answer} reason={no_answer_reason or 'pass'}"
            )

            # keyword_match_ratio kept for display purposes
            query_kw = self._extract_keywords(query)
            resp_kw = self._extract_keywords(response_text)
            kw_ratio = len(query_kw & resp_kw) / max(len(query_kw), 1) if query_kw else 0.0

            return ConfidenceScore(
                overall_score=overall,
                reference_score=retrieval_score if retrieval_score is not None else 0.0,
                faithfulness_score=faithfulness_score if faithfulness_score is not None else 0.0,
                content_quality_score=quality_score,
                relevance_score=faithfulness_score if faithfulness_score is not None else 0.0,
                completeness_score=completeness_score,
                reference_count=len(references),
                response_length=len(response_text),
                has_structured_content=self._has_structured_content(response_text),
                keyword_match_ratio=kw_ratio,
                confidence_level=confidence_level,
                explanation=self._generate_explanation(
                    overall, retrieval_score, faithfulness_score,
                    quality_score, completeness_score, len(references)
                ),
                retrieval=retrieval_signal,
                decision=decision,
            )

        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            return ConfidenceScore(
                overall_score=0.0,
                reference_score=0.0,
                faithfulness_score=0.0,
                content_quality_score=0.0,
                relevance_score=0.0,
                completeness_score=0.0,
                confidence_level="unknown",
                explanation=f"Scoring error: {e}",
                retrieval={},
                decision={"should_answer": False, "no_answer_reason": "scoring_error"},
            )

    # -------------------------------------------------------------------------
    # Retrieval signal
    # -------------------------------------------------------------------------

    def _get_retrieval_signal(
        self,
        references: List[Dict],
        chunks: List[Dict],
    ) -> Tuple[Optional[float], str, Dict]:
        """Extract retrieval score from chunks (prefer rerank) or references."""
        scores: List[float] = []
        score_source = "none"

        # Priority 1: rerank scores from chunks
        for chunk in chunks:
            s = self._extract_normalized_score(chunk, prefer_rerank=True)
            if s is not None:
                scores.append(s)
        if scores:
            score_source = "rerank"

        # Priority 2: scores from references
        if not scores:
            for ref in references:
                s = self._extract_normalized_score(ref, prefer_rerank=False)
                if s is not None:
                    scores.append(s)
            if scores:
                score_source = "reference"

        if not scores:
            signal: Dict[str, Any] = {
                "score_source": "none",
                "threshold": self.RERANK_THRESHOLD,
                "top1": None, "avg": None, "supporting_refs": 0,
                "scored_refs": 0,
            }
            return None, "none", signal

        threshold = self.RERANK_THRESHOLD if score_source == "rerank" else self.EMBED_THRESHOLD
        scores_sorted = sorted(scores, reverse=True)
        top_k = scores_sorted[:min(5, len(scores_sorted))]
        rank_weights = [1.0 / (i + 1) for i in range(len(top_k))]
        w_sum = sum(rank_weights)
        weighted_avg = sum(s * w for s, w in zip(top_k, rank_weights)) / w_sum
        top1 = top_k[0]
        supporting = sum(1 for s in scores_sorted if s >= threshold)
        coverage = supporting / max(len(references), 1)

        consistency = 1.0
        if len(top_k) >= 2:
            consistency = self._clamp(1.0 - statistics.pstdev(top_k) / 0.35)

        retrieval_strength = (
            0.45 * top1 + 0.30 * weighted_avg + 0.15 * coverage + 0.10 * consistency
        )
        retrieval_strength = self._clamp(retrieval_strength)

        signal = {
            "score_source": score_source,
            "threshold": threshold,
            "top1": round(top1, 4),
            "avg": round(weighted_avg, 4),
            "supporting_refs": supporting,
            "scored_refs": len(scores_sorted),
            "retrieval_strength": round(retrieval_strength, 4),
            "coverage": round(coverage, 4),
            "consistency": round(consistency, 4),
        }
        return retrieval_strength, score_source, signal

    def _extract_normalized_score(self, item: Any, prefer_rerank: bool) -> Optional[float]:
        if not isinstance(item, dict):
            return None
        candidates = []
        if prefer_rerank and "rerank_score" in item:
            candidates.append(("rerank_score", item["rerank_score"]))
        for key in ("score", "similarity", "relevance", "distance"):
            if key in item:
                candidates.append((key, item[key]))
        if not prefer_rerank and "rerank_score" in item:
            candidates.append(("rerank_score", item["rerank_score"]))
        for key, raw in candidates:
            n = self._normalize_score(raw, key)
            if n is not None:
                return n
        return None

    def _normalize_score(self, raw: Any, score_type: str) -> Optional[float]:
        if raw is None:
            return None
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if score_type == "distance":
            if v < 0:
                return None
            return self._clamp(1.0 - v) if v <= 1.0 else self._clamp(1.0 / (1.0 + v))
        if v < 0:
            return self._clamp((v + 1.0) / 2.0) if v >= -1.0 else None
        if v <= 1.0:
            return self._clamp(v)
        if v <= 100.0:
            return self._clamp(v / 100.0)
        return 1.0

    # -------------------------------------------------------------------------
    # Faithfulness signal
    # -------------------------------------------------------------------------

    def _extract_chunk_texts(
        self, references: List[Dict], chunks: List[Dict]
    ) -> List[str]:
        """Collect all chunk text from references (content field) and raw chunks."""
        texts: List[str] = []
        for ref in references:
            content = ref.get("content")
            if isinstance(content, list):
                texts.extend(c for c in content if isinstance(c, str) and c.strip())
            elif isinstance(content, str) and content.strip():
                texts.append(content)
        for chunk in chunks:
            text = chunk.get("content", "")
            if isinstance(text, str) and text.strip():
                texts.append(text)
        return texts

    def _calculate_faithfulness_score(
        self, response_text: str, chunk_texts: List[str]
    ) -> Tuple[Optional[float], Dict]:
        """
        Check what fraction of verifiable facts in the answer appear in the
        source chunk text.  Returns None when chunk content is unavailable.
        """
        if not chunk_texts:
            return None, {"available": False, "reason": "no_chunk_content"}

        if not response_text or not response_text.strip():
            return None, {"available": False, "reason": "empty_response"}

        combined = " ".join(chunk_texts).lower()
        key_facts = self._extract_key_facts(response_text)

        # Character bigram overlap — always computed as a soft signal
        overlap = self._character_overlap(response_text, combined)
        overlap_score = 0.35 + 0.55 * overlap  # range [0.35, 0.90]

        if not key_facts:
            return self._clamp(overlap_score), {
                "available": True,
                "method": "character_overlap",
                "overlap": round(overlap, 3),
                "score": round(overlap_score, 3),
            }

        matched = [f for f in key_facts if f.lower() in combined]
        ratio = len(matched) / len(key_facts)
        fact_score = 0.10 + 0.90 * ratio  # 0% → 0.10, 100% → 1.0

        # When fact matching looks weak, fall back to bigram overlap as a floor.
        # Knowledge-graph chunks (from LightRAG mix mode) often omit raw numbers
        # but will still share topical Chinese terms with the answer.
        if ratio < 0.30 and len(key_facts) <= 4:
            # Low-evidence situation: trust overlap more
            score = max(fact_score, overlap_score * 0.85)
        else:
            # Sufficient facts checked: blend, weighting fact matching higher
            score = 0.65 * fact_score + 0.35 * overlap_score

        logger.debug(
            f"Faithfulness: facts={len(matched)}/{len(key_facts)} ({ratio:.0%}) "
            f"fact_score={fact_score:.2f} overlap={overlap:.2f} final={score:.2f}"
        )
        return self._clamp(score), {
            "available": True,
            "method": "fact+overlap",
            "key_facts_count": len(key_facts),
            "matched_count": len(matched),
            "match_ratio": round(ratio, 3),
            "overlap": round(overlap, 3),
            "score": round(score, 3),
        }

    def _extract_key_facts(self, text: str) -> List[str]:
        """
        Extract verifiable facts: numbers with units, ranges, size codes.
        These are the facts most likely to be hallucinated and easiest to verify.
        """
        facts: List[str] = []

        # Number ranges: 100-104, 65~72
        facts += re.findall(r'\d+\s*[-~—]\s*\d+', text)

        # Numbers with Chinese units: 45厘米, 1.5公斤, 175cm
        facts += re.findall(
            r'\d+(?:[.,]\d+)?\s*(?:厘米|毫米|公分|公里|公斤|克|升|毫升|cm|mm|kg|g|ml|L|℃|°C)',
            text, re.IGNORECASE
        )

        # Size codes: L码, XL码, XS, S, M, L, XL, XXL
        facts += re.findall(r'(?:X{0,3}S|X{0,3}L|M)\s*码?', text)

        # Standalone 2-4 digit numbers (sizes, measurements like 175, 45)
        facts += re.findall(r'\b\d{2,4}\b', text)

        # Deduplicate and strip
        seen: set = set()
        result: List[str] = []
        for f in facts:
            cleaned = f.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result

    def _character_overlap(self, answer: str, source: str) -> float:
        """
        Fraction of Chinese character bigrams from the answer that appear in source.
        Used as a softer faithfulness signal when there are no numeric key facts.
        """
        answer_chars = re.findall(r'[一-鿿]', answer)
        if len(answer_chars) < 2:
            return 0.5  # neutral for very short or non-Chinese answers
        bigrams = {answer_chars[i] + answer_chars[i + 1] for i in range(len(answer_chars) - 1)}
        if not bigrams:
            return 0.5
        matched = sum(1 for bg in bigrams if bg in source)
        return matched / len(bigrams)

    # -------------------------------------------------------------------------
    # Proxy signals
    # -------------------------------------------------------------------------

    def _calculate_quality_score(self, response_text: str) -> float:
        """
        1.0 by default.  Drops to ~0.1 when the response is a refusal or error.
        Acts mainly as a negative gate; only contributes 5% to the total score.
        """
        if not response_text or len(response_text.strip()) < 5:
            return 0.0

        refusal_phrases = [
            "i don't know", "i cannot", "i'm unable", "i am unable",
            "no information", "cannot find", "couldn't find", "could not find",
            "not enough relevant context", "not found",
            "无法回答", "无法找到", "找不到", "没有相关", "无相关信息",
            "无法提供", "不确定", "没有找到", "抱歉，我", "对不起，我",
            "我没有", "无从得知",
        ]
        text_lower = response_text.lower()
        for phrase in refusal_phrases:
            if phrase in text_lower:
                return 0.1

        return 1.0

    def _calculate_completeness_score(
        self,
        response: str,
        query: str,
        query_options: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Score based on response length relative to query complexity."""
        if not response:
            return 0.0

        length = len(response)
        if length < 20:
            length_score = 0.15
        elif length < 80:
            length_score = 0.45
        elif length < 250:
            length_score = 0.65
        elif length < 600:
            length_score = 0.82
        elif length < 1200:
            length_score = 0.92
        else:
            length_score = 1.0

        # Multi-aspect bonus: query contains multiple question words or commas
        cn_q_words = len(re.findall(r'[？?]', query))
        multi_aspect = cn_q_words > 1 or query.count('，') >= 2 or query.count(',') >= 2
        if multi_aspect:
            # Check response covers multiple sentences
            sentence_count = (
                response.count('。') + response.count('.') +
                response.count('！') + response.count('!')
            )
            if sentence_count < 2:
                length_score *= 0.75  # penalise incomplete multi-aspect answers

        return self._clamp(length_score)

    # -------------------------------------------------------------------------
    # Overall formula
    # -------------------------------------------------------------------------

    def _calculate_overall(
        self,
        retrieval_score: Optional[float],
        faithfulness_score: Optional[float],
        completeness_score: float,
        quality_score: float,
        ref_count: int,
        response_text: str = "",
        query_relevance: Optional[float] = None,
    ) -> Tuple[float, str]:
        has_R = retrieval_score is not None
        has_F = faithfulness_score is not None

        if has_R and has_F:
            score = (
                0.50 * retrieval_score +
                0.30 * faithfulness_score +
                0.15 * completeness_score +
                0.05 * quality_score
            )
            formula = "R50+F30+C15+Q5"

        elif has_R:
            score = (
                0.65 * retrieval_score +
                0.25 * completeness_score +
                0.10 * quality_score
            )
            score = min(score, 0.80)  # cap: faithfulness unverified
            formula = "R65+C25+Q10_cap80"

        elif has_F:
            score = (
                0.50 * faithfulness_score +
                0.35 * completeness_score +
                0.15 * quality_score
            )
            formula = "F50+C35+Q15"

        else:
            # Proxy fallback — no primary signals.
            # Reference count and answer specificity are the best available signals.
            if ref_count == 0:
                score = 0.12
                formula = "no_refs"
            else:
                # ref_conf: diminishing returns — 1→0.25, 3→0.57, 5→0.76
                ref_conf = 1.0 - math.exp(-ref_count / 3.5)
                # specificity: does the answer contain verifiable facts (numbers,
                # measurements, size codes)?  A fluent but vague answer scores low.
                key_facts = self._extract_key_facts(response_text)
                specificity = self._clamp(len(key_facts) / 4.0)
                score = (
                    0.35 * ref_conf +
                    0.28 * specificity +
                    0.22 * completeness_score +
                    0.15 * quality_score
                )
                formula = "refconf+spec+C+Q"

        # Off-topic gate: when there is NO retrieval/rerank signal (the fast-path),
        # an off-topic-but-well-formed chunk can still score high. If the only
        # relevance signal we have — query↔chunk keyword overlap — is near-zero,
        # cap the score below the prompt's distrust gate. Only applies without R
        # (with R the retrieval score already reflects relevance). Env-disable:
        # ECAN_RAG_RELEVANCE_GATE=0.
        if (not has_R
                and query_relevance is not None
                and query_relevance <= self.OFFTOPIC_RELEVANCE_MAX
                and self._clamp(score) > self.OFFTOPIC_SCORE_CAP
                and (os.getenv("ECAN_RAG_RELEVANCE_GATE") or "1").strip().lower()
                     in ("1", "true", "yes", "on")):
            score = self.OFFTOPIC_SCORE_CAP
            formula = f"{formula}_offtopic_cap{int(self.OFFTOPIC_SCORE_CAP * 100)}"

        return self._clamp(score), formula

    # -------------------------------------------------------------------------
    # Decision
    # -------------------------------------------------------------------------

    def _make_decision(
        self,
        overall: float,
        retrieval_score: Optional[float],
        faithfulness_score: Optional[float],
        ref_count: int,
        is_refusal: bool,
    ) -> Tuple[bool, Optional[str]]:
        if is_refusal:
            return False, "llm_refused"
        if ref_count == 0:
            return False, "no_references"
        if retrieval_score is not None and retrieval_score < 0.18:
            return False, "low_retrieval"
        if overall < 0.22:
            return False, "overall_too_low"
        return True, None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _filter_references(self, references: List[Any]) -> List[Dict]:
        valid: List[Dict] = []
        seen_paths: set = set()
        for ref in references:
            if not isinstance(ref, dict):
                continue
            fp = ref.get("file_path", "")
            has_fp = fp and fp != "unknown_source"
            has_id = ref.get("reference_id")
            if not (has_fp or has_id):
                continue
            if fp and fp in seen_paths:
                continue
            if fp:
                seen_paths.add(fp)
            valid.append(ref)
        return valid

    def _determine_confidence_level(self, score: float) -> str:
        if score >= 0.85:
            return "very_high"
        if score >= 0.70:
            return "high"
        if score >= 0.50:
            return "medium"
        if score >= 0.30:
            return "low"
        return "very_low"

    def _generate_explanation(
        self,
        overall: float,
        retrieval_score: Optional[float],
        faithfulness_score: Optional[float],
        quality_score: float,
        completeness_score: float,
        ref_count: int,
    ) -> str:
        level = self._determine_confidence_level(overall)
        parts = []
        labels = {
            "very_high": "Very high confidence.",
            "high": "High confidence.",
            "medium": "Medium confidence.",
            "low": "Low confidence.",
            "very_low": "Very low confidence.",
        }
        parts.append(labels.get(level, ""))

        if ref_count == 0:
            parts.append("No source references found.")
        else:
            parts.append(f"{ref_count} reference(s) retrieved.")

        if retrieval_score is not None:
            if retrieval_score >= 0.70:
                parts.append("Strong retrieval match.")
            elif retrieval_score >= 0.45:
                parts.append("Moderate retrieval match.")
            else:
                parts.append("Weak retrieval match.")
        else:
            parts.append("No retrieval scores available.")

        if faithfulness_score is not None:
            if faithfulness_score >= 0.80:
                parts.append("Answer well grounded in sources.")
            elif faithfulness_score >= 0.50:
                parts.append("Answer partially grounded in sources.")
            else:
                parts.append("Answer facts poorly supported by sources.")
        else:
            parts.append("Faithfulness not verified (no chunk content).")

        if quality_score <= 0.15:
            parts.append("Response appears to be a refusal or error.")

        return " ".join(parts)

    def _has_structured_content(self, text: str) -> bool:
        return bool(
            re.search(r'[•\-\*]\s', text) or
            re.search(r'\d+[\.\)]\s', text) or
            text.count('\n\n') >= 1
        )

    def _extract_keywords(self, text: str) -> set:
        """
        Keyword extractor supporting Chinese (unigrams + bigrams) and ASCII.
        Used only for the display keyword_match_ratio metric.
        """
        char_stop = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都',
            '一', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
            '啊', '哦', '嗯', '吧', '呢', '吗', '么', '呀',
        }
        word_stop = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
            'be', 'been', '没有', '一个', '多少', '什么', '怎么', '哪个',
        }
        keywords: set = set()
        for word in re.findall(r'[a-z0-9]+', text.lower()):
            if word not in word_stop and (len(word) >= 2 or word.isalpha()):
                keywords.add(word)
        cn = re.findall(r'[一-鿿]', text)
        for ch in cn:
            if ch not in char_stop:
                keywords.add(ch)
        for i in range(len(cn) - 1):
            bg = cn[i] + cn[i + 1]
            if bg not in word_stop:
                keywords.add(bg)
        return keywords

    def _query_context_relevance(
        self, query: str, chunk_texts: List[str]
    ) -> Optional[float]:
        """
        Fraction of the query's keywords (Chinese unigrams+bigrams / ASCII words)
        that appear in the retrieved chunk text. This is the query↔CONTEXT
        relevance the confidence formula otherwise ignores. Returns None when the
        query is too short to score meaningfully (avoids false off-topic flags).
        """
        if not chunk_texts:
            return None
        query_kw = self._extract_keywords(query or "")
        if len(query_kw) < self.OFFTOPIC_MIN_QUERY_KW:
            return None
        chunk_kw = self._extract_keywords(" ".join(chunk_texts))
        if not chunk_kw:
            return 0.0
        return len(query_kw & chunk_kw) / len(query_kw)

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def score_lightrag_response(
    query: str,
    response_data: Dict[str, Any],
    query_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score a LightRAG query response and return a dict."""
    return LightRAGConfidenceScorer().score(query, response_data, query_options).to_dict()
