import re
import math
import json
from app.config import settings

QUESTION_RE = re.compile(r"\?|who |what |why |how |when |where |which |would |could |should ")
SUPERLATIVE_RE = re.compile(r"\bbest\b|\bworst\b|\bmost\b|\bleast\b|\bonly\b|\bnever\b|\balways\b|\bfirst\b|\bfastest\b|\bslowest\b")
NUMERAL_RE = re.compile(r"\b\d+\b")
NEGATION_RE = re.compile(r"\bnot\b|\bnever\b|\bdon't\b|\bcan't\b|\bwon't\b|\bisn't\b|\bdoesn't\b|\bdidn't\b")
PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b")
CONTRARIAN_RE = re.compile(r"\bactually\b|\bwrong\b|\bmyth\b|\bmistake\b|\bmisconception\b|\bcontrary\b|\bcontroversial\b|\bdebunk\b")
INTENSITY_RE = re.compile(r"!|amazing|incredible|unbelievable|shocking|insane|crazy|unreal")
SELF_REF_RE = re.compile(r"\bthis\b|\bthat\b|\bit\b|\bthey\b")

WINDOW_SIZES = [15, 30, 45, 60]


def _text_block(segments, start, end):
    texts = []
    for s in segments:
        if s["start"] >= end:
            break
        if s["end"] <= start:
            continue
        texts.append(s["text"].strip())
    return " ".join(texts)


def generate_candidates(segments: list[dict], duration: float) -> list[dict]:
    candidates = []
    if not segments:
        return candidates
    sentence_ends = []
    for s in segments:
        if s["text"].strip().endswith((".", "!", "?")):
            sentence_ends.append(s["end"])
    if not sentence_ends:
        sentence_ends = [s["end"] for s in segments]
    for boundary in sentence_ends:
        for wsize in WINDOW_SIZES:
            start = max(0, boundary - wsize * 0.4)
            end = min(duration, start + wsize)
            candidates.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "size": round(end - start, 2),
            })
    seen = set()
    unique = []
    for c in candidates:
        key = (round(c["start"], 1), round(c["end"], 1))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _count_pattern(text, pattern):
    return len(pattern.findall(text))


def score_candidate(candidate: dict, segments: list[dict], audio_rms: float = None) -> tuple[float, list[str], list[str]]:
    text = _text_block(segments, candidate["start"], candidate["end"])
    if not text.strip():
        return 0, [], ["No speech in window"]

    reasons = []
    weaknesses = []
    w = settings.HOOK_SCORE_WEIGHTS.copy()

    # curiosity: question marks
    questions = _count_pattern(text, QUESTION_RE)
    curiosity = min(100, questions * 40)
    if questions > 0:
        reasons.append(f"+ {questions} question(s)")

    # emotional intensity
    intensity = min(100, _count_pattern(text, INTENSITY_RE) * 30)
    if intensity > 0:
        reasons.append("+ Emotional intensity words")

    # specificity: numerals + named entities
    specifics = min(100, _count_pattern(text, NUMERAL_RE) * 20 + _count_pattern(text, PROPER_NOUN_RE) * 15)
    if specifics > 0:
        reasons.append("+ Specific references")

    # novelty: contrarian phrasing
    novelty = min(100, _count_pattern(text, CONTRARIAN_RE) * 35)
    if novelty > 0:
        reasons.append("+ Contrarian/framing claim")

    # conflict: negation
    conflict = min(100, _count_pattern(text, NEGATION_RE) * 25)
    if conflict > 0:
        reasons.append("+ Strong assertion/negation")

    # payoff: does the text contain a resolution word
    payoff_words = re.compile(r"\bso\b|\btherefore\b|\bbecause\b|\bresult\b|\bturns out\b|\bhere's why\b")
    payoff = min(100, _count_pattern(text, payoff_words) * 40)
    if payoff > 0:
        reasons.append("+ Story payoff / resolution")

    # self-contained: penalty for self-references at start
    opening = text[:min(50, len(text))]
    self_refs = _count_pattern(opening, SELF_REF_RE)
    self_contained = max(0, 100 - self_refs * 30)
    if self_refs > 0:
        weaknesses.append(f"Opening references antecedent ({self_refs}x)")

    # speech energy
    speech_energy = min(100, (audio_rms or 50))

    # context completeness
    context_completeness = 100 if text[0:1] not in (" ",) and not text.lower().startswith(("he ", "she ", "they ", "it ", "this ")) else 60

    # transcript confidence
    confs = [s.get("confidence", 0.5) for s in segments if s["end"] > candidate["start"] and s["start"] < candidate["end"]]
    avg_conf = sum(confs) / len(confs) if confs else 0.5
    transcript_conf = avg_conf * 100

    scores = {
        "curiosity": curiosity,
        "emotional_intensity": intensity,
        "specificity": specifics,
        "novelty": novelty,
        "conflict": conflict,
        "payoff": payoff,
        "self_contained": self_contained,
        "speech_energy": speech_energy,
        "context_completeness": context_completeness,
        "transcript_confidence": transcript_conf,
        "llm_score": 50,  # placeholder; LLM provider fills this
    }

    final = (
        scores["curiosity"] * w["curiosity"]
        + scores["emotional_intensity"] * w["emotional_intensity"]
        + scores["specificity"] * w["specificity"]
        + scores["novelty"] * w["novelty"]
        + scores["conflict"] * w["conflict"]
        + scores["payoff"] * w["payoff"]
        + scores["self_contained"] * w["self_contained"]
        + scores["speech_energy"] * w["speech_energy"]
        + scores["context_completeness"] * w["context_completeness"]
        + scores["llm_score"] * w["llm_score"]
    )

    if not reasons:
        reasons.append("Meets minimum speech threshold")
    if self_contained < 60:
        weaknesses.append("Lacks self-contained opening")

    return round(final, 1), reasons, weaknesses
