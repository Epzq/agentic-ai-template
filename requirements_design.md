# Research Opportunity Intelligence Agent
## Final Requirements and System Design Specification

**Purpose:** Implementation handoff for Claude Code  
**Status:** Final design  
**Primary LLM:** Google Gemini  
**Implementation language:** Python

---

# 1. Executive Summary

This system is an **agentic research-funding decision-support tool**.

The tool is intended for a researcher or research team who has:

1. a specific grant call available as a webpage and/or PDF; and
2. a public researcher/team biography, lab page, or academic website.

The researcher **does not need to have a research topic in mind**.

The system must determine promising research directions by combining:

- what the grant call requires and prioritizes;
- what the applicant/team is genuinely capable of doing;
- what the current literature shows is already solved or still open;
- how competitive each candidate direction is;
- which collaborators could fill capability gaps.

The system does **not** write a grant proposal.

Its final job is to produce an evidence-backed ranking of research directions that are strong candidates for the applicant to pursue under the supplied funding call.

The final system should answer:

> **Given this grant call and this researcher/team, what are the strongest research directions they should consider, why are they strong, how competitive are they, and what collaboration opportunities could strengthen them?**

---

# 2. Problem Background

Researchers may begin a funding application with only:

- a funding opportunity; and
- their own expertise, publication history, collaborations, and publicly visible research capabilities.

They may not yet know the best research topic to pursue.

Finding a strong topic requires reasoning across several information spaces:

- grant scope and eligibility;
- funding-agency priorities;
- evaluation criteria;
- applicant track record;
- applicant research trajectory;
- recent and foundational research literature;
- real unresolved research gaps;
- active competing researchers and groups;
- possible collaborators.

Doing this manually is time-consuming and error-prone. A researcher can easily choose:

- a scientifically interesting topic that does not fit the grant;
- a grant-aligned topic that does not fit their expertise;
- an apparent research gap that has already been addressed;
- an overly crowded direction;
- a direction that depends on expertise the team does not possess.

The proposed system addresses this using specialized agents and explicit evidence exchange between them.

---

# 3. Final Scope

## 3.1 Required user inputs

The MVP accepts only the following required inputs.

### Input A — Grant call

One or both of:

- grant-call webpage URL;
- grant-call PDF.

Example:

```text
https://<funding-agency>/<grant-call>
```

or:

```text
/path/to/grant_call.pdf
```

### Input B — Researcher/team profile

A public biography, lab, academic, or research-group website.

Example:

```text
https://<researcher-or-lab-website>/
```

The user is **not required to provide a research topic**.

---

## 3.2 Final system output

The system returns a **Final Research Direction Ranking Report**.

For each recommended direction, the output should include:

- rank;
- research direction;
- concise problem statement;
- evidence-backed open gap;
- grant alignment;
- applicant/team fit;
- scientific novelty;
- scientific/practical importance;
- competitive intensity;
- competitive differentiation;
- collaborator needs;
- potential collaborator candidates where evidence supports them;
- key strengths;
- key weaknesses;
- major risks or uncertainties;
- confidence;
- supporting evidence/provenance.

The system should normally return the top **3–5 research directions**, depending on the quality of available evidence.

---

# 4. Explicit Non-Goals

The MVP does **not**:

- automatically discover and compare all grants in Singapore;
- require the researcher to supply a research topic;
- write a full grant proposal;
- draft proposal sections;
- create a project budget;
- estimate salaries, equipment costs, or project expenditure;
- perform a separate reviewer/critic stage;
- fabricate collaborators;
- claim that a researcher will collaborate;
- invent missing grant requirements;
- infer unavailable resources as if they are known;
- treat a single paper limitation as proof of a field-wide research gap.

The product is a **research opportunity identification, evidence analysis, competitor/collaborator intelligence, and research-direction ranking tool**.

---

# 5. Final High-Level Architecture

```text
                    PROPOSAL MANAGER /
                       COORDINATOR
                            |
                            v
                         USER INPUT
                            |
              +-------------+-------------+
              |                           |
         Grant Call                Researcher /
        PDF / Webpage              Team Bio Website
              |                           |
              v                           v
       Grant Analyzer             Applicant Profile
           Agent                  Analyzer Agent
              |                           |
              +-------------+-------------+
                            |
                            v
                Research Opportunity &
                     Gap Agent
                            |
                            v
             Competitor & Collaborator
                       Agent
                            |
                            v
              Research Direction Ranking
                       Agent
                            |
                            v
             FINAL RANKED RESEARCH
                  DIRECTIONS
```

The **Proposal Manager / Coordinator** manages the workflow, system state, agent invocation, and final consolidation.

---

# 6. Core Design Principles

## 6.1 Evidence first

Every important factual claim should be traceable to a source.

Examples:

- grant requirement -> grant PDF/webpage;
- applicant expertise -> publication/profile/project evidence;
- research gap -> multiple relevant papers and recent verification;
- competitor claim -> recent related publications/projects;
- collaborator fit -> documented expertise or resources.

## 6.2 Separate fact from inference

Outputs should clearly distinguish:

- **stated fact**;
- **agent inference**;
- **unknown / not specified**.

Example:

```text
FACT:
The grant explicitly requires a Singapore-based lead PI.

INFERENCE:
A Singapore-based collaborator could strengthen the team for this call.

UNKNOWN:
The applicant's access to a physical robot platform could not be verified.
```

## 6.3 Never invent missing information

Use values such as:

```text
not_specified
unknown
not_verified
insufficient_evidence
```

rather than guessing.

## 6.4 Prefer authoritative and current sources

For grant requirements, prefer:

1. official call document;
2. official funding-agency website;
3. official FAQ/guidelines;
4. secondary sources only when necessary.

For researcher information, prefer:

1. researcher/lab website;
2. institutional page;
3. ORCID;
4. DBLP / Semantic Scholar / OpenAlex;
5. publication pages.

## 6.5 Use recent literature to validate gaps

A limitation reported several years ago is not automatically a current research gap.

Every shortlisted gap must undergo a **recent-work verification search**.

## 6.6 Use applicant fit, not just scientific novelty

A highly novel topic may still be a poor recommendation if the applicant lacks:

- relevant expertise;
- credible track record;
- suitable methodological background;
- collaborators needed to fill important expertise gaps.

## 6.7 Keep ranking transparent

The ranking must expose:

- criteria;
- weights;
- per-criterion scores;
- supporting evidence;
- uncertainty.

Do not return a black-box overall score only.

---

# 7. Agent 1 — Proposal Manager / Coordinator

## Key question

> **Given the grant call and applicant profile, what information do we currently have, what is missing, which specialist agent should run next, and is the analysis ready to finish?**

## Main input

Initial input:

```json
{
  "grant_source": {
    "url": "...",
    "pdf_path": "..."
  },
  "applicant_profile_url": "..."
}
```

During execution it also receives the full research-opportunity state.

## Tools

The Coordinator mainly uses specialist agents as tools:

```text
analyze_grant()
analyze_applicant_profile()
find_research_opportunities_and_gaps()
analyze_competitors_and_collaborators()
rank_research_directions()
```

The Coordinator should generally **not** directly perform deep literature search or competitor research.

## Reasoning

The Coordinator determines:

1. Has the grant been fully analyzed?
2. Has the applicant/team profile been characterized?
3. Have grant priorities and applicant capabilities been intersected?
4. Have real research opportunities and gaps been found?
5. Have gaps been checked against active competitors?
6. Have missing capabilities and collaborator options been identified?
7. Have candidate directions been ranked?
8. Is the available evidence sufficient to finalize the ranking?

The first two agents can run in parallel:

```text
Grant Analyzer
      +
Applicant Profile Analyzer
```

Later stages depend on their outputs.

## Main output

The Coordinator produces:

- next agent/action;
- updated system state;
- request for missing user information only when it cannot be obtained through tools;
- final consolidated ranked-research-direction report.

## State model

```python
proposal_state = {
    "grant_analysis": None,
    "applicant_profile": None,
    "candidate_research_directions": None,
    "candidate_gaps": None,
    "competitor_analysis": None,
    "collaborator_analysis": None,
    "direction_ranking": None,
    "final_recommendations": None,
    "status": "initialized"
}
```

---

# 8. Agent 2 — Grant Analyzer Agent

## Key question

> **What exactly does this funding call require, prioritize, permit, restrict, and evaluate?**

## Main input

- official grant-call webpage;
- grant-call PDF;
- supplementary grant documents/FAQ if discoverable.

The applicant profile is not required for the core grant analysis.

## Tools

- webpage retrieval;
- PDF/document parser;
- structured information extractor;
- official funding-agency website search;
- general web search for supplementary official materials;
- optional eligibility-rule checker.

## Reasoning

### 1. Identify the exact grant

Extract:

- funding agency;
- grant programme;
- specific call;
- call year/cycle.

### 2. Extract explicit requirements

Examples:

- maximum funding;
- project duration;
- deadline;
- eligible institution;
- PI requirements;
- collaborator requirements;
- submission requirements.

If unavailable, mark as `not_specified`.

### 3. Separate mandatory vs preferred conditions

Example:

```text
MANDATORY
- eligible host institution
- maximum project duration
- budget ceiling

PREFERRED / ENCOURAGED
- multidisciplinary team
- industry partnership
- national impact
```

### 4. Determine research scope

Classify areas as:

- explicitly in scope;
- potentially in scope;
- out of scope / weakly aligned.

### 5. Infer funder priorities

Look for repeated themes such as:

- scientific excellence;
- national relevance;
- economic or societal impact;
- translation;
- deployment;
- multidisciplinary research;
- industry partnership.

These must be labeled as **interpretation**, not explicit requirements, unless directly stated.

### 6. Analyze evaluation criteria

Extract:

- criteria;
- weights if provided;
- implications for later ranking.

### 7. Identify grant-related risks

Examples:

- missing required partner;
- topic outside scope;
- project duration outside allowed limits.

## Main output

### Grant Intelligence Report

Suggested schema:

```json
{
  "grant_identity": {
    "funding_agency": "...",
    "programme": "...",
    "call_name": "...",
    "call_year": "..."
  },
  "objectives": [],
  "priority_research_areas": [],
  "eligibility": {
    "pi_requirements": [],
    "institution_requirements": [],
    "collaboration_requirements": []
  },
  "funding": {
    "maximum_budget": null,
    "project_duration": null
  },
  "timeline": {
    "opening_date": null,
    "deadline": null
  },
  "evaluation_criteria": [],
  "mandatory_requirements": [],
  "preferred_characteristics": [],
  "expected_outcomes": [],
  "restrictions": [],
  "strategic_observations": [],
  "risks": [],
  "information_missing": [],
  "evidence": []
}
```

---

# 9. Agent 3 — Applicant Profile Analyzer Agent

## Key question

> **What research expertise, track record, capabilities, collaborations, and strategic strengths does this researcher/team have that can support a competitive research direction?**

## Main input

- researcher/team bio website.

The agent may follow relevant public links from the site.

## Tools

- webpage retrieval;
- same-domain/site crawler with bounded depth;
- institutional-profile search;
- scholarly author search;
- publication search;
- Semantic Scholar;
- OpenAlex;
- DBLP;
- ORCID;
- optional Google Scholar profile lookup when available;
- project/lab website search;
- co-authorship analysis.

## Reasoning

### 1. Resolve researcher/team identity

Avoid mixing researchers with the same or similar names.

Use:

- current institution;
- publication topics;
- personal/lab website;
- ORCID if available.

### 2. Identify core expertise

Distinguish:

- sustained/core research expertise;
- emerging research directions;
- occasional publication topics.

### 3. Identify methodological strengths

Examples:

- computer vision;
- VLMs;
- robotics;
- causal inference;
- optimization;
- hardware systems.

### 4. Identify application/domain strengths

Examples:

- healthcare;
- manufacturing;
- robotics;
- mobility;
- education.

### 5. Analyze research trajectory

Determine how research interests have evolved over time.

### 6. Extract resources only when evidenced

Possible publicly verifiable resources:

- compute infrastructure;
- datasets;
- robot platforms;
- labs;
- testbeds;
- industry access;
- research facilities.

If not publicly verified, mark as unknown.

### 7. Identify existing collaboration network

Use:

- co-authors;
- joint projects;
- current collaborators;
- institutions;
- industry partners.

### 8. Identify capability strengths and gaps

Produce an evidence-backed capability map.

## Main output

### Applicant Capability Profile

Suggested schema:

```json
{
  "applicant_identity": {
    "name": "...",
    "institution": "...",
    "role": "..."
  },
  "core_expertise": [],
  "emerging_research_areas": [],
  "methodological_strengths": [],
  "application_domains": [],
  "representative_publications": [],
  "research_trajectory": [],
  "available_resources": [],
  "existing_collaborations": [],
  "capability_strengths": [],
  "capability_gaps": [],
  "unknown_information": [],
  "evidence": []
}
```

---

# 10. Agent 4 — Research Opportunity & Gap Agent

## Key question

> **At the intersection of the grant's priorities and the applicant's capabilities, what promising research directions contain important, defensible, current, and feasible open research gaps?**

## Main input

1. Grant Intelligence Report
2. Applicant Capability Profile

No researcher-supplied topic is required.

## Tools

### Scholarly search

Recommended sources:

- Google Scholar — https://scholar.google.com/
- Semantic Scholar — https://www.semanticscholar.org/
- OpenAlex — https://openalex.org/
- arXiv — https://arxiv.org/
- IEEE Xplore — https://ieeexplore.ieee.org/
- DBLP — https://dblp.org/
- ACM Digital Library — https://dl.acm.org/
- PubMed — https://pubmed.ncbi.nlm.nih.gov/

### Paper retrieval / reader

Inspect where available:

- abstract;
- introduction;
- related work;
- method;
- experiments;
- limitations;
- discussion;
- conclusion.

### Related/citing-paper exploration

Possible interfaces:

```text
find_related_papers()
find_citing_papers()
```

### Recent-paper search

Must verify whether an older limitation remains unresolved.

### Research-landscape mapping

Cluster literature into coherent subareas.

### Grant–applicant intersection analysis

Generate candidate directions from:

```text
grant priorities
      x
applicant capabilities
```

### Gap verification

For every proposed gap, explicitly search for recent work targeting that gap.

### Optional patent/technology search

Useful for translation-oriented calls.

## Reasoning

### 1. Find grant–applicant intersections

Example:

```text
Grant priorities:
trustworthy autonomous systems

Applicant capabilities:
multimodal learning + embodied AI

Candidate direction:
trustworthy multimodal embodied agents
```

At this stage these are **directions**, not validated gaps.

### 2. Generate several candidate research directions

Do not prematurely commit to one topic.

### 3. Map the research landscape for each direction

Identify:

- subareas;
- representative work;
- recent work;
- current state.

### 4. Extract known limitations

For important papers:

- what problem is solved?
- what assumptions are made?
- what is not solved?
- what limitations are explicitly stated?

### 5. Detect recurring unresolved limitations

A strong gap should usually be supported by multiple pieces of evidence.

### 6. Classify the gap

Possible categories:

- capability gap;
- generalization gap;
- evaluation gap;
- methodological gap;
- data gap;
- deployment gap.

### 7. Verify the gap is still open

Run targeted recent searches.

Reject or weaken a gap when recent work substantially addresses it.

### 8. Evaluate each gap

Criteria:

- scientific novelty;
- importance;
- grant alignment;
- evidence strength;
- applicant fit;
- feasibility;
- impact potential.

### 9. Rank preliminary opportunities

Return several candidates rather than selecting a final direction.

## Main output

### Research Opportunity & Gap Intelligence Report

Suggested structure:

```json
{
  "candidate_research_directions": [
    {
      "direction_id": "D1",
      "title": "...",
      "grant_alignment": "...",
      "applicant_alignment": "...",
      "reason": "...",
      "evidence": []
    }
  ],
  "research_landscape": [
    {
      "direction_id": "D1",
      "subareas": [],
      "representative_work": [],
      "current_state": "..."
    }
  ],
  "candidate_gaps": [
    {
      "gap_id": "G1",
      "direction_id": "D1",
      "title": "...",
      "gap_type": "...",
      "current_state": "...",
      "missing_capability": "...",
      "why_it_matters": "...",
      "grant_alignment_score": 0,
      "applicant_fit_score": 0,
      "novelty_score": 0,
      "importance_score": 0,
      "feasibility_score": 0,
      "evidence_strength_score": 0,
      "confidence": "...",
      "risks": [],
      "evidence": []
    }
  ],
  "preliminary_ranked_opportunities": [],
  "rejected_or_weak_opportunities": []
}
```

---

# 11. Agent 5 — Competitor & Collaborator Agent

## Key question

> **For the candidate research opportunities, who is already working on these problems, how competitive is each opportunity, and which researchers, labs, institutions, or companies could complement the applicant team?**

## Main input

1. Research Opportunity & Gap Intelligence Report
2. Applicant Capability Profile
3. Grant Intelligence Report

## Tools

### Scholarly literature search

Use the same academic sources as the Research Opportunity & Gap Agent, but with a different objective:

> identify **who repeatedly publishes** on each specific gap.

### Author/researcher search

Possible interface:

```text
search_researchers()
```

Retrieve:

- researcher name;
- institution;
- research interests;
- recent publications;
- co-authors;
- related projects.

### Researcher-profile retrieval

Possible interface:

```text
get_researcher_profile()
```

### Institution/lab search

Possible interface:

```text
search_research_labs()
```

Search:

- university labs;
- research institutes;
- government research centres;
- industry research groups.

### Citation and co-authorship analysis

Possible interfaces:

```text
get_citation_network()
get_coauthor_network()
```

### Funded-project search

Possible interface:

```text
search_funded_projects()
```

Useful public sources may include:

- relevant national funding databases;
- CORDIS;
- UKRI Gateway to Research;
- NSF Award Search;
- NIH RePORTER.

### Institutional/lab websites

Verify:

- current affiliation;
- lab focus;
- facilities;
- hardware;
- current projects;
- industry partnerships.

### Industry partner search

Useful for calls that emphasize translation or deployment.

## Reasoning

### 1. Analyze each shortlisted gap separately

Use gap-specific queries.

### 2. Identify active researchers/groups

Prefer evidence from:

- multiple recent relevant publications;
- repeated activity;
- current projects;
- coherent research trajectory.

### 3. Measure technical overlap

Classify:

- direct competitor;
- adjacent competitor;
- potential collaborator;
- both competitor and collaborator;
- insufficiently related.

Do not label someone a competitor merely because they work in the same broad field.

### 4. Estimate competitive intensity

Consider:

- number of active groups;
- recency;
- method similarity;
- maturity;
- funded activity.

Return:

- LOW / MEDIUM / HIGH;
- or normalized numeric score.

### 5. Identify applicant capability gaps for each direction

Determine what expertise is needed to execute the direction that the applicant does not already have.

### 6. Define collaborator profiles before searching names

Examples:

- formal-safety group;
- physical robot validation lab;
- healthcare end-user partner;
- manufacturing partner.

### 7. Search concrete collaborators

Search individuals, labs, institutions, and companies that satisfy the required capability profiles.

### 8. Check grant collaboration rules

A technically useful collaborator may not satisfy a required partner category.

### 9. Score collaborator fit

Criteria:

- expertise fit;
- complementarity;
- research relevance;
- grant fit;
- resource contribution where evidenced;
- track record;
- overlap risk.

### 10. Do not assume willingness

Output:

```text
potential collaborator
```

not:

```text
confirmed collaborator
```

unless evidence explicitly supports confirmation.

### 11. Update strategic attractiveness of the research directions

The agent may show that a direction is:

- scientifically strong but crowded;
- less crowded but dependent on missing expertise;
- stronger when paired with a specific collaborator profile.

It does not make the final selection.

## Main output

### Competitor & Collaborator Intelligence Report

Suggested schema:

```json
{
  "opportunity_competition_analysis": [],
  "applicant_capability_gaps": [],
  "required_collaborator_profiles": [],
  "potential_collaborators": [],
  "opportunity_strategic_assessment": [],
  "recommended_collaboration_options": [],
  "risks_and_uncertainties": [],
  "evidence": []
}
```

---

# 12. Agent 6 — Research Direction Ranking Agent

## Key question

> **Considering the grant requirements, applicant capabilities, research gaps, competitive landscape, and collaboration opportunities, which research directions are the strongest opportunities for this applicant?**

## Main input

1. Grant Intelligence Report
2. Applicant Capability Profile
3. Research Opportunity & Gap Intelligence Report
4. Competitor & Collaborator Intelligence Report

## Tools

### Multi-criteria scoring

Score candidate directions on a normalized scale, e.g. 0–10.

### Weighted ranking

Weights should be derived from grant evaluation priorities when explicit.

If the grant does not provide usable weights:

- derive them from the grant's stated priorities; or
- use configurable default weights.

Always expose the weights in the result.

### Normalization

Convert values such as:

```text
LOW / MEDIUM / HIGH
```

into comparable internal numeric values.

### Evidence aggregation

Each criterion score must point to supporting evidence from upstream reports.

### Constraint checker

Hard grant violations should disqualify or strongly penalize a direction.

### Sensitivity analysis

Test whether modest changes in criterion weights significantly change the ordering of top candidates.

### Optional multi-criteria decision analysis

The MVP can use a transparent weighted-sum model.

More sophisticated methods such as TOPSIS or AHP may be added later if useful.

## Required ranking criteria

At minimum:

1. Grant alignment
2. Scientific novelty
3. Scientific/practical importance
4. Applicant fit
5. Feasibility
6. Competitive differentiation
7. Collaboration potential
8. Impact potential
9. Evidence strength

## Reasoning

1. Normalize upstream scores.
2. Determine ranking weights.
3. Apply hard grant constraints.
4. Compute per-direction criterion scores.
5. Aggregate weighted score.
6. Explain every score using evidence.
7. Perform sensitivity analysis.
8. Identify close or uncertain rankings.
9. Rank the candidate directions.
10. Produce the final research-direction recommendations.

## Main output

### Final Research Direction Ranking Report

Suggested schema:

```json
{
  "ranking_criteria": {
    "grant_alignment": 0.0,
    "scientific_novelty": 0.0,
    "importance": 0.0,
    "applicant_fit": 0.0,
    "feasibility": 0.0,
    "competitive_differentiation": 0.0,
    "collaboration_potential": 0.0,
    "impact_potential": 0.0,
    "evidence_strength": 0.0
  },
  "ranked_directions": [
    {
      "rank": 1,
      "direction_id": "G1",
      "title": "...",
      "problem_statement": "...",
      "evidence_backed_gap": "...",
      "scores": {},
      "overall_score": 0.0,
      "key_strengths": [],
      "key_weaknesses": [],
      "competition_level": "...",
      "competitive_differentiation": "...",
      "required_collaborator_profiles": [],
      "potential_collaborators": [],
      "risks_and_uncertainties": [],
      "confidence": "...",
      "recommendation": "...",
      "evidence": []
    }
  ],
  "rejected_or_weak_directions": [
    {
      "direction_id": "...",
      "reason": "..."
    }
  ],
  "sensitivity_analysis": {}
}
```

The ranking agent is the **final analytical agent** in the workflow.

---

# 13. Final Workflow Logic

## Phase 1 — Input

User provides:

```text
grant webpage/PDF
+
researcher/team profile URL
```

## Phase 2 — Parallel understanding

Run in parallel:

```text
Grant Analyzer
Applicant Profile Analyzer
```

## Phase 3 — Opportunity discovery

Use both outputs to run:

```text
Research Opportunity & Gap Agent
```

## Phase 4 — Competitor/collaborator intelligence

Run:

```text
Competitor & Collaborator Agent
```

## Phase 5 — Final ranking

Run:

```text
Research Direction Ranking Agent
```

## Phase 6 — Final output

The Coordinator consolidates the final ranking into a human-readable report.

No proposal-writing, budget, or critic stage is included.

---

# 14. Recommended Implementation Architecture

## 14.1 Language and model

Use:

```text
Python
Google Gemini API
google-genai Python SDK
```

API key:

```text
GEMINI_API_KEY
```

stored in `.env`.

Do not hardcode API keys.

## 14.2 Orchestration strategy

Use a **hybrid deterministic + agentic workflow**.

The dependency graph is deterministic:

```text
Grant + Applicant
    ->
Opportunity/Gap
    ->
Competitor/Collaborator
    ->
Ranking
```

Within each stage, Gemini can:

- reason;
- generate search queries;
- call tools;
- inspect results;
- perform additional retrieval when evidence is insufficient.

The Coordinator controls:

- state;
- dependency enforcement;
- retries;
- stage completion;
- final consolidation.

This is preferable to giving one LLM unrestricted autonomy over the whole system.

## 14.3 Structured outputs

Every agent must return structured output.

Use Pydantic models where practical.

Example:

```python
from pydantic import BaseModel
```

Gemini output should be parsed and validated before being committed to shared state.

If validation fails:

1. retry with schema-correction instructions;
2. if still invalid, mark the stage as failed;
3. do not silently continue with malformed data.

---

# 15. Suggested Project Structure

Use `app_agents` rather than a local folder named `agents`, because the latter can conflict with installed Python packages.

```text
hackathon/
|
|-- main.py
|-- .env
|-- requirements.txt
|
|-- app_agents/
|   |-- __init__.py
|   |-- coordinator.py
|   |-- grant_analyzer.py
|   |-- applicant_profile_analyzer.py
|   |-- research_opportunity_gap.py
|   |-- competitor_collaborator.py
|   `-- direction_ranker.py
|
|-- tools/
|   |-- __init__.py
|   |-- web_retrieval.py
|   |-- pdf_reader.py
|   |-- academic_search.py
|   |-- author_search.py
|   |-- citation_search.py
|   |-- grant_search.py
|   |-- project_search.py
|   `-- evidence_tools.py
|
|-- schemas/
|   |-- __init__.py
|   |-- grant.py
|   |-- applicant.py
|   |-- opportunity.py
|   |-- competitor.py
|   `-- ranking.py
|
|-- prompts/
|   |-- grant_analyzer.txt
|   |-- applicant_profile.txt
|   |-- research_opportunity_gap.txt
|   |-- competitor_collaborator.txt
|   `-- direction_ranker.txt
|
|-- config/
|   |-- ranking_weights.yaml
|   `-- source_config.yaml
|
|-- outputs/
|   `-- run_<timestamp>/
|       |-- grant_intelligence.json
|       |-- applicant_capability.json
|       |-- opportunity_gap.json
|       |-- competitor_collaborator.json
|       |-- ranking.json
|       `-- final_report.md
|
`-- tests/
    |-- test_grant_parser.py
    |-- test_profile_parser.py
    |-- test_gap_analysis.py
    |-- test_competitor_analysis.py
    |-- test_ranking.py
    `-- test_end_to_end.py
```

---

# 16. Research and Data Sources

## Academic literature

### Recommended machine-accessible primary sources

- Semantic Scholar — https://www.semanticscholar.org/
- OpenAlex — https://openalex.org/
- arXiv — https://arxiv.org/
- DBLP — https://dblp.org/
- PubMed — https://pubmed.ncbi.nlm.nih.gov/

### Additional scholarly sources

- IEEE Xplore — https://ieeexplore.ieee.org/
- ACM Digital Library — https://dl.acm.org/
- Google Scholar — https://scholar.google.com/

Implementation notes:

- avoid relying solely on Google Scholar because it does not provide a general official public API for unrestricted automated search;
- prefer APIs such as Semantic Scholar, OpenAlex, arXiv, DBLP, and PubMed for reproducible programmatic retrieval;
- use IEEE/ACM where legally and technically accessible;
- respect terms of service and rate limits.

## Researcher identity/profile sources

- researcher's website;
- university/institution page;
- lab website;
- ORCID;
- DBLP;
- Semantic Scholar;
- OpenAlex.

## Funding/project sources

Prefer official funding databases and agency sites.

For competitor/collaborator intelligence, useful international examples include:

- CORDIS;
- UKRI Gateway to Research;
- NSF Award Search;
- NIH RePORTER.

---

# 17. Evidence and Provenance Model

Every retrieved item should use a common evidence structure.

Example:

```json
{
  "source_type": "grant_pdf | webpage | paper | profile | project",
  "title": "...",
  "url": "...",
  "authors": [],
  "publication_date": "...",
  "retrieved_at": "...",
  "supports": "...",
  "evidence_summary": "...",
  "confidence": "high | medium | low"
}
```

For PDFs, additionally store:

```json
{
  "page": 12
}
```

When possible, store exact paragraph or section identifiers.

The system should be capable of explaining **why** it made every major recommendation.

---

# 18. Search Strategy Requirements

## Research-gap search

For each candidate direction:

1. broad landscape search;
2. representative/foundational work search;
3. recent work search;
4. explicit limitation search;
5. targeted verification of candidate gaps;
6. citing/related work search;
7. reject gaps contradicted by recent evidence.

## Competitor search

For each candidate gap:

1. identify repeated authors/groups;
2. retrieve recent relevant work;
3. compare technical scope;
4. classify overlap;
5. estimate competition.

## Collaborator search

First identify missing capability, then search.

Correct:

```text
Need formal safety expertise
    ->
search formal robot safety researchers/labs
```

Incorrect:

```text
search famous robotics professors
```

---

# 19. Ranking Requirements

## Scoring scale

Use a normalized scale such as:

```text
0–10
```

for each criterion.

## Required criteria

```text
grant_alignment
scientific_novelty
importance
applicant_fit
feasibility
competitive_differentiation
collaboration_potential
impact_potential
evidence_strength
```

## Weight selection

Priority:

1. use explicit grant evaluation weights when they map to ranking criteria;
2. otherwise derive weights from grant priorities;
3. if still unavailable, use configurable defaults.

Always show the weights used.

## Hard constraints

Examples:

- applicant clearly ineligible;
- research clearly outside grant scope;
- project fundamentally incompatible with a mandatory grant condition.

Hard constraints should not be hidden inside ordinary weighted scores.

## Sensitivity analysis

The top ranking should be marked less certain when small changes in weights reverse the order of top candidates.

---

# 20. Reliability Rules

## Never fabricate

Do not fabricate:

- grant rules;
- publications;
- researcher affiliations;
- collaborators;
- project funding;
- resources;
- citation counts.

## Identity ambiguity

If researcher identity is ambiguous:

```text
identity_confidence = low
```

and search for stronger disambiguation.

## Missing evidence

A low-evidence candidate should receive:

```text
confidence = low
```

even if the LLM finds the idea plausible.

## Source freshness

Recent literature should receive special attention because the objective is to find **currently open** opportunities.

## Public professional information only

The profile-analysis component should use public professional information relevant to research capability.

---

# 21. Error Handling

The system should handle:

### Grant webpage inaccessible

- try official PDF;
- try supplementary official pages;
- report inaccessible content.

### Scanned PDF

- use OCR only when normal PDF text extraction fails.

### Researcher profile unavailable

- search official institution and academic-profile sources;
- report missing data.

### Academic API failure

- use fallback provider;
- preserve partial evidence;
- do not fabricate results.

### No credible gap found

Return:

```text
No high-confidence research gap identified from the available evidence.
```

Do not force a recommendation.

### No suitable collaborator found

Return a required collaborator profile rather than inventing a named collaborator.

---

# 22. MVP Interface

The first implementation can be CLI-based.

Example:

```bash
python main.py \
  --grant-url "https://..." \
  --grant-pdf "/path/to/call.pdf" \
  --profile-url "https://..."
```

At least one grant source must be supplied.

Output:

```text
outputs/run_<timestamp>/final_report.md
```

plus all intermediate JSON reports.

A web UI can be added later without changing the agent architecture.

---

# 23. Final Report Format

The human-facing `final_report.md` should contain:

## A. Grant summary

- purpose;
- scope;
- eligibility;
- funding ceiling/duration where relevant to understanding the call;
- evaluation priorities.

## B. Applicant capability summary

- strongest expertise;
- research trajectory;
- verified resources where relevant;
- known capability gaps.

## C. Research landscape summary

- major relevant research directions;
- important current trends.

## D. Ranked research directions

For each candidate:

```text
Rank:
Direction:
Problem:
Evidence-backed gap:
Grant alignment:
Applicant fit:
Novelty:
Importance:
Competition:
Competitive differentiation:
Required collaborator profile(s):
Potential collaborators:
Key strengths:
Key weaknesses:
Risks / uncertainty:
Confidence:
Supporting sources:
```

## E. Directions not recommended

Explain why:

- already crowded;
- weak applicant fit;
- weak grant fit;
- low evidence;
- outside grant scope;
- excessive dependency on missing expertise.

---

# 24. Suggested Development Order

Implement incrementally.

## Stage 1

- schemas;
- Gemini client;
- grant webpage/PDF ingestion;
- Grant Analyzer Agent.

## Stage 2

- researcher website ingestion;
- academic identity resolution;
- Applicant Profile Analyzer Agent.

## Stage 3

- academic search adapters;
- Research Opportunity & Gap Agent;
- evidence/provenance store.

## Stage 4

- author/group search;
- Competitor & Collaborator Agent.

## Stage 5

- transparent weighted ranking;
- Research Direction Ranking Agent;
- final report generation.

## Stage 6

- tests;
- caching;
- parallel retrieval;
- rate-limit handling;
- performance improvements.

---

# 25. Testing and Evaluation

The tool should be evaluated on several grant/profile pairs.

## Grant Analyzer

Measure:

- requirement extraction accuracy;
- correct mandatory/preferred classification;
- deadline/budget/duration accuracy where present.

## Applicant Profile Analyzer

Measure:

- expertise extraction precision;
- identity resolution correctness;
- unsupported-resource claim rate.

## Research Opportunity & Gap Agent

Human expert review:

- gap validity;
- evidence sufficiency;
- novelty;
- grant alignment;
- applicant alignment.

## Competitor & Collaborator Agent

Check:

- whether competitor overlap is correctly characterized;
- whether collaborator recommendations genuinely fill capability gaps;
- whether current affiliations are correct.

## Ranking Agent

Evaluate:

- score explainability;
- ranking stability;
- agreement with expert judgment;
- evidence coverage for each score.

---

# 26. Definition of Done for the MVP

The MVP is complete when a user can provide:

```text
1. grant URL and/or PDF
2. researcher/team profile URL
```

and the system automatically produces:

1. Grant Intelligence Report
2. Applicant Capability Profile
3. Research Opportunity & Gap Intelligence Report
4. Competitor & Collaborator Intelligence Report
5. Final Research Direction Ranking Report

with:

- traceable evidence;
- structured JSON;
- a human-readable Markdown report;
- no required researcher-supplied topic;
- no proposal writing;
- no budget/resource agent;
- no reviewer/critic agent.

---

# 27. One-Sentence Product Definition

> **An agentic system that takes a grant call and a researcher/team profile, discovers evidence-backed research opportunities at their intersection, evaluates research gaps, competition, and collaboration potential, and returns a transparent ranking of the strongest research directions to pursue.**
