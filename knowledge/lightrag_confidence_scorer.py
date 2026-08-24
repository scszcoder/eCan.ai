"""
LightRAG Query Response Confidence Scorer (v2 - 2026-08-24)

新的置信度计算逻辑：

1. 核心原则：置信度应该反映"LLM 生成的答案是否可靠"，而不是"检索是否成功"

2. 主要信号：
   - LLM_response_is_refusal: LLM 是否拒绝回答（最重要的信号）
   - LLM_response_has_content: LLM 是否生成了实质内容
   - LLM_response_matches_context: LLM 回答是否与检索内容相关
   - retrieval_score: 检索质量（辅助信号）
   - reference_count: 参考来源数量

3. 决策逻辑：
   - 如果 LLM 生成了实质性回答 → 应该显示该回答
   - 如果 LLM 拒绝回答或无内容 → 显示"未找到"
   - 置信度分数用于提示用户答案的可靠程度，但不应阻止显示

4. 关键修复 (v2):
   - streaming 时正确累积 references
   - 考虑 LLM 实际生成的 raw_response
   - 简化决策逻辑：优先显示 LLM 输出
"""

from __future__ import annotations

import math
import re
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

    # Threshold constants (行业推荐值)
    RERANK_THRESHOLD = 0.30   # BGE-Reranker 推荐的最小分数
    EMBED_THRESHOLD = 0.35    # Cosine similarity 阈值
    MIN_RESPONSE_LENGTH = 30    # 有意义回答的最小长度
    REFUSAL_THRESHOLD = 0.20  # 低于此值认为是拒绝回答
    OFFTOPIC_MIN_QUERY_KW = 2  # 查询关键词最小数量，低于此值跳过离题检测

    def score(
        self,
        query: str,
        response_data: Dict[str, Any],
        query_options: Optional[Dict[str, Any]] = None,
    ) -> ConfidenceScore:
        """
        计算置信度的核心方法 (v2)

        核心逻辑：
        1. 首先判断 LLM 是否生成了实质内容
        2. 如果有实质内容，置信度应该较高（即使检索分数低）
        3. 如果是拒绝/无内容，置信度应该低
        """
        try:
            # 获取 LLM 生成的原始回答
            response_text = response_data.get("response", "")
            raw_response = response_data.get("raw_response", "")

            # 使用 raw_response 作为实质内容判断依据
            # 因为 response 可能被前端覆盖为 "未找到"
            llm_actual_content = raw_response if raw_response else response_text

            # 获取 references 和 chunks
            raw_references = response_data.get("references", [])
            chunks = (
                response_data.get("data", {}).get("chunks", [])
                if isinstance(response_data.get("data"), dict)
                else []
            )

            # 去重 references
            references = self._filter_references(raw_references)

            # 判断 LLM 是否生成了实质内容
            is_refusal, refusal_reason = self._detect_refusal(llm_actual_content, references)
            has_substantial_content = len(llm_actual_content.strip()) >= self.MIN_RESPONSE_LENGTH

            # 计算检索分数
            retrieval_score, score_source, retrieval_signal = self._get_retrieval_signal(
                references, chunks
            )

            # 提取 chunk 内容用于计算 faithfulness
            chunk_texts = self._extract_chunk_texts(references, chunks)
            faithfulness_score, faith_signal = self._calculate_faithfulness_score(
                llm_actual_content, chunk_texts
            )
            retrieval_signal["faithfulness"] = faith_signal

            # 计算查询-内容相关性
            query_relevance = self._query_context_relevance(query, chunk_texts)
            retrieval_signal["query_relevance"] = (
                round(query_relevance, 3) if query_relevance is not None else None
            )

            # 计算完整度
            completeness_score = self._calculate_completeness_score(
                llm_actual_content, query, query_options
            )

            # 计算质量分数（用于拒绝检测）
            quality_score = self._calculate_quality_score(llm_actual_content)

            # 计算总体置信度
            overall, formula_used = self._calculate_overall_v2(
                llm_has_content=has_substantial_content,
                is_refusal=is_refusal,
                retrieval_score=retrieval_score,
                faithfulness_score=faithfulness_score,
                completeness_score=completeness_score,
                quality_score=quality_score,
                ref_count=len(references),
                response_text=llm_actual_content,
                query_relevance=query_relevance,
            )
            retrieval_signal["formula"] = formula_used

            # 决策：是否应该显示 LLM 的回答
            should_answer = self._make_decision_v2(
                llm_has_content=has_substantial_content,
                is_refusal=is_refusal,
                overall=overall,
                retrieval_score=retrieval_score,
                ref_count=len(references),
            )

            # 如果应该显示回答，但置信度很低，给出警告原因
            if should_answer and overall < 0.4:
                decision_reason = "low_confidence_but_content_exists"
            elif is_refusal:
                decision_reason = refusal_reason
            elif not has_substantial_content:
                decision_reason = "no_substantial_content"
            else:
                decision_reason = None

            decision: Dict[str, Any] = {
                "should_answer": bool(should_answer),
                "no_answer_reason": decision_reason,
                "is_refusal": is_refusal,
                "has_substantial_content": has_substantial_content,
            }

            confidence_level = self._determine_confidence_level(overall)

            # 日志输出
            retrieval_str = f"{retrieval_score:.2f}" if retrieval_score is not None else "n/a"
            faith_str = f"{faithfulness_score:.2f}" if faithfulness_score is not None else "n/a"
            logger.info(
                f"📊 Confidence v2: {overall:.2f} ({confidence_level}) | "
                f"content={has_substantial_content} refusal={is_refusal} "
                f"retrieval={retrieval_str} "
                f"faith={faith_str} "
                f"refs={len(references)} | "
                f"should_answer={should_answer}"
            )

            # 计算关键词匹配度
            query_kw = self._extract_keywords(query)
            resp_kw = self._extract_keywords(llm_actual_content)
            kw_ratio = len(query_kw & resp_kw) / max(len(query_kw), 1) if query_kw else 0.0

            return ConfidenceScore(
                overall_score=overall,
                reference_score=retrieval_score if retrieval_score is not None else 0.0,
                faithfulness_score=faithfulness_score if faithfulness_score is not None else 0.0,
                content_quality_score=quality_score,
                relevance_score=faithfulness_score if faithfulness_score is not None else 0.0,
                completeness_score=completeness_score,
                reference_count=len(references),
                response_length=len(llm_actual_content),
                has_structured_content=self._has_structured_content(llm_actual_content),
                keyword_match_ratio=kw_ratio,
                confidence_level=confidence_level,
                explanation=self._generate_explanation_v2(
                    overall, has_substantial_content, is_refusal,
                    retrieval_score, faithfulness_score, len(references)
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

    def _detect_refusal(
        self, response_text: str, references: List[Dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        检测 LLM 是否拒绝了回答

        拒绝的常见模式：
        1. 直接拒绝：抱歉、我不知道、没有信息
        2. 空内容：回答太短或只有标点
        3. 通用回复：无法回答、无法确定
        """
        if not response_text or not response_text.strip():
            return True, "empty_response"

        text_lower = response_text.lower().strip()

        # 拒绝关键词
        refusal_patterns = [
            r'^抱歉', r'^对不起', r'^我无法', r'^我不知道',
            r'^无法', r'^不能', r'^没有找到', r'^没有相关',
            r"couldn't", r"don't know", r"cannot", r"unable",
            r"i'm sorry", r"don't have", r"no information",
        ]

        for pattern in refusal_patterns:
            if re.search(pattern, text_lower):
                return True, "refusal_pattern_detected"

        # 短回答但有关键词（可能是真实的简短回答）
        if len(response_text.strip()) < 20:
            return False, None  # 不算拒绝，可能是简短的真实回答

        return False, None

    # -------------------------------------------------------------------------
    # Overall formula v2
    # -------------------------------------------------------------------------

    def _calculate_overall_v2(
        self,
        llm_has_content: bool,
        is_refusal: bool,
        retrieval_score: Optional[float],
        faithfulness_score: Optional[float],
        completeness_score: float,
        quality_score: float,
        ref_count: int,
        response_text: str = "",
        query_relevance: Optional[float] = None,
    ) -> Tuple[float, str]:
        """
        计算总体置信度 (v2)

        核心逻辑：
        - 如果 LLM 生成了实质内容且不是拒绝 → 高置信度
        - 如果是拒绝或无内容 → 低置信度
        - 检索分数作为辅助调整
        """
        # 情况1：LLM 拒绝或无内容 → 很低置信度
        if is_refusal:
            return 0.10, "refusal"

        if not llm_has_content:
            return 0.15, "no_content"

        has_R = retrieval_score is not None
        has_F = faithfulness_score is not None

        # 情况2：LLM 有内容，使用加权公式
        if has_R and has_F:
            # retrieval + faithfulness 都可用
            score = (
                0.40 * retrieval_score +
                0.35 * faithfulness_score +
                0.15 * completeness_score +
                0.10 * quality_score
            )
            formula = "v2_R40+F35+C15+Q10"

        elif has_R:
            # 只有 retrieval
            score = (
                0.55 * retrieval_score +
                0.25 * completeness_score +
                0.20 * quality_score
            )
            formula = "v2_R55+C25+Q20"

        elif has_F:
            # 只有 faithfulness
            score = (
                0.50 * faithfulness_score +
                0.30 * completeness_score +
                0.20 * quality_score
            )
            formula = "v2_F50+C30+Q20"

        else:
            # 无检索信号，使用代理信号
            if ref_count == 0:
                score = 0.25
                formula = "v2_no_signals"
            else:
                # 基于参考数量和内容长度
                ref_conf = min(1.0, ref_count / 5.0)
                length_ratio = min(1.0, len(response_text) / 500.0)
                score = 0.40 * ref_conf + 0.35 * length_ratio + 0.25 * quality_score
                formula = "v2_proxy"

        # Off-topic 检测：如果 query_relevance 很低但 LLM 生成了内容
        # 说明可能是 LLM 在编造（低检索+高内容 = 危险）
        if query_relevance is not None and query_relevance < 0.15 and has_R and retrieval_score and retrieval_score < 0.3:
            score = min(score, 0.35)  # 降低置信度
            formula = f"{formula}_low_relevance"

        return self._clamp(score), formula

    # -------------------------------------------------------------------------
    # Decision v2
    # -------------------------------------------------------------------------

    def _make_decision_v2(
        self,
        llm_has_content: bool,
        is_refusal: bool,
        overall: float,
        retrieval_score: Optional[float],
        ref_count: int,
    ) -> bool:
        """
        决定是否应该显示 LLM 的回答 (v2)

        核心逻辑：优先显示 LLM 的回答
        - 只有在明确是拒绝时才不显示
        - 低置信度但有内容时仍然显示，但添加警告
        """
        # 明确拒绝 → 不显示
        if is_refusal:
            return False

        # 没有实质内容 → 不显示
        if not llm_has_content:
            return False

        # 有实质内容 → 显示（即使置信度低）
        return True

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

    def _generate_explanation_v2(
        self,
        overall: float,
        llm_has_content: bool,
        is_refusal: bool,
        retrieval_score: Optional[float],
        faithfulness_score: Optional[float],
        ref_count: int,
    ) -> str:
        """生成解释文本 (v2)"""
        if is_refusal:
            return "LLM refused to answer. No reliable information available."

        if not llm_has_content:
            return "LLM generated no substantial content."

        level = self._determine_confidence_level(overall)
        level_text = {
            "very_high": "Very high confidence",
            "high": "High confidence",
            "medium": "Medium confidence",
            "low": "Low confidence",
            "very_low": "Very low confidence",
        }.get(level, "Unknown confidence")

        parts = [f"{level_text}."]

        if ref_count > 0:
            parts.append(f"{ref_count} reference(s) retrieved.")

        if retrieval_score is not None:
            if retrieval_score >= 0.6:
                parts.append("Strong retrieval match.")
            elif retrieval_score >= 0.4:
                parts.append("Moderate retrieval match.")
            else:
                parts.append("Weak retrieval match.")

        if faithfulness_score is not None and faithfulness_score >= 0.6:
            parts.append("Answer well grounded in retrieved content.")

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
