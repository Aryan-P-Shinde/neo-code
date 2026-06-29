"""
Redrob Intelligent Candidate Ranker — Recruiter Demo
Run: streamlit run app.py
"""

import streamlit as st
import json
import csv
import io
import sys
from pathlib import Path
from datetime import date

TODAY = date(2026, 6, 28)

# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Redrob Candidate Ranker",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Styling ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .stApp { background-color: #0f1117; }

    .rank-badge {
        display: inline-block;
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 13px;
        font-weight: 700;
        color: #a0aec0;
        margin-right: 8px;
    }
    .rank-badge.top3 { border-color: #f6ad55; color: #f6ad55; }
    .rank-badge.top10 { border-color: #68d391; color: #68d391; }
    .rank-badge.top50 { border-color: #63b3ed; color: #63b3ed; }

    .score-bar-container {
        background: #1a1f2e;
        border-radius: 4px;
        height: 6px;
        margin-top: 4px;
    }
    .score-bar {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        border-radius: 4px;
        height: 6px;
    }

    .candidate-card {
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
        cursor: pointer;
    }
    .candidate-card:hover {
        border-color: #4a5568;
    }
    .candidate-card.selected {
        border-color: #667eea;
        background: #1e2235;
    }

    .tag {
        display: inline-block;
        background: #2d3748;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
        color: #a0aec0;
        margin: 2px;
    }
    .tag.green { background: #1a3a2a; color: #68d391; }
    .tag.yellow { background: #3a3320; color: #f6ad55; }
    .tag.red { background: #3a1a1a; color: #fc8181; }
    .tag.blue { background: #1a2a3a; color: #63b3ed; }

    .evidence-block {
        background: #0d1117;
        border-left: 3px solid #667eea;
        border-radius: 0 6px 6px 0;
        padding: 10px 14px;
        margin: 8px 0;
        font-size: 13px;
        color: #a0aec0;
    }

    .signal-row {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin: 8px 0;
    }

    .metric-pill {
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 12px;
        color: #a0aec0;
    }

    .section-header {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: #4a5568;
        text-transform: uppercase;
        margin: 16px 0 8px 0;
    }

    .honeypot-warning {
        background: #3a1a1a;
        border: 1px solid #fc8181;
        border-radius: 6px;
        padding: 8px 12px;
        color: #fc8181;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Data Loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_precomputed():
    """Load pre-computed results if available."""
    p = Path(__file__).parent / "top200_results.json"
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


@st.cache_data
def run_ranker_on_sample(jsonl_content: str):
    """Run the ranker on uploaded JSONL content."""
    sys.path.insert(0, str(Path(__file__).parent))
    from ranker import score_candidate

    candidates = []
    for line in jsonl_content.strip().split('\n'):
        line = line.strip()
        if line:
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    results = []
    for c in candidates:
        r = score_candidate(c)
        r['profile'] = c['profile']
        r['career_history'] = c['career_history']
        r['skills'] = c['skills']
        r['redrob_signals'] = c['redrob_signals']
        r['education'] = c.get('education', [])
        results.append(r)

    results.sort(key=lambda r: (-r['final_score'], r['candidate_id']))
    return results


def days_ago_label(date_str: str) -> str:
    d = date.fromisoformat(date_str)
    days = (TODAY - d).days
    if days <= 7:
        return f"{days}d ago 🟢"
    elif days <= 30:
        return f"{days}d ago 🟡"
    elif days <= 90:
        return f"{days}d ago 🟠"
    else:
        return f"{days}d ago 🔴"


def notice_label(days: int) -> str:
    if days <= 15:
        return f"{days}d ✅"
    elif days <= 30:
        return f"{days}d 🟢"
    elif days <= 60:
        return f"{days}d 🟡"
    else:
        return f"{days}d 🔴"


def response_label(rate: float) -> str:
    if rate >= 0.7:
        return f"{rate:.0%} ✅"
    elif rate >= 0.4:
        return f"{rate:.0%} 🟡"
    else:
        return f"{rate:.0%} 🔴"


def score_color(score: float) -> str:
    if score >= 0.9:
        return "#68d391"
    elif score >= 0.75:
        return "#f6ad55"
    else:
        return "#fc8181"


# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🎯 Redrob Ranker")
    st.markdown("*Intelligent candidate discovery — scores evidence, not keywords*")
    st.divider()

    mode = st.radio(
        "Data source",
        ["Use pre-ranked shortlist (100K pool)", "Upload candidate sample (JSONL)"],
        index=0
    )

    st.divider()

    if mode == "Use pre-ranked shortlist (100K pool)":
        n_show = st.slider("Candidates to show", 10, 100, 25)
        min_score = st.slider("Min score filter", 0.0, 1.0, 0.75, 0.05)
        st.divider()
        st.markdown("**Score components**")
        st.markdown("""
        <small>
        🔵 <b>Role Fit</b> — title trajectory, career evidence, experience, location, company type<br>
        🟡 <b>Evidence Quality</b> — skill claims vs duration, assessments, endorsements<br>
        🟢 <b>Availability</b> — activity recency, response rate, notice period
        </small>
        """, unsafe_allow_html=True)

    st.divider()
    st.caption("Built for Redrob Hackathon — Intelligent Candidate Discovery & Ranking Challenge")


# ─── Main Content ─────────────────────────────────────────────────────────────

st.title("Candidate Shortlist")
st.caption("Ranked by genuine fit — scored on career evidence, not keyword matching")

# Load data
results = None

if mode == "Use pre-ranked shortlist (100K pool)":
    results = load_precomputed()
    if results is None:
        st.error("Pre-computed results not found. Run the ranker first: `python ranker.py --candidates candidates.jsonl --out submission.csv`")
        st.stop()

    # Filter
    filtered = [r for r in results if r['final_score'] >= min_score][:n_show]

    if not filtered:
        st.warning("No candidates match the current filters.")
        st.stop()

    st.markdown(f"Showing **{len(filtered)}** candidates (from {len(results)} pre-ranked) with score ≥ {min_score:.2f}")

else:
    uploaded = st.file_uploader(
        "Upload candidates.jsonl or a sample",
        type=['jsonl', 'json', 'txt'],
        help="Upload a JSONL file with candidate profiles matching the Redrob schema"
    )

    if uploaded is None:
        st.info("Upload a JSONL file to rank candidates. Use `sample_candidates.json` for a quick demo.")
        st.stop()

    content = uploaded.read().decode('utf-8')
    # Handle JSON array or JSONL
    if content.strip().startswith('['):
        data = json.loads(content)
        content = '\n'.join(json.dumps(c) for c in data)

    with st.spinner(f"Scoring candidates..."):
        results = run_ranker_on_sample(content)

    filtered = results
    n_show = len(results)
    st.success(f"Ranked {len(results)} candidates")


# ─── Layout: List + Detail Panel ───────────────────────────────────────────────

list_col, detail_col = st.columns([2, 3], gap="large")

with list_col:
    st.markdown(f"#### Shortlist")

    if 'selected_idx' not in st.session_state:
        st.session_state.selected_idx = 0

    for i, result in enumerate(filtered):
        cid = result['candidate_id']
        score = result['final_score']
        profile = result['profile']
        components = result.get('components', {})

        # Rank badge class
        rank = i + 1
        if rank <= 3:
            badge_class = "top3"
        elif rank <= 10:
            badge_class = "top10"
        else:
            badge_class = "top50"

        is_selected = (i == st.session_state.selected_idx)
        card_class = "candidate-card selected" if is_selected else "candidate-card"

        # Score bar width
        bar_width = int(score * 100)

        # Quick availability signal
        sig = result['redrob_signals']
        active_days = (TODAY - date.fromisoformat(sig['last_active_date'])).days
        if active_days <= 30 and sig['recruiter_response_rate'] >= 0.5:
            avail_indicator = "🟢"
        elif active_days <= 90:
            avail_indicator = "🟡"
        else:
            avail_indicator = "🔴"

        # Render card
        btn_label = f"#{rank}  {profile['current_title']}  •  {profile['years_of_experience']}yrs  {avail_indicator}  {score:.3f}"
        if st.button(btn_label, key=f"card_{i}", use_container_width=True):
            st.session_state.selected_idx = i

        # Score bar
        color = score_color(score)
        st.markdown(
            f'<div class="score-bar-container"><div class="score-bar" style="width:{bar_width}%; background: {color};"></div></div>',
            unsafe_allow_html=True
        )


# ─── Detail Panel ──────────────────────────────────────────────────────────────

with detail_col:
    if st.session_state.selected_idx < len(filtered):
        result = filtered[st.session_state.selected_idx]
        profile = result['profile']
        career = result['career_history']
        skills = result['skills']
        sig = result['redrob_signals']
        components = result.get('components', {})
        education = result.get('education', [])

        rank = st.session_state.selected_idx + 1
        score = result['final_score']

        # Header
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(f"#### #{rank} — {profile['current_title']}")
            st.caption(f"{result['candidate_id']} · {profile['location']}, {profile['country']}")
        with col_b:
            color = score_color(score)
            st.markdown(
                f'<div style="text-align:right; font-size:28px; font-weight:700; color:{color};">{score:.3f}</div>'
                f'<div style="text-align:right; font-size:11px; color:#4a5568;">FIT SCORE</div>',
                unsafe_allow_html=True
            )

        st.divider()

        # Score breakdown
        st.markdown('<div class="section-header">Score Breakdown</div>', unsafe_allow_html=True)

        comp_col1, comp_col2, comp_col3 = st.columns(3)
        with comp_col1:
            role_fit = components.get('role_fit', 0)
            st.metric("Role Fit", f"{role_fit:.3f}", help="Title trajectory, career evidence, experience, location, company type")
        with comp_col2:
            ev_mult = components.get('evidence_multiplier', 1.0)
            ev_delta = f"{(ev_mult - 1.0):+.2f}" if ev_mult != 1.0 else "neutral"
            st.metric("Evidence Quality", f"{ev_mult:.2f}×", delta=ev_delta, help="Skill claims vs duration, assessments, endorsements")
        with comp_col3:
            av_mult = components.get('availability_multiplier', 1.0)
            st.metric("Availability", f"{av_mult:.2f}×", help="Activity recency, response rate, notice period")

        # Sub-scores
        sub_cols = st.columns(5)
        labels = ['Title', 'Evidence', 'Experience', 'Location', 'Company']
        keys = ['title_score', 'desc_score', 'exp_score', 'loc_score', 'company_score']
        for col, label, key in zip(sub_cols, labels, keys):
            val = components.get(key, 0)
            col.metric(label, f"{val:.2f}")

        st.divider()

        # Why this candidate — evidence layer
        st.markdown('<div class="section-header">Why This Candidate</div>', unsafe_allow_html=True)

        if result.get('is_honeypot'):
            st.markdown(
                f'<div class="honeypot-warning">⚠️ Profile integrity issue: {result["reasoning"]}</div>',
                unsafe_allow_html=True
            )
        else:
            # Company background
            company_label = components.get('company_label', '')
            if company_label:
                icon = "✅" if "Strong product" in company_label else "⚠️" if "consulting" in company_label.lower() else "🔵"
                st.markdown(
                    f'<div class="evidence-block">{icon} <b>Company background:</b> {company_label}</div>',
                    unsafe_allow_html=True
                )

            # Career description evidence
            desc_evidence = components.get('desc_evidence', [])
            if desc_evidence:
                for ev in desc_evidence[:2]:
                    st.markdown(
                        f'<div class="evidence-block">🔍 {ev}</div>',
                        unsafe_allow_html=True
                    )

            # Evidence quality notes
            ev_notes = components.get('evidence_notes', [])
            for note in ev_notes[:2]:
                icon = "✅" if ("backed" in note or "depth" in note) else "⚠️"
                st.markdown(
                    f'<div class="evidence-block">{icon} {note}</div>',
                    unsafe_allow_html=True
                )

            # Availability notes
            av_notes = components.get('availability_notes', [])
            for note in av_notes[:2]:
                icon = "🔴" if ("Inactive" in note or "unavailable" in note or "unresponsive" in note) else "✅" if "High" in note or "Immediate" in note else "🟡"
                st.markdown(
                    f'<div class="evidence-block">{icon} <b>Availability:</b> {note}</div>',
                    unsafe_allow_html=True
                )

        st.divider()

        # Career History
        st.markdown('<div class="section-header">Career History</div>', unsafe_allow_html=True)
        for job in career:
            dur = job['duration_months']
            yrs = dur / 12
            current_tag = " 🟢 current" if job.get('is_current') else ""
            st.markdown(
                f"**{job['title']}** at {job['company']} "
                f"<span style='color:#4a5568; font-size:12px;'>({job['industry']} · {job['company_size']} · {yrs:.1f}yr{current_tag})</span>",
                unsafe_allow_html=True
            )
            with st.expander("Role description", expanded=False):
                st.markdown(f"<small>{job['description']}</small>", unsafe_allow_html=True)

        st.divider()

        # Skills — core JD-relevant ones highlighted
        st.markdown('<div class="section-header">Skills</div>', unsafe_allow_html=True)

        CORE_SKILLS = {
            'sentence transformers', 'sentence-transformers', 'embeddings', 'text embeddings',
            'semantic search', 'dense retrieval', 'information retrieval', 'vector search',
            'hybrid search', 'pinecone', 'weaviate', 'qdrant', 'milvus', 'faiss', 'opensearch',
            'elasticsearch', 'pgvector', 'chroma', 'rag', 'learning to rank', 'ltr',
            'ndcg', 'recommendation systems', 'search ranking', 'reranking', 'bm25',
            'fine-tuning llms', 'lora', 'qlora', 'peft', 'hugging face transformers',
            'xgboost', 'lightgbm', 'bert', 'transformer', 'nlp'
        }

        skills_sorted = sorted(skills, key=lambda s: (
            1 if s['name'].lower() in CORE_SKILLS else 0,
            s.get('duration_months', 0)
        ), reverse=True)

        assessments = sig.get('skill_assessment_scores', {})

        skill_html = ""
        for s in skills_sorted[:20]:
            is_core = s['name'].lower() in CORE_SKILLS
            duration = s.get('duration_months', 0)
            prof = s['proficiency']
            endorsements = s['endorsements']
            assessed_score = assessments.get(s['name'])

            tag_color = "green" if is_core else "blue" if prof in ('expert', 'advanced') else ""
            duration_str = f"{duration}mo" if duration else "?"
            assessed_str = f" · assessed {assessed_score:.0f}/100" if assessed_score else ""
            endorsement_str = f" · {endorsements}⭐" if endorsements > 5 else ""

            skill_html += (
                f'<span class="tag {tag_color}">'
                f'{"🎯 " if is_core else ""}{s["name"]} · {prof} · {duration_str}{assessed_str}{endorsement_str}'
                f'</span>'
            )

        st.markdown(skill_html, unsafe_allow_html=True)
        st.caption("🎯 = core JD requirement · green = JD-relevant · assessed score verified on platform")

        st.divider()

        # Behavioral Signals
        st.markdown('<div class="section-header">Platform Signals</div>', unsafe_allow_html=True)

        sig_cols = st.columns(4)
        sig_cols[0].metric(
            "Last Active",
            days_ago_label(sig['last_active_date'])
        )
        sig_cols[1].metric(
            "Response Rate",
            response_label(sig['recruiter_response_rate'])
        )
        sig_cols[2].metric(
            "Notice Period",
            notice_label(sig['notice_period_days'])
        )
        sig_cols[3].metric(
            "Open to Work",
            "Yes ✅" if sig['open_to_work_flag'] else "No 🔴"
        )

        sig_cols2 = st.columns(4)
        sig_cols2[0].metric(
            "Interview Completion",
            f"{sig['interview_completion_rate']:.0%}"
        )
        offer_rate = sig['offer_acceptance_rate']
        sig_cols2[1].metric(
            "Offer Accept Rate",
            f"{offer_rate:.0%}" if offer_rate >= 0 else "N/A"
        )
        sig_cols2[2].metric(
            "GitHub Activity",
            f"{sig['github_activity_score']:.0f}/100" if sig['github_activity_score'] >= 0 else "Not linked"
        )
        sig_cols2[3].metric(
            "Profile Complete",
            f"{sig['profile_completeness_score']:.0f}%"
        )

        st.divider()

        # Expected Salary
        sal = sig['expected_salary_range_inr_lpa']
        work_mode = sig['preferred_work_mode']
        relocate = "Yes" if sig['willing_to_relocate'] else "No"

        info_cols = st.columns(3)
        info_cols[0].metric("Expected Salary", f"₹{sal['min']:.0f}–{sal['max']:.0f} LPA")
        info_cols[1].metric("Work Mode Pref", work_mode.title())
        info_cols[2].metric("Willing to Relocate", relocate)

        # Education
        if education:
            st.divider()
            st.markdown('<div class="section-header">Education</div>', unsafe_allow_html=True)
            for edu in education:
                tier = edu.get('tier', 'unknown')
                tier_icon = {"tier_1": "⭐", "tier_2": "🔵", "tier_3": "⚪", "tier_4": "⚪"}.get(tier, "")
                st.markdown(
                    f"{tier_icon} **{edu['degree']}** in {edu['field_of_study']} — {edu['institution']} "
                    f"<span style='color:#4a5568; font-size:12px;'>({edu['start_year']}–{edu['end_year']} · {tier})</span>",
                    unsafe_allow_html=True
                )

        st.divider()

        # Export this candidate
        st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)
        export_data = {
            'candidate_id': result['candidate_id'],
            'rank': rank,
            'score': score,
            'reasoning': result['reasoning'],
            'profile': profile,
            'score_breakdown': {
                'role_fit': components.get('role_fit'),
                'evidence_multiplier': components.get('evidence_multiplier'),
                'availability_multiplier': components.get('availability_multiplier'),
            }
        }
        st.download_button(
            "Download candidate JSON",
            data=json.dumps(export_data, indent=2),
            file_name=f"{result['candidate_id']}_profile.json",
            mime="application/json"
        )


# ─── Bottom: Export Shortlist ──────────────────────────────────────────────────

st.divider()
st.markdown("### Export Shortlist")

export_cols = st.columns(3)

with export_cols[0]:
    # CSV submission format
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(['candidate_id', 'rank', 'score', 'reasoning'])
    for i, r in enumerate(filtered[:100], 1):
        writer.writerow([r['candidate_id'], i, r['final_score'], r['reasoning']])

    st.download_button(
        "📥 Download submission CSV",
        data=csv_buf.getvalue(),
        file_name="redrob_submission.csv",
        mime="text/csv",
        use_container_width=True
    )

with export_cols[1]:
    # Full shortlist JSON
    export_json = [
        {
            'rank': i + 1,
            'candidate_id': r['candidate_id'],
            'score': r['final_score'],
            'reasoning': r['reasoning'],
            'title': r['profile']['current_title'],
            'yoe': r['profile']['years_of_experience'],
            'location': r['profile']['location'],
            'score_breakdown': {
                'role_fit': r.get('components', {}).get('role_fit'),
                'evidence_multiplier': r.get('components', {}).get('evidence_multiplier'),
                'availability_multiplier': r.get('components', {}).get('availability_multiplier'),
            }
        }
        for i, r in enumerate(filtered[:100])
    ]
    st.download_button(
        "📥 Download shortlist JSON",
        data=json.dumps(export_json, indent=2),
        file_name="shortlist.json",
        mime="application/json",
        use_container_width=True
    )

with export_cols[2]:
    st.info(f"Shortlist: {min(len(filtered), 100)} candidates · Scoring: evidence-based, 3-layer")
