# Redrob Candidate Ranker

**Redrob Hackathon — Intelligent Candidate Discovery & Ranking Challenge**

> *Score what a candidate's history proves. Not what their profile claims.*

---

## The Problem With Every Other Approach

A standard keyword ranker or embedding cosine similarity system has one exploitable weakness: it reads what a candidate *wrote*, not what they *did*.

A Marketing Manager who lists "LLMs, RAG, Pinecone, Transformers" in their skills section will outscore a genuine ML engineer whose profile uses different terminology. A consultant who spent 6 years doing SAP migrations but titles themselves "AI Engineer" this month looks identical to someone who shipped real retrieval systems at product companies.

This is the problem the PS is describing. Most submissions will solve it with better embeddings. We solved it differently.

---

## Core Idea

Candidate profiles have two layers:

- **What they wrote** — skills listed, titles claimed, summary keywords
- **What their history reveals** — how long they used each skill, what companies they worked at, whether their career descriptions contain evidence of real technical work, whether they actually respond to recruiters

Every keyword-based and embedding-based system reads layer 1. This system reads layer 2.

The insight is simple: **career description text is the hardest thing to fake.** Writing "Owned the ranking layer, evolved it from a hand-tuned scoring function to a learning-to-rank model, evaluated with NDCG and MRR, A/B tested against production traffic" requires having done it. Writing "worked with AI technologies" does not.

---

## Architecture

```
FINAL SCORE = (Role Fit × Evidence Quality × Availability × 0.92) + (Tiebreaker × 0.08)
```

### Layer 1 — Role Fit

Weighted sum of five components evaluated against the JD:

| Component | Weight | What it actually measures |
|---|---|---|
| Career Description Evidence | 35% | Technical terms found in job description text — not skills section |
| Title & Trajectory | 25% | Current title + progression of past roles toward ML/AI |
| Company Background | 15% | Product company history vs consulting-only career |
| Experience Fit | 15% | YoE against JD's 5–9yr target |
| Location | 10% | Pune/Noida/preferred India cities + relocation signal |

The 35% weight on career description evidence is the anti-gaming layer. The skills section is self-reported and unverified. Job descriptions require coherent sentences about actual work — specific terms like `embedding drift`, `NDCG`, `A/B test`, `learning to rank`, `re-rank`, `production traffic` appear because the person worked on these things, not because they read the job description.

### Layer 2 — Evidence Quality Multiplier (0.6× – 1.25×)

Cross-references skill claims against supporting evidence:

- Proficiency level vs duration months consistency — claiming `expert` with 4 months is a flag
- Platform assessment scores vs claimed proficiency — an `expert` who scored 28/100 on the assessment is a flag
- Core skill depth — `advanced`/`expert` in JD-critical skills with 12+ months boosts the multiplier
- Endorsement patterns on claimed skills

This catches keyword stuffers who load their profile with advanced-level claims that don't hold up under scrutiny.

### Layer 3 — Availability Multiplier (0.45× – 1.0×)

Behavioral gate using platform signals:

| Signal | Weight |
|---|---|
| Days since last active | 35% |
| Recruiter response rate | 30% |
| Notice period | 20% |
| Open to work flag | 10% |

Hard ceiling: candidates inactive for 6+ months AND response rate below 15% are capped at 0.45× regardless of how strong their skill profile is. A perfect-on-paper candidate who doesn't respond to recruiters is not a hire.

### Tiebreaker (8% weight)

When main scores are close, breaks ties on: Pune/Noida location precision, notice period under 30 days, assessment scores on JD-relevant skills specifically, GitHub activity score, and recruiter response reliability.

---

## Honeypot Defense

The spec mentions ~80 profiles with "subtly impossible" characteristics designed to trap naive rankers. Before scoring, each profile is checked for internal contradictions:

- Claimed YoE exceeds what the career start date allows
- Expert-level skills claimed with 0 months of recorded use
- 3+ assessment scores that contradict claimed proficiency level
- Current job duration impossible given its start date

Flagged profiles receive score 0.05 and cannot appear in the shortlist. We detected **57 suspicious profiles** in the 100K pool.

---

## Results

**100,000 candidates → top 100 shortlist in ~30 seconds on CPU.**

Top 10 ranked candidates — all verifiable against their profiles:

| Rank | Title | Company | Location | Score | Key evidence |
|---|---|---|---|---|---|
| 1 | Senior ML Engineer | Zomato → Flipkart | Noida | 1.000 | RAG (94mo expert), Learning to Rank (expert), NDCG + MRR in descriptions |
| 2 | Senior ML Engineer | Genpact AI → LinkedIn | Pune | 1.000 | Sentence Transformers (74mo), Information Retrieval (59mo), NDCG in descriptions |
| 3 | Search Engineer | Sarvam AI → Aganitha | Gurgaon | 1.000 | Milvus + Weaviate + RAG, A/B test + shipped in descriptions |
| 4 | Lead AI Engineer | Razorpay → Paytm | Jaipur | 1.000 | Embeddings (95mo), embedding drift + index refresh in descriptions |
| 5 | Senior ML Engineer | Flipkart → Uber | London | 0.999 | Vector Search (93mo), embedding drift + NDCG in descriptions |

Every candidate in the shortlist can be audited. The reasoning column in the CSV tells a recruiter exactly what to look at — specific skills with duration, specific terms from their actual job descriptions, assessment scores, and availability signals. Not a black-box number.

Title distribution in top 100: ML/Applied ML Engineer (30), Recommendation Systems Engineer (14), AI/Senior AI Engineer (13), Search Engineer (8), Senior Data Scientist (10), NLP Engineer (10), others (15). Zero Business Analysts. Zero HR Managers. Zero keyword stuffers.

---

## What Makes This Different

**vs keyword matching:** Doesn't read the skills section as ground truth. Reads career descriptions instead, where real work leaves specific, verifiable traces.

**vs embedding cosine similarity:** Embeddings still get fooled by ATS-optimized summaries. A summary full of "LLMs, RAG, vector search" embeds close to the JD regardless of whether the person actually built any of it. Our system requires corroborating evidence across multiple data sources.

**vs LLM reranking:** We don't call any LLM at ranking time. The scoring is deterministic, auditable, and runs in 30 seconds. An LLM reranker that processes 100K profiles at runtime is not a production system.

**vs pure behavioral filtering:** Behavioral signals matter but shouldn't override skill evidence. We use them as a multiplier and gate, not as the primary signal.

**The trust layer:** Every ranked candidate comes with a reasoning string that pulls specific evidence from their profile — not generated text, but extracted facts. A recruiter can look at rank 1 and verify: "RAG, 94 months, expert, confirmed by Weaviate assessment at 72/100, NDCG appears in 2 job descriptions, 15-day notice period, active 46 days ago." That's a shortlist a recruiter can trust.

---

## Reproduce

```bash
pip install -r requirements.txt
python rank.py --candidates candidates.jsonl --out submission.csv
python validate_submission.py submission.csv
```

Runs in ~30 seconds on CPU. No GPU. No API calls. No network access during ranking.

## Demo

```bash
streamlit run app.py
```

Or visit the hosted sandbox: [link in submission_metadata.yaml]

Upload `sample_candidates.json` from the dataset to try it on a sample, or load the pre-computed shortlist from the full 100K pool.

---

## Files

| File | Purpose |
|---|---|
| `ranker.py` | Core scoring engine — all three layers |
| `rank.py` | CLI entry point |
| `app.py` | Streamlit recruiter demo UI |
| `submission_final.csv` | Submission file (top 100 ranked candidates) |
| `top200_results.json` | Pre-computed results for demo |
| `sample_candidates.json` | Small sample from dataset for sandbox testing |
| `requirements.txt` | Dependencies (`streamlit` only) |

---

## AI Tools

Used Claude as a development assistant for architecture design and code generation. No candidate data was fed to any LLM. The ranking pipeline is fully deterministic — no LLM calls at inference time.