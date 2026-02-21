# Track Selection Decision Tree (v0.1)

Answer in order; pick the first strong match.

1) Is the primary object of study a **dataset/API/registry/leak** you might ingest or rely on?
- Yes → **Track D — Data Source Assessment (data-source)**

2) Is the primary object of study a **software technology/platform** you might adopt (DB, engine, framework, tool)?
- Yes → **Track C — Technology / Platform Evaluation (tech-evaluation)**

3) Is the primary object of study a **product/tool similar to Power Atlas** (OSINT, link analysis, KG exploration, “influence scoring”), mainly to learn patterns/hazards?
- Yes → **Track F — Similar Platforms Review (similar-platforms)**

4) Is the primary object of study an **investigative/journalistic case** where the output is a network and you want to understand the method and build evaluation scenarios?
- Yes → **Track E — Journalistic / Investigative Case Study (case-study)**

5) Is the primary object of study an **academic/scientific body of work** (theory, field, conceptual framework) to borrow vocabulary/constraints/cautions?
- Yes → **Track A — Conceptual / Scientific Research (conceptual-research)**

6) Is the primary object of study a **method/technique** that could shape core capabilities (ER, extraction, uncertainty, evaluation, review workflows)?
- Yes → **Track B — Methods / Techniques Research (methods-techniques)**

7) Is this primarily an **internal question** meant to stress-test semantics/governance (“what if we…”), not external literature?
- Yes → **Track G — Internal Design Spike / Thought Experiment (internal-spike)**

8) None fit well → **Track M — Misc / Hybrid (misc)**
- Required: state why, and propose intended reclassification or split.
