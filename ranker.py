#!/usr/bin/env python3
"""
Redrob Intelligent Candidate Ranker
Core insight: score against evidence of real work, not stated keywords.
Three-layer scoring: Role Fit × Evidence Quality × Availability
"""

import json
import csv
import re
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────────

TODAY = date(2026, 6, 28)

# Companies the JD explicitly disqualifies (consulting-only backgrounds)
CONSULTING_FIRMS = {
    'tcs', 'tata consultancy', 'infosys', 'wipro', 'accenture', 'cognizant',
    'capgemini', 'hcl technologies', 'hcl tech', 'tech mahindra', 'mphasis',
    'hexaware', 'ltimindtree', 'mindtree', 'l&t infotech', 'persistent systems',
    'niit technologies', 'mastech', 'zensar'
}

# What the JD explicitly calls "things you absolutely need"
CORE_RETRIEVAL_SKILLS = {
    'sentence transformers', 'sentence-transformers', 'embeddings', 'text embeddings',
    'openai embeddings', 'semantic search', 'dense retrieval', 'bi-encoder',
    'cross-encoder', 'information retrieval', 'bge', 'e5 embeddings',
    'vector search', 'hybrid search'
}

VECTOR_DB_SKILLS = {
    'pinecone', 'weaviate', 'qdrant', 'milvus', 'faiss', 'opensearch',
    'elasticsearch', 'pgvector', 'chroma', 'chromadb', 'vespa', 'typesense',
    'redis vector', 'annoy', 'scann'
}

RANKING_EVAL_SKILLS = {
    'learning to rank', 'ltr', 'ranknet', 'lambdamart', 'lambdarank',
    'ndcg', 'mrr', 'map', 'information retrieval', 'recommendation systems',
    'search ranking', 'relevance ranking', 'reranking', 're-ranking',
    'xgboost', 'lightgbm', 'catboost', 'rag', 'retrieval augmented'
}

LLM_SKILLS = {
    'fine-tuning llms', 'fine-tuning', 'lora', 'qlora', 'peft', 'rlhf',
    'hugging face', 'hugging face transformers', 'transformers', 'bert',
    'gpt', 'llm', 'large language model', 'instruction tuning'
}

# Titles that indicate ML/AI trajectory 
STRONG_FIT_TITLES = {
    'ml engineer', 'machine learning engineer', 'senior machine learning engineer',
    'staff machine learning engineer', 'nlp engineer', 'senior nlp engineer',
    'search engineer', 'applied ml engineer', 'ai engineer', 'senior ai engineer',
    'lead ai engineer', 'recommendation systems engineer', 'ai research engineer',
    'data scientist', 'senior data scientist', 'applied scientist', 'senior applied scientist',
    'research engineer', 'senior software engineer (ml)'
}

ADJACENT_FIT_TITLES = {
    'data engineer', 'senior data engineer', 'analytics engineer',
    'backend engineer', 'software engineer', 'senior software engineer',
    'full stack developer', 'cloud engineer'
}

# Disqualifying title patterns (JD: CV, speech, robotics without NLP)
WEAK_FIT_TITLES = {
    'computer vision engineer', 'junior ml engineer', 'ai specialist'
}

# India locations the JD explicitly mentions
PREFERRED_INDIA_LOCATIONS = {
    'pune', 'noida', 'hyderabad', 'mumbai', 'delhi', 'bangalore', 'bengaluru',
    'gurgaon', 'gurugram', 'chennai', 'new delhi', 'greater noida',
    'navi mumbai', 'thane', 'secunderabad'
}

# Career description evidence terms — presence in job descriptions means real work
DESCRIPTION_EVIDENCE = {
    # High value — very specific, hard to fake
    'high': [
        'embedding drift', 'index refresh', 'retrieval quality', 'recall@', 'precision@',
        'ndcg', 'mrr', 'mean reciprocal', 'a/b test', 'online evaluation', 'offline eval',
        'learning to rank', 'rerank', 're-rank', 'hybrid retrieval', 'dense retrieval',
        'sparse retrieval', 'bm25', 'ann index', 'approximate nearest neighbor',
        'embedding model', 'bi-encoder', 'cross-encoder', 'sentence-transformer',
        'fine-tun', 'lora', 'qlora', 'peft', 'vector index', 'semantic similarity',
        'shipped', 'deployed to production', 'production traffic', 'real users',
        'search latency', 'p99', 'query latency', 'throughput', 'qps',
        'recommendation engine', 'ranking model', 'candidate generation',
    ],
    # Medium value — meaningful but broader
    'medium': [
        'vector', 'embedding', 'retrieval', 'ranking', 'faiss', 'pinecone', 'qdrant',
        'milvus', 'weaviate', 'elasticsearch', 'opensearch', 'semantic search',
        'transformer', 'bert', 'rag', 'retrieval augmented', 'feature engineering',
        'pipeline', 'production', 'inference', 'mlops', 'model serving', 'model deployment',
        'recommendation', 'search', 'relevance', 'similarity', 'natural language',
        'text classification', 'named entity', 'information extraction',
        'xgboost', 'lightgbm', 'gradient boost', 'ensemble',
    ]
}


# ─── Honeypot Detection ────────────────────────────────────────────────────────

def detect_honeypot(candidate: dict) -> tuple[bool, list[str]]:
    """
    Returns (is_honeypot, reasons).
    The spec says ~80 honeypots with 'subtly impossible profiles'.
    We check for internal contradictions, not just suspicious values.
    """
    flags = []
    profile = candidate['profile']
    career = candidate['career_history']
    skills = candidate['skills']

    # Check 1: claimed YoE exceeds possible career span
    if career:
        earliest_start_year = min(int(j['start_date'][:4]) for j in career)
        max_possible_yoe = TODAY.year - earliest_start_year + 1
        claimed_yoe = profile['years_of_experience']
        if claimed_yoe > max_possible_yoe + 2:
            flags.append(
                f"Claimed {claimed_yoe}yrs experience but career history only spans "
                f"from {earliest_start_year} ({max_possible_yoe}yrs max possible)"
            )

    # Check 2: assessment scores wildly contradict claimed proficiency
    assessments = candidate['redrob_signals']['skill_assessment_scores']
    contradictions = 0
    for skill_name, score in assessments.items():
        matching = [s for s in skills if s['name'].lower() == skill_name.lower()]
        if matching:
            claimed = matching[0]['proficiency']
            # Expert claiming <30 on assessment, or advanced claiming <20
            if claimed == 'expert' and score < 30:
                contradictions += 1
            elif claimed == 'advanced' and score < 20:
                contradictions += 1
    if contradictions >= 3:
        flags.append(f"{contradictions} skills with expert/advanced claim but assessment score <30")

    # Check 3: Many expert skills with 0 months duration (padding)
    expert_zero_duration = [
        s for s in skills
        if s['proficiency'] == 'expert' and s.get('duration_months', 0) == 0
    ]
    if len(expert_zero_duration) >= 4:
        flags.append(
            f"{len(expert_zero_duration)} skills claimed as expert with 0 months of use"
        )

    # Check 4: Current role duration impossible given start date
    for job in career:
        if job['is_current'] and job['start_date']:
            start = date.fromisoformat(job['start_date'])
            actual_months = (TODAY.year - start.year) * 12 + (TODAY.month - start.month)
            stated_months = job['duration_months']
            if stated_months > actual_months + 6:
                flags.append(
                    f"Current job states {stated_months} months but start date only allows {actual_months}"
                )

    return len(flags) > 0, flags


# ─── Layer 1: Role Fit Score ───────────────────────────────────────────────────

def score_title_trajectory(candidate: dict) -> tuple[float, str]:
    """
    Score based on career title progression toward ML/AI.
    Current title matters, but trajectory matters more — someone who has been
    NLP Engineer → Search Engineer → Applied ML is more credible than someone
    who became 'AI Engineer' last month.
    """
    current_title = candidate['profile']['current_title'].lower()
    career = candidate['career_history']

    # Current title score
    if current_title in STRONG_FIT_TITLES:
        base = 1.0
        label = f"Strong fit title: {candidate['profile']['current_title']}"
    elif current_title in ADJACENT_FIT_TITLES:
        base = 0.55
        label = f"Adjacent title: {candidate['profile']['current_title']}"
    elif current_title in WEAK_FIT_TITLES:
        base = 0.35
        label = f"Weak fit title: {candidate['profile']['current_title']}"
    else:
        base = 0.0
        label = f"Off-domain title: {candidate['profile']['current_title']}"

    # Trajectory bonus: how many past roles were in ML/AI?
    ml_role_count = sum(
        1 for job in career
        if job['title'].lower() in STRONG_FIT_TITLES
        or any(kw in job['title'].lower() for kw in ['ml', 'nlp', 'ai ', 'search', 'recommend', 'data scien'])
    )
    trajectory_bonus = min(0.15, ml_role_count * 0.05)

    # Trajectory penalty: if current is strong but entire past was consulting/non-technical
    if base > 0.5 and len(career) > 1:
        past_roles = career[1:]  # exclude current
        consulting_past = sum(
            1 for job in past_roles
            if any(f in job['company'].lower() for f in CONSULTING_FIRMS)
        )
        if consulting_past == len(past_roles):
            trajectory_bonus -= 0.1
            label += " (consulting background)"

    score = min(1.0, base + trajectory_bonus)
    return score, label


def score_career_description_evidence(candidate: dict) -> tuple[float, list[str]]:
    """
    This is the anti-gaming layer.
    We read what they actually did in each job, not what they listed as skills.
    High-value technical terms in descriptions = real work evidence.
    Generic buzzwords with no specifics = low signal.
    """
    all_descriptions = " ".join(
        job['description'].lower() for job in candidate['career_history']
    )

    high_hits = []
    medium_hits = []

    for term in DESCRIPTION_EVIDENCE['high']:
        if term in all_descriptions:
            high_hits.append(term)

    for term in DESCRIPTION_EVIDENCE['medium']:
        if term in all_descriptions:
            medium_hits.append(term)

    # Score: high-value terms worth more
    high_score = min(1.0, len(high_hits) * 0.12)
    medium_score = min(0.5, len(medium_hits) * 0.04)
    raw_score = min(1.0, high_score + medium_score)

    # Build evidence list for reasoning
    evidence = []
    if high_hits:
        evidence.append(f"Career descriptions mention: {', '.join(high_hits[:5])}")
    if medium_hits[:3]:
        evidence.append(f"Also evidenced: {', '.join(medium_hits[:3])}")

    # Bonus: if they shipped to production with real users
    production_signals = ['production', 'real users', 'deployed', 'shipped', 'live traffic']
    prod_count = sum(1 for s in production_signals if s in all_descriptions)
    if prod_count >= 2:
        raw_score = min(1.0, raw_score + 0.1)
        evidence.append("Production deployment evidence in career history")

    return raw_score, evidence


def score_experience_fit(candidate: dict) -> tuple[float, str]:
    """
    JD wants 5-9 years. But explicitly says this is a range, not a hard cutoff.
    Under-experience is worse than over-experience for this role.
    """
    yoe = candidate['profile']['years_of_experience']

    if 5 <= yoe <= 9:
        score = 1.0
        label = f"{yoe}yrs (ideal range 5-9)"
    elif 4 <= yoe < 5:
        score = 0.8
        label = f"{yoe}yrs (slightly under, acceptable)"
    elif 9 < yoe <= 12:
        score = 0.85
        label = f"{yoe}yrs (over range, still viable)"
    elif 3 <= yoe < 4:
        score = 0.55
        label = f"{yoe}yrs (under-experienced)"
    elif yoe > 12:
        score = 0.7
        label = f"{yoe}yrs (senior — over-qualified risk)"
    else:
        score = 0.2
        label = f"{yoe}yrs (too junior)"

    return score, label


def score_location_fit(candidate: dict) -> tuple[float, str]:
    """
    JD prefers Pune/Noida but accepts Hyderabad/Mumbai/Delhi NCR/Bangalore.
    India-based is strongly preferred. Outside India = case-by-case.
    willing_to_relocate matters.
    """
    location = candidate['profile']['location'].lower()
    country = candidate['profile']['country']
    relocate = candidate['redrob_signals']['willing_to_relocate']

    # Check preferred India locations
    location_match = any(city in location for city in PREFERRED_INDIA_LOCATIONS)

    if country == 'India':
        if location_match:
            return 1.0, f"India, {candidate['profile']['location']} (preferred location)"
        elif relocate:
            return 0.75, f"India, {candidate['profile']['location']} (willing to relocate)"
        else:
            return 0.55, f"India, {candidate['profile']['location']} (not preferred city, not relocating)"
    else:
        if relocate:
            return 0.4, f"{country} (international, willing to relocate)"
        else:
            return 0.15, f"{country} (international, not relocating)"


def score_company_background(candidate: dict) -> tuple[float, str]:
    """
    JD explicitly disqualifies consulting-only backgrounds (TCS, Infosys etc).
    Product company experience is a strong positive signal.
    """
    career = candidate['career_history']
    if not career:
        return 0.5, "No career history"

    PRODUCT_INDUSTRIES = {
        'fintech', 'food delivery', 'e-commerce', 'edtech', 'saas', 'ai/ml',
        'gaming', 'healthtech', 'adtech', 'transportation', 'conversational ai',
        'ai services', 'software', 'healthtech ai', 'insurance tech'
    }

    consulting_jobs = 0
    product_jobs = 0
    total_months = sum(j['duration_months'] for j in career)
    consulting_months = 0
    product_months = 0

    for job in career:
        is_consulting = any(f in job['company'].lower() for f in CONSULTING_FIRMS)
        is_product = job['industry'].lower() in PRODUCT_INDUSTRIES

        if is_consulting:
            consulting_jobs += 1
            consulting_months += job['duration_months']
        if is_product:
            product_jobs += 1
            product_months += job['duration_months']

    # Pure consulting: all jobs at consulting firms
    if consulting_jobs == len(career):
        return 0.1, f"Consulting-only background ({', '.join(set(j['company'] for j in career))})"

    # Majority consulting
    if total_months > 0 and consulting_months / total_months > 0.6:
        return 0.35, f"Predominantly consulting background ({consulting_months}mo consulting)"

    # Good product company experience
    if product_months > 24:
        return 1.0, f"Strong product company background ({product_months}mo at product companies)"
    elif product_jobs > 0:
        return 0.75, f"Some product company experience ({product_jobs} product roles)"

    return 0.55, "Mixed background (not consulting-dominated, not clearly product-focused)"


# ─── Layer 2: Evidence Quality Multiplier ─────────────────────────────────────

def compute_evidence_quality(candidate: dict) -> tuple[float, list[str]]:
    """
    Cross-reference skill claims against evidence.
    A skill claimed as 'expert' should have: high duration, endorsements, and 
    assessment score that backs it up.
    This catches keyword stuffers who list skills they don't actually have.
    """
    skills = candidate['skills']
    assessments = candidate['redrob_signals']['skill_assessment_scores']
    evidence_notes = []

    if not skills:
        return 0.7, ["No skills listed"]

    # Check proficiency vs duration consistency
    inconsistencies = 0
    total_checked = 0

    for skill in skills:
        prof = skill['proficiency']
        duration = skill.get('duration_months', 0)
        endorsements = skill['endorsements']

        # Expected minimum duration for each proficiency level
        expected_min = {'beginner': 1, 'intermediate': 6, 'advanced': 18, 'expert': 36}
        min_dur = expected_min.get(prof, 0)

        if duration < min_dur and prof in ('expert', 'advanced'):
            inconsistencies += 1
        total_checked += 1

    # Check assessment scores vs claimed proficiency
    assessment_penalties = 0
    assessment_bonuses = 0
    for skill_name, score in assessments.items():
        matching = [s for s in skills if s['name'].lower() == skill_name.lower()]
        if matching:
            claimed_prof = matching[0]['proficiency']
            if claimed_prof == 'expert' and score >= 70:
                assessment_bonuses += 1
            elif claimed_prof in ('expert', 'advanced') and score < 40:
                assessment_penalties += 1

    # Core skill depth: do they have the JD's core skills with real depth?
    core_skills_with_depth = 0
    all_skill_names = {s['name'].lower() for s in skills}
    for skill in skills:
        skill_lower = skill['name'].lower()
        if (skill_lower in CORE_RETRIEVAL_SKILLS or skill_lower in VECTOR_DB_SKILLS):
            if skill.get('duration_months', 0) >= 12 and skill['proficiency'] in ('advanced', 'expert'):
                core_skills_with_depth += 1

    # Build multiplier
    base = 1.0

    if inconsistencies > 0 and total_checked > 0:
        inconsistency_rate = inconsistencies / total_checked
        penalty = inconsistency_rate * 0.3
        base -= penalty
        if inconsistency_rate > 0.3:
            evidence_notes.append(
                f"{inconsistencies} skill claims have proficiency inconsistent with duration"
            )

    if assessment_penalties > 0:
        base -= assessment_penalties * 0.08
        evidence_notes.append(
            f"{assessment_penalties} skills with expert/advanced claim but low assessment score"
        )

    if assessment_bonuses > 0:
        base += assessment_bonuses * 0.05
        evidence_notes.append(
            f"{assessment_bonuses} core skill claims backed by strong assessment scores"
        )

    if core_skills_with_depth > 0:
        base += min(0.15, core_skills_with_depth * 0.05)
        evidence_notes.append(
            f"{core_skills_with_depth} core JD skills with 12+ months depth"
        )

    multiplier = max(0.6, min(1.25, base))
    return multiplier, evidence_notes


# ─── Layer 3: Availability Multiplier ─────────────────────────────────────────

def compute_availability(candidate: dict) -> tuple[float, list[str]]:
    """
    A perfect-on-paper candidate who is behaviorally unavailable is not a hire.
    This is a hard gate: dead accounts get a low ceiling regardless of skill score.
    """
    sig = candidate['redrob_signals']
    notes = []

    last_active = date.fromisoformat(sig['last_active_date'])
    days_inactive = (TODAY - last_active).days
    response_rate = sig['recruiter_response_rate']
    notice_days = sig['notice_period_days']
    open_to_work = sig['open_to_work_flag']
    interview_completion = sig['interview_completion_rate']

    # Activity recency score
    if days_inactive <= 30:
        activity_score = 1.0
        notes.append(f"Active {days_inactive} days ago")
    elif days_inactive <= 60:
        activity_score = 0.9
        notes.append(f"Active {days_inactive} days ago")
    elif days_inactive <= 120:
        activity_score = 0.75
        notes.append(f"Last active {days_inactive} days ago (moderate staleness)")
    elif days_inactive <= 180:
        activity_score = 0.55
        notes.append(f"Last active {days_inactive} days ago (stale)")
    else:
        activity_score = 0.3
        notes.append(f"Inactive for {days_inactive} days — likely not actually looking")

    # Response rate score
    if response_rate >= 0.7:
        response_score = 1.0
        notes.append(f"High recruiter response rate ({response_rate:.0%})")
    elif response_rate >= 0.4:
        response_score = 0.8
    elif response_rate >= 0.2:
        response_score = 0.6
        notes.append(f"Low response rate ({response_rate:.0%})")
    else:
        response_score = 0.3
        notes.append(f"Very low response rate ({response_rate:.0%}) — unlikely to engage")

    # Notice period (JD prefers sub-30 days, can buy out 30 days)
    if notice_days <= 15:
        notice_score = 1.0
        notes.append(f"Immediate / near-immediate availability ({notice_days}d notice)")
    elif notice_days <= 30:
        notice_score = 0.95
        notes.append(f"{notice_days}d notice (within buyout range)")
    elif notice_days <= 60:
        notice_score = 0.8
    elif notice_days <= 90:
        notice_score = 0.65
        notes.append(f"{notice_days}d notice (long — adds friction)")
    else:
        notice_score = 0.45
        notes.append(f"{notice_days}d notice (very long — significant hiring risk)")

    # Open to work flag
    if not open_to_work:
        notes.append("Not flagged as open to work")
        open_score = 0.7
    else:
        open_score = 1.0

    # Reliability signals
    reliability = (interview_completion + sig['offer_acceptance_rate'] + 1) / 3 if sig['offer_acceptance_rate'] >= 0 else interview_completion
    reliability = max(0.5, min(1.0, reliability))

    # Combine: activity and response rate are the most critical
    raw = (
        activity_score * 0.35 +
        response_score * 0.30 +
        notice_score * 0.20 +
        open_score * 0.10 +
        reliability * 0.05
    )

    # Hard ceiling: if truly dead (inactive 6mo AND response rate <15%) cap at 0.45
    if days_inactive > 180 and response_rate < 0.15:
        raw = min(0.45, raw)
        notes.append("⚠ Behaviorally unavailable: inactive + unresponsive")

    return raw, notes


# ─── Final Score Assembly ─────────────────────────────────────────────────────

# JD section weights
ROLE_FIT_WEIGHTS = {
    'title_trajectory': 0.25,
    'description_evidence': 0.35,
    'experience': 0.15,
    'location': 0.10,
    'company_background': 0.15,
}


def score_tiebreaker(candidate: dict) -> float:
    """
    Fine-grained signal used to break ties among similarly-scored candidates.
    This is what separates rank 1 from rank 13 when core scores are equal.
    Combines: location precision, notice period, assessment score quality,
    github activity, core skill depth, and response reliability.
    Returns a value in [0, 1] added at small weight to final score.
    """
    sig = candidate['redrob_signals']
    skills = candidate['skills']
    profile = candidate['profile']
    score = 0.0

    # Preferred city precision (Pune/Noida > NCR > other preferred)
    location_lower = profile['location'].lower()
    if 'pune' in location_lower or 'noida' in location_lower:
        score += 0.25
    elif any(c in location_lower for c in ['gurgaon', 'gurugram', 'delhi', 'hyderabad', 'bangalore', 'bengaluru', 'mumbai']):
        score += 0.15

    # Notice period precision (sub-30 is JD's ideal)
    notice = sig['notice_period_days']
    if notice <= 15:
        score += 0.20
    elif notice <= 30:
        score += 0.15
    elif notice <= 60:
        score += 0.08

    # Assessment quality on JD-relevant skills
    assessments = sig['skill_assessment_scores']
    jd_relevant_assessments = []
    for skill_name, asmt_score in assessments.items():
        skill_lower = skill_name.lower()
        if (skill_lower in CORE_RETRIEVAL_SKILLS or
                skill_lower in VECTOR_DB_SKILLS or
                skill_lower in RANKING_EVAL_SKILLS or
                'machine learning' in skill_lower or
                'deep learning' in skill_lower or
                'nlp' in skill_lower):
            jd_relevant_assessments.append(asmt_score)
    if jd_relevant_assessments:
        avg_relevant = sum(jd_relevant_assessments) / len(jd_relevant_assessments)
        score += min(0.20, avg_relevant / 500)  # max 0.20 at score=100

    # GitHub activity (JD mentions open-source contributions as a positive)
    github = sig['github_activity_score']
    if github >= 70:
        score += 0.15
    elif github >= 40:
        score += 0.08
    elif github >= 10:
        score += 0.03

    # Core skill depth: expert/advanced skills in exact JD-required areas
    core_depth_count = 0
    for s in skills:
        skill_lower = s['name'].lower()
        if (skill_lower in CORE_RETRIEVAL_SKILLS or skill_lower in VECTOR_DB_SKILLS):
            if s['proficiency'] in ('expert', 'advanced') and s.get('duration_months', 0) >= 24:
                core_depth_count += 1
    score += min(0.15, core_depth_count * 0.05)

    # Response reliability
    if sig['recruiter_response_rate'] >= 0.75:
        score += 0.05

    return min(1.0, score)


def build_rich_reasoning(candidate: dict, components: dict) -> str:
    """
    Build a reasoning string that a recruiter can actually verify.
    Pulls specific facts from the candidate's profile rather than templates.
    """
    profile = candidate['profile']
    career = candidate['career_history']
    sig = candidate['redrob_signals']
    skills = candidate['skills']

    parts = []

    # 1. Core identity: title, YoE, company trajectory
    current_job = career[0] if career else None
    if current_job:
        parts.append(
            f"{profile['current_title']} ({profile['years_of_experience']}yrs) currently at "
            f"{current_job['company']} ({current_job['industry']})"
        )
    else:
        parts.append(f"{profile['current_title']}, {profile['years_of_experience']}yrs exp")

    # 2. Career trajectory highlight (most relevant past role)
    past_relevant = [
        j for j in career[1:]
        if any(kw in j['title'].lower() for kw in ['ml', 'nlp', 'ai', 'search', 'data scien', 'recommend'])
        or any(kw in j['industry'].lower() for kw in ['ai', 'fintech', 'food', 'e-commerce', 'saas', 'tech'])
    ]
    if past_relevant:
        prev = past_relevant[0]
        parts.append(f"prev: {prev['title']} @ {prev['company']}")

    # 3. Strongest skill evidence (highest duration core skills)
    core_skill_names = CORE_RETRIEVAL_SKILLS | VECTOR_DB_SKILLS | RANKING_EVAL_SKILLS
    strong_skills = [
        s for s in skills
        if s['name'].lower() in core_skill_names
        and s.get('duration_months', 0) >= 12
        and s['proficiency'] in ('expert', 'advanced')
    ]
    strong_skills.sort(key=lambda s: s.get('duration_months', 0), reverse=True)
    if strong_skills:
        skill_strs = [f"{s['name']} ({s.get('duration_months',0)}mo, {s['proficiency']})"
                      for s in strong_skills[:3]]
        parts.append(f"core skills: {', '.join(skill_strs)}")

    # 4. Career description evidence (specific technical terms found)
    all_descs = " ".join(j['description'].lower() for j in career)
    high_evidence = [t for t in DESCRIPTION_EVIDENCE['high'] if t in all_descs]
    if high_evidence:
        parts.append(f"career evidence: {', '.join(high_evidence[:4])}")

    # 5. Assessment backing (if relevant scores exist)
    relevant_assessments = {
        k: v for k, v in sig['skill_assessment_scores'].items()
        if k.lower() in core_skill_names or 'machine learning' in k.lower() or 'nlp' in k.lower()
    }
    if relevant_assessments:
        best = max(relevant_assessments.items(), key=lambda x: x[1])
        parts.append(f"assessed: {best[0]} {best[1]:.0f}/100")

    # 6. Availability summary
    last_active = date.fromisoformat(sig['last_active_date'])
    days_ago = (TODAY - last_active).days
    avail_str = f"active {days_ago}d ago, {sig['recruiter_response_rate']:.0%} response rate, {sig['notice_period_days']}d notice"
    parts.append(avail_str)

    # 7. Location
    parts.append(f"{profile['location']}, {profile['country']}")

    return " | ".join(parts)[:500]


def score_candidate(candidate: dict) -> dict:
    """
    Full scoring pipeline for one candidate.
    Returns score components + reasoning for the recruiter.
    """

    # Honeypot check first
    is_honeypot, honeypot_reasons = detect_honeypot(candidate)
    if is_honeypot:
        return {
            'candidate_id': candidate['candidate_id'],
            'final_score': 0.05,
            'is_honeypot': True,
            'reasoning': f"Profile integrity issue: {'; '.join(honeypot_reasons[:2])}",
            'components': {}
        }

    # Layer 1: Role Fit
    title_score, title_label = score_title_trajectory(candidate)
    desc_score, desc_evidence = score_career_description_evidence(candidate)
    exp_score, exp_label = score_experience_fit(candidate)
    loc_score, loc_label = score_location_fit(candidate)
    company_score, company_label = score_company_background(candidate)

    role_fit = (
        title_score * ROLE_FIT_WEIGHTS['title_trajectory'] +
        desc_score * ROLE_FIT_WEIGHTS['description_evidence'] +
        exp_score * ROLE_FIT_WEIGHTS['experience'] +
        loc_score * ROLE_FIT_WEIGHTS['location'] +
        company_score * ROLE_FIT_WEIGHTS['company_background']
    )

    # Layer 2: Evidence Quality
    evidence_multiplier, evidence_notes = compute_evidence_quality(candidate)

    # Layer 3: Availability
    availability_multiplier, availability_notes = compute_availability(candidate)

    # Tiebreaker (small weight — only matters when main scores are close)
    tiebreaker = score_tiebreaker(candidate)

    # Final score: main score + small tiebreaker contribution
    raw_score = role_fit * evidence_multiplier * availability_multiplier
    final_score = raw_score * 0.92 + tiebreaker * 0.08
    final_score = max(0.0, min(1.0, final_score))

    # Build components for UI + CSV
    components = {
        'role_fit': round(role_fit, 4),
        'title_score': round(title_score, 4),
        'title_label': title_label,
        'desc_score': round(desc_score, 4),
        'desc_evidence': desc_evidence,
        'exp_score': round(exp_score, 4),
        'exp_label': exp_label,
        'loc_score': round(loc_score, 4),
        'loc_label': loc_label,
        'company_score': round(company_score, 4),
        'company_label': company_label,
        'evidence_multiplier': round(evidence_multiplier, 4),
        'evidence_notes': evidence_notes,
        'availability_multiplier': round(availability_multiplier, 4),
        'availability_notes': availability_notes,
        'tiebreaker': round(tiebreaker, 4),
    }

    reasoning = build_rich_reasoning(candidate, components)

    return {
        'candidate_id': candidate['candidate_id'],
        'final_score': round(final_score, 4),
        'is_honeypot': False,
        'reasoning': reasoning,
        'components': components
    }


# ─── Main Ranking Pipeline ────────────────────────────────────────────────────

def rank_candidates(candidates_path: str, output_path: str, verbose: bool = False):
    print(f"Loading candidates from {candidates_path}...")
    candidates = []
    with open(candidates_path) as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))

    print(f"Loaded {len(candidates)} candidates. Scoring...")

    results = []
    honeypot_count = 0

    for i, candidate in enumerate(candidates):
        if verbose and i % 10000 == 0:
            print(f"  Scored {i}/{len(candidates)}...")

        result = score_candidate(candidate)
        results.append(result)
        if result['is_honeypot']:
            honeypot_count += 1

    print(f"Scoring complete. Detected {honeypot_count} honeypots.")

    # Sort by final score descending, tie-break by candidate_id ascending
    results.sort(key=lambda r: (-r['final_score'], r['candidate_id']))

    # Take top 100
    top_100 = results[:100]

    # Assign ranks and ensure non-increasing scores
    # (scores are already sorted, just need to handle exact ties)
    output_rows = []
    for rank, result in enumerate(top_100, start=1):
        output_rows.append({
            'candidate_id': result['candidate_id'],
            'rank': rank,
            'score': result['final_score'],
            'reasoning': result['reasoning']
        })

    # Write CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['candidate_id', 'rank', 'score', 'reasoning'])
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Submission written to {output_path}")
    print(f"\nTop 10 candidates:")
    for row in output_rows[:10]:
        print(f"  #{row['rank']} {row['candidate_id']} ({row['score']:.4f}): {row['reasoning'][:100]}...")

    return output_rows, results


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Redrob Candidate Ranker')
    parser.add_argument('--candidates', default='candidates.jsonl')
    parser.add_argument('--out', default='submission.csv')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    rank_candidates(args.candidates, args.out, verbose=args.verbose)
