# Integration and Validation Architecture for Power Atlas Experimental Pipeline

## Executive summary

This Week 6 deliverable specifies an experimental (architecture + methods) pipeline that integrates bipartite projection, multilayer construction, structural metrics, community detection via modularity and stochastic block models, brokerage measures, iterative latent capability inference, temporal evolution modeling, and derived-entity storage—while enforcing time-scoped edges, confidence scoring, algorithmic provenance, and human-in-the-loop oversight. The central design premise is that *every* derived structural output must be (a) reproducible, (b) attributable to a specific dataset snapshot and parameterization, and (c) accompanied by stability diagnostics demonstrating that results are not artifacts of modeling choices. This premise is aligned with multilayer-network best practice emphasizing explicit modeling assumptions and sensitivity to layer coupling and definitions. citeturn0search5turn6search1turn6search0

The proposed architecture is modular and stage-gated, with explicit validation checkpoints and failure containment. The pipeline starts from an evidence-first ingestion layer that produces a person-centric multiplex graph with time-scoped edges and confidence scores. It then constructs time slices and multilayer representations (multiplex and/or temporal multislice), computes baselines, runs community detection through *two method families*—(i) modularity maximization on multislice networks and (ii) probabilistic inference via SBMs (including degree correction and model selection)—and cross-compares them as an internal validation mechanism rather than treating either as ground truth. citeturn0search9turn6search11turn1search0turn12search0turn13search1

A dedicated robustness framework is specified as a *stability testing matrix* that maps each major algorithmic output to perturbation types (random and targeted edge/node removals, weight noise, layer-weight shifts, time-window shifts, and projection-null recalibration) and to diagnostic metrics (e.g., VI/ARI for clustering stability; rank correlation for brokerage/centrality stability; posterior predictive checks and information criteria/MDL for SBM adequacy). The matrix also highlights known instability modes: modularity’s resolution limit and degeneracy, Louvain-type partition connectivity pathologies, SBM misspecification under heavy-tailed degrees without degree correction, and temporal nonstationarity under arbitrary windowing. citeturn0search6turn1search16turn7search0turn1search0turn14search0turn2search2

Validation is defined narrowly as *structural validity under uncertainty*: (1) invariance/robustness to reasonable modeling perturbations, (2) internal consistency across complementary methods, (3) predictive adequacy where applicable (e.g., held-out edges or posterior predictive checks), and (4) auditability and provenance that allow independent reproduction and review. Validation explicitly excludes narrative plausibility, “high modularity = truth,” or agreement with metadata categories treated as ground truth without assessing metadata quality. citeturn1search16turn15search0turn14search3turn12search0

Finally, reproducibility and auditability are operationalized through a derived-entity schema and a “Method Run Record” template grounded in provenance standards and data stewardship principles: dataset hashing, immutable run records with seeds and parameter registries, and explicit lineage links among derived artifacts. citeturn18search3turn18search0turn18search2

## Unified pipeline architecture

### Pipeline diagram

The pipeline is organized around **immutable artifacts** (inputs, intermediate graphs, derived entities) and **stage gates** (checks that block progression when integrity or stability requirements fail). Multilayer and temporal modeling are treated as first-class representations rather than post-hoc add-ons, consistent with formal multilayer frameworks that extend adjacency-matrix thinking to tensor/multislice structures. citeturn6search1turn6search0turn0search5

**Conceptual data flow (text diagram):**

Evidence sources → Evidence normalization → Entity resolution → Event/edge extraction  
→ Person-centric evidence graph (multiplex, time-scoped, confidence-scored)  
→ Slice builder (time windows) + Layer builder (relationship types)  
→ Multilayer graph pack (multiplex + multislice couplings)  
→ Baseline structural metrics (per layer + aggregated)  
→ Community detection track A (multislice modularity)  
→ Community detection track B (SBM inference + model selection)  
→ Brokerage + mediation metrics (per layer, cross-layer, and aggregated)  
→ Iterative latent capability inference (network-driven iteration)  
→ Temporal evolution modeling (transitions, persistence, half-life)  
→ Stability/robustness harness (perturbations + sweeps)  
→ Derived entity store (outputs + provenance + diagnostics)  
→ Human review checkpoints → Export layer (reports, comparative dashboards)

### Stage-by-stage specification

The specifications below assume a person-centric multiplex system (people nodes as primary) with institutions/events as secondary nodes, and typed edges that are time-scoped and confidence-scored. This is consistent with treating multiplexity and time variation as core dimensions rather than noise. citeturn0search5turn6search1turn2search2

#### Evidence ingestion and normalization

**Inputs:** Raw evidence items (documents, filings, media, structured datasets), each with timestamps, source metadata, and extraction confidence.

**Transformations:** Parsing, canonicalization, de-duplication, source weighting, timestamp normalization. Confidence assignment distinguishes fact, allegation, and inference as separate *edge epistemic states* (not just weights).

**Outputs:** Normalized evidence objects; evidence metadata index.

**Parameter registry:** Source trust priors; extractor versions; timestamp resolution rules; confidence calibration mapping.

**Failure risks:** Timestamp ambiguity; source duplication; systematic extractor bias; confidence score drift across sources (risk of mixing incomparable scores).

#### Entity resolution and identity graph

**Inputs:** Normalized evidence objects with extracted mentions.

**Transformations:** Entity resolution (ER) to produce stable IDs for persons and institutions; creation of an identity graph and “same-as” assertions.

**Outputs:** Canonical entity table; identity linkage graph; ER uncertainty annotations.

**Parameter registry:** ER model version; match thresholds; blocking features; manual override log.

**Failure risks:** Over-merging (false identity collapse) or under-merging (splitting); identity drift over time; feedback loops where downstream network structure biases ER decisions.

#### Event/edge extraction and confidence-scored, time-scoped edge ledger

**Inputs:** Canonical entities, evidence objects, ER outputs.

**Transformations:** Convert evidence into typed edges with (start_time, end_time), directionality, weight, uncertainty, and epistemic status; store *edge ledger* as append-only.

**Outputs:** Edge ledger (immutable); edge provenance map linking each edge to evidence items.

**Parameter registry:** Edge typing ontology; time-window interpretation rules (instantaneous vs interval edges); directionality conventions; confidence computation.

**Failure risks:** Time-scope errors (e.g., end_time missing); conflating relation types; double-counting repeated mentions; incorrect directionality.

#### Person-centric multiplex graph construction

**Inputs:** Edge ledger; entity table.

**Transformations:** Build multiplex graph layers by relation type (e.g., employment, board membership, communication, co-attendance) and optionally bipartite subgraphs (person–institution, person–event). Multilayer representation should preserve layer identity as formal frameworks recommend; avoid premature aggregation at this stage. citeturn6search1turn0search5turn8search13

**Outputs:** Layered graphs (G_layer); bipartite subgraphs (G_bipartite); mapping tables.

**Parameter registry:** Layer definitions; inclusion thresholds; weight normalization per layer; treatment of directed/undirected edges.

**Failure risks:** Layer leakage through inconsistent typing; dominance artifacts from scale mismatch (one dense layer overwhelms others); loss of uncertainty metadata.

#### Time slicing and multislice coupling construction

**Inputs:** Layered graphs with time-scoped edges.

**Transformations:** Construct time windows (rolling or fixed), producing slices; define interslice couplings that tie each node to itself across adjacent time slices (or across multiple aspects), consistent with multislice modularity formalisms. citeturn0search2turn6search11turn6search10

**Outputs:** Multislice network package: {layers × time_slices, couplings}; slice metadata.

**Parameter registry:** Window length/step; coupling strength ω; per-slice resolution γ_s; boundary handling.

**Failure risks:** Window choice induces spurious transitions; coupling too strong forces artificial persistence; coupling too weak yields unstable switching; missingness varies across windows.

#### Baseline metrics (structural fingerprints)

**Inputs:** Multilayer graph package; optionally aggregated views.

**Transformations:** Compute per-layer and aggregated metrics: density, degree distributions, assortativity, clustering, centralities, core-periphery indicators. Metrics should be computed per slice and per layer, then summarized; multilayer theory cautions that naive single-layer generalizations can behave differently depending on choices. citeturn0search5turn6search0turn8search2

**Outputs:** Baseline metric store; per-slice fingerprints.

**Parameter registry:** Centrality definitions (weighted vs unweighted); path-cost rules for weighted shortest paths; normalization choices.

**Failure risks:** Betweenness and shortest-path-based measures are brittle under small weight/tie changes; scale differences across layers distort aggregated metrics. citeturn2search3turn3search4

#### Community detection track A: multislice modularity (exploratory structure)

**Inputs:** Multislice package (layers × time), coupling parameters.

**Transformations:** Optimize modularity (or related quality functions) per slice and across slices. Known issues include modularity’s resolution limit and degeneracy (many near-optimal partitions). Mitigate using parameter sweeps, multiple random restarts, and consensus/ensemble summarization. citeturn0search6turn1search16turn1search48turn0search2

**Outputs:** Partition sets (multiple runs); consensus partitions; per-community statistics (size, internal density, persistence).

**Parameter registry:** γ grid; ω grid; algorithm choice (e.g., Leiden vs Louvain); number of restarts; convergence criteria.

**Failure risks:** Resolution-limit merges small communities; high degeneracy leads to unstable meanings; Louvain can produce badly connected communities, motivating Leiden-like alternatives. citeturn0search6turn1search16turn7search0

#### Community detection track B: SBM inference (probabilistic structure)

**Inputs:** Per-slice graphs and/or multilayer graphs; choice of SBM family.

**Transformations:** Fit SBMs (ideally degree-corrected where degree heterogeneity is present) and select model complexity via Bayesian/MDL principles to reduce overfitting. Dynamic SBMs can explicitly model temporal evolution of block memberships. citeturn1search0turn12search0turn13search1turn12search3

**Outputs:** Posterior samples or MAP partitions; block interaction matrices; uncertainty measures; model selection diagnostics.

**Parameter registry:** SBM variant (DC-SBM, weighted SBM, hierarchical SBM); priors; inference method; seed; model selection criterion.

**Failure risks:** Misspecification (e.g., ignoring degree heterogeneity); over/underfitting in community count; poor fit detectable via posterior predictive checks. citeturn1search0turn12search0turn14search3

#### Brokerage computation (bridging, mediation, structural holes)

**Inputs:** Graphs + community assignments (from both tracks), per layer and per slice.

**Transformations:** Compute brokerage metrics (betweenness, flow-based measures, structural holes proxies such as constraint/effective size). Brokerage can be computed within and across communities and layers. Betweenness is defined via shortest paths and requires careful weight interpretation. citeturn2search3turn2search10turn3search4

**Outputs:** Broker score tables; rank lists; uncertainty under perturbations.

**Parameter registry:** Shortest-path weight transform; tie handling; normalization; whether to compute per layer vs multiplex paths.

**Failure risks:** Rank instability under minor perturbations; artifacts from disconnected components; layer dominance if computed on aggregated graph.

#### Iterative latent capability inference (network-driven iteration)

**Inputs:** Bipartite and/or projected graphs; per-slice matrices; optionally evidence weights.

**Transformations:** Apply iterative coupled-map procedures that infer latent “capabilities” or competitiveness-like scores from bipartite structure. Literature on economic complexity emphasizes that non-linear iterations can converge to fixed points but can also amplify small data errors, motivating noise-injection and convergence diagnostics. citeturn10search6turn10search1turn11search1

**Outputs:** Capability scores per person/institution; convergence traces; sensitivity statistics.

**Parameter registry:** Initialization; normalization; stopping criteria; handling of missing edges.

**Failure risks:** Sensitivity to missing/fictitious edges; slow or oscillatory convergence; spurious interpretability if treated as causal rather than structural proxy. citeturn11search1turn10search6

#### Temporal evolution modeling (persistence, transitions, half-life)

**Inputs:** Per-slice partitions (both tracks), broker scores, capability scores, baseline fingerprints.

**Transformations:** Track communities across windows; compute persistence and transition measures; quantify structural change. Temporal network work stresses time-respecting paths and the non-equivalence of static aggregation. citeturn2search2turn0search2

**Outputs:** Community lineage graphs; transition matrices; entropy-like descriptors; estimated “structural half-life” of communities/scores (defined operationally as time until similarity drops below a threshold).

**Parameter registry:** Matching method across slices (Hungarian by overlap, Jaccard, VI minimization); half-life threshold; smoothing choices.

**Failure risks:** Window artifacts; label switching; false merges/splits in tracking; nonstationarity.

#### Derived entity storage and publication

**Inputs:** All prior outputs + provenance.

**Transformations:** Persist derived artifacts as immutable records with full lineage; attach stability metrics and run metadata; expose for review.

**Outputs:** Derived entities; audit logs; export-ready datasets.

**Parameter registry:** Serialization version; hashing functions; access control.

**Failure risks:** Provenance loss; schema drift; inability to reproduce due to missing seeds or dependency versions.

### Derived entity schema

Power Atlas requires that each derived output (communities, centralities, broker ranks, capability scores, temporal transitions, projections) is stored as a **derived entity** with traceable lineage. This follows general provenance principles: provenance should capture entities, activities, agents, and derivations, enabling trust and reproducibility assessments. citeturn18search3

Below is a canonical **DerivedEntity** structure (conceptual JSON). It is designed to be content-addressable (hashable), immutable, and linkable.

```json
{
  "derived_entity_id": "de:sha256:<output_hash>",
  "type": "community_partition | sbm_fit | centrality_table | brokerage_table | capability_scores | temporal_transitions | projection_graph | multilayer_pack",
  "created_at_utc": "YYYY-MM-DDThh:mm:ssZ",

  "algorithm": {
    "name": "multislice_modularity | leiden | dc_sbm | dynamic_sbm | betweenness | constraint | fitness_complexity | ...",
    "implementation": "library/package name",
    "version": "semantic version or git commit",
    "random_seed": 123456789
  },

  "parameters": {
    "time_window": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "window_size_days": 90, "step_days": 30 },
    "layers": { "included": ["employment", "board", "coattendance"], "weights": { "employment": 1.0, "board": 0.7 }, "coupling": { "omega": 1.0 }, "resolution": { "gamma": 1.0 } },
    "projection": { "bipartite_mode": "person-institution", "projection_rule": "simple | weighted | validated", "null_model": "BiCM | hypergeometric", "p_value_threshold": 0.01 },
    "metric_defs": { "edge_weight_transform": "1/w | -log(w) | unweighted", "directed": true }
  },

  "input_signature": {
    "dataset_id": "ds:<id>",
    "dataset_hash": "sha256:<hash-of-raw-or-canonical-edge-ledger>",
    "entity_resolution_hash": "sha256:<hash-of-entity-table-and-er-links>",
    "code_environment": { "container_digest": "sha256:<...>", "os": "...", "python": "...", "deps_lockfile_hash": "sha256:<...>" }
  },

  "output_signature": {
    "output_hash": "sha256:<hash>",
    "output_format": "parquet | arrow | jsonl | graphml | ...",
    "row_count": 12345,
    "schema_version": "v1"
  },

  "stability": {
    "tests_run": ["edge_dropout_10pct", "layer_weight_sweep", "time_shift"],
    "metrics": {
      "community": { "VI_mean": 0.12, "ARI_mean": 0.84 },
      "rank": { "spearman_rho_mean": 0.88, "kendall_tau_mean": 0.74 },
      "sbm": { "ppc_pass_rate": 0.9, "mdl_delta": -1200 }
    },
    "notes": "free text"
  },

  "provenance_links": {
    "upstream_entities": ["de:sha256:<...>", "de:sha256:<...>"],
    "evidence_ledger_ref": "edge_ledger:sha256:<...>",
    "human_reviews": ["review:<id>"]
  }
}
```

Key design choice: the **dataset_hash** should refer to the *canonical edge ledger representation*, not just the raw source files, because it is the ledger that actually determines the graph. “Specificity and verifiability” expectations in data citation require fixity and version specificity to support later verification. citeturn18search2turn18search3

## Stability framework

### Core principle

Structural outputs in complex networks can be highly sensitive to modeling assumptions: community partitions can be non-unique and unstable (especially under modularity), and multilayer results can be dominated by a dense layer or by coupling choices. Therefore, robustness must be treated as a *first-class experimental product*, not an afterthought. citeturn1search16turn0search5turn6search1

The stability framework is implemented as a **harness** that can be invoked for any derived entity type, producing a standardized set of perturbation runs and diagnostics stored back into the derived entity record.

### Perturbation testing families

These perturbations are intentionally model-agnostic and can be applied across layers and time slices.

**Random edge removal (dropout):** Remove a fraction ε of edges (optionally stratified by edge type or confidence band). Tests whether outputs depend on a small set of edges.

**Targeted hub removal:** Remove or downweight high-degree or high-strength nodes/edges to test reliance on hubs (important in person–institution networks where institutions can create projection artifacts). citeturn8search13turn8search9

**Weight perturbation:** Add noise to edge weights; rescale weights; jitter within confidence intervals; test sensitivity of shortest-path-based measures.

**Layer weight shifts / layer ablations:** Multiply one layer’s weights by α ∈ [0, …] or remove the layer entirely to detect layer dominance artifacts (see validation section).

**Time-window perturbations:** Shift windows, change window length, change overlap, or use event-time jitter within plausible timestamp uncertainty to test temporal brittleness. Temporal network research emphasizes that aggregation can change reachable paths and inferred structure. citeturn2search2turn0search2

**Projection recalibration:** For bipartite projections, compare naive projection to statistically validated projections or maximum-entropy null projection to test projection bias. citeturn8search9turn9search1turn8search13

### Community stability metrics

Community stability is defined as similarity between partitions produced across perturbations, parameter sweeps, or reruns.

**Variation of Information (VI):** A metric distance between partitions; useful for comparing clusterings without assuming label alignment. citeturn3search0

**Adjusted Rand Index (ARI):** Agreement measure corrected for chance; widely used for clustering comparison. citeturn4search0

**Overlap metrics:** Jaccard overlap for matched communities, size-weighted overlap, and persistence scores for temporal tracking.

### Stability testing matrix

The matrix below specifies, for each major algorithmic component, the perturbations, diagnostics, acceptable variance guidance (conceptual, not universal), and known instability modes. Numerical ranges are “engineering thresholds” for experimental-phase gating; they should be tuned per dataset scale and sparsity. citeturn14search0turn2search2turn1search16

#### Bipartite projection and people–people derived edges

**Perturbations:** edge dropout; targeted removal of high-degree institutions; projection rule swap (naive vs validated); layer ablation.

**Diagnostics:** edge survival rate; change in degree distribution; stability of derived adjacency under projection method; downstream stability of communities/centralities.

**Acceptable variance guidance:** large changes under institution hub removal indicate projection bias; require that key structural conclusions (e.g., top brokers) persist under validated projection (rank correlation ≥ ~0.8).

**Known instability modes:** spurious co-membership edges driven by degree heterogeneity; projection creates dense cliques around hubs; mitigated by statistically validated projection or BiCM-type nulls. citeturn8search9turn9search1turn8search7

#### Multilayer packing and coupling (layers × time)

**Perturbations:** layer weight sweeps; coupling ω sweeps; layer drop-one-out; time-slice jitter.

**Diagnostics:** layer contribution ratios (share of total weight/edges per layer); sensitivity of node embeddings/centralities to ω; community persistence vs ω.

**Acceptable variance guidance:** detect “phase transitions” where small ω changes create radically different partitions; treat such regimes as unstable and require consensus across a stable ω band.

**Known instability modes:** layer dominance (dense layer overrides others); oversmoothing across time from high coupling; fragmentation from low coupling. citeturn0search2turn6search1turn0search5

#### Centrality and baseline structural metrics

**Perturbations:** weight noise; tie-breaking randomization; edge dropout; component isolation.

**Diagnostics:** rank correlation (Spearman/Kendall) of top-k nodes; distributional drift of centrality scores; component coverage.

**Acceptable variance guidance:** report top-k stability bands (e.g., top 20 stable at ≥80% membership across perturbations). For betweenness-like measures, expect higher sensitivity and require explicit uncertainty intervals.

**Known instability modes:** shortest-path tie sensitivity; disconnected graphs yield undefined or misleading path-based metrics; weighting choice changes path geometry. citeturn2search3turn3search4

#### Community detection track A (multislice modularity)

**Perturbations:** γ sweep; ω sweep; multiple random restarts; edge dropout; layer ablation.

**Diagnostics:** VI/ARI across runs; modularity score distribution; consensus clustering stability; connectivity checks of communities.

**Acceptable variance guidance:** require that consensus communities remain stable across a meaningful γ interval, not a single tuned value. Treat high modularity alone as insufficient evidence of structure.

**Known instability modes:** resolution limit (small communities merged); degeneracy (many near-optima); algorithm artifacts (Louvain can yield disconnected communities; prefer Leiden-like methods). citeturn0search6turn1search16turn7search0turn5search2

#### Community detection track B (SBM inference)

**Perturbations:** alternative SBM variants (degree-corrected vs not; weighted vs unweighted); prior sensitivity; edge dropout; posterior sampling variability; time-slice shifts.

**Diagnostics:** posterior predictive checks; model selection/MDL deltas; block count stability; uncertainty in assignments.

**Acceptable variance guidance:** reject SBM fits that systematically fail predictive checks on key descriptors (e.g., degree distribution, clustering, path lengths) (PPC failures indicate misspecification). Prefer models that minimize description length and avoid overfitting. citeturn12search0turn13search1turn14search3

**Known instability modes:** misspecification under heterogenous degrees without degree correction; overfitting community count; dynamic instability in temporal block assignments without temporal regularization. citeturn1search0turn12search3

#### Brokerage metrics

**Perturbations:** edge dropout; weight noise; alternative path-cost transform; recompute with/without specific layers.

**Diagnostics:** rank correlation and top-k overlap; sensitivity to shortest-path tie changes; stability conditional on community partitions (brokerage-within-community vs across).

**Acceptable variance guidance:** require rank stability for “headline brokers” under multiple plausible edge weight codings; otherwise mark broker status as unstable and require human review.

**Known instability modes:** betweenness sensitivity and computational scaling; constraint measures can change when ego networks change slightly; dense layers can create “shortcut inflation.” citeturn2search3turn2search10

#### Capability iteration stability

**Perturbations:** initialization sweeps; noise injection into bipartite matrix; edge missingness simulation; time-slice shifts.

**Diagnostics:** convergence rate; fixed-point uniqueness; sensitivity to small errors (local perturbation amplification); stability of rank ordering.

**Acceptable variance guidance:** require convergence to consistent ordering across initializations; if results change materially under minor noise, treat capability scores as exploratory only.

**Known instability modes:** nonlinear iterations can propagate small data errors; sensitivity to missing flows/edges is explicitly noted in empirical analyses of such approaches. citeturn11search1turn10search1turn10search6

#### Temporal evolution modeling

**Perturbations:** window size/step sweeps; timestamp jitter; matching rule alternatives.

**Diagnostics:** persistence curves; transition entropy; half-life estimates with confidence intervals (bootstrap over windows).

**Acceptable variance guidance:** report half-life as a range, not a point; require that qualitative temporal conclusions persist across reasonable window choices.

**Known instability modes:** aggregation bias (static views misrepresent time-respecting connectivity); label switching; windowing artifacts. citeturn2search2turn0search2

## Validation philosophy

### What constitutes validation in structural network modeling

Validation for Power Atlas should be defined as **evidence that derived structure reflects stable properties of the modeled system under explicit assumptions**, rather than artifacts of a single modeling choice. This includes:

**Robustness validation:** outputs remain meaningfully similar under perturbations and parameter sweeps (as specified in the stability matrix). For community detection, this directly addresses degeneracy and resolution effects. citeturn1search16turn0search6

**Cross-method triangulation:** compare partitions and role assignments from modularity-based methods with SBM-based inferences; persistent agreement across method families increases confidence, while systematic divergence is a diagnostic that assumptions are driving results. Modularity and SBM approaches optimize different objective functions and have distinct failure modes. citeturn5search2turn12search0turn1search0

**Probabilistic adequacy:** for SBMs, use posterior predictive model checking and model selection principles (Bayesian or MDL) to determine if inferred structure explains observed network features without overfitting. citeturn13search1turn12search0turn14search3

**Temporal validity:** if the system is time-varying, validate that temporal conclusions are not window artifacts, consistent with temporal network cautions about aggregation. citeturn2search2turn0search2

**Auditability:** every derived claim can be traced to a reproducible run and to specific evidence edges with time scope and epistemic status. Provenance models explicitly aim to support trust judgments about reliability and quality. citeturn18search3

### What is not validation

**High modularity is not validation.** Modularity can exhibit resolution limits and can produce many near-optimal, meaningfully different partitions; therefore a single “best modularity” partition should not be treated as the true structure. citeturn0search6turn1search16turn1search48

**Agreement with metadata labels is not validation unless metadata quality is assessed.** Metadata categories may be incomplete, inaccurate, or only indirectly related to structural communities; principled approaches treat metadata as potentially informative but not ground truth. citeturn15search0turn15search6

**Narrative plausibility is not validation.** A cluster that “looks right” can still be an artifact of layer weighting, projection bias, or windowing.

### Overfitting to layer definitions, time windows, and weighting schemes

Structural models can overfit when they mirror modeling design choices rather than underlying structure.

**Layer overfitting:** arises when one layer dominates the objective function (e.g., densest layer drives communities). Multilayer reviews emphasize that layer definitions are modeling decisions and should be tested for sensitivity. citeturn0search5turn6search1

**Time-window overfitting:** occurs when window sizes are tuned until desired patterns appear; temporal network work warns that aggregation changes reachable paths and therefore inferred structure. citeturn2search2turn0search2

**Algorithmic over/underfitting in community detection:** different methods can systematically overfit or underfit; evaluation work stresses that no method is universally best and that overfitting behavior can be diagnosed. citeturn14search0

### Detecting layer dominance artifacts

Layer dominance should be treated as an observable diagnostic, not an anecdotal concern.

**Recommended diagnostics:**
- **Objective contribution accounting:** compute share of modularity gain or likelihood contribution attributable to each layer/time slice under current parameters (report as percentages).
- **Layer ablation tests:** rerun communities and broker rankings with one layer removed; large changes identify dependence on that layer.
- **Layer weight sweep stability band:** identify parameter regions where outputs are stable vs unstable (phase transition behavior). This is consistent with multilayer sensitivity considerations. citeturn0search5turn0search2

### Detecting projection bias in bipartite graphs

Bipartite projection is well-known to generate spurious edges due to degree heterogeneity in the bipartite sets; this is especially acute in person–institution networks where large institutions create dense co-membership cliques. Research on two-mode networks and on statistically validated projections emphasizes the need for null-model-based validation. citeturn8search13turn8search9turn9search1

**Recommended approach:**
- Treat projection as *one hypothesis* of person–person association.
- Validate projected edges against a bipartite null (e.g., statistically validated networks or maximum-entropy bipartite configuration models).
- Maintain projected edges with a provenance tag indicating projection method and null model, plus a confidence/p-value field.

Statistically validated projections explicitly aim to distinguish edges reflecting genuine association from edges reflecting heterogeneity. citeturn8search7turn8search9turn9search1

## Reproducibility standards

### Design standards

Power Atlas should implement reproducibility as architecture, not policy. The following standards should be non-optional for experimental runs:

**Parameter logging as first-class data:** Every stage emits a parameter registry and random seeds. This is essential because community detection and some inference routines are stochastic and can show nontrivial variability. citeturn1search16turn7search0

**Dataset hashing and fixity:** Hash the canonical edge ledger and the resolved entity table used to build graphs; store these hashes in each derived entity record. Data citation principles emphasize specificity, verifiability, and fixity metadata to enable later verification. citeturn18search2turn18search3

**Snapshot versioning:** Immutable dataset snapshots (edge ledger + entity table + ontologies). Avoid “mutable latest” semantics for any analysis-critical artifact.

**Lineage tracking:** Implement provenance using a PROV-style model of entities, activities, agents, and derivations; store provenance links between derived entities. PROV-DM explicitly frames provenance in these terms. citeturn18search3

**FAIR-aligned metadata:** Ensure outputs and datasets are findable and reusable through machine-actionable metadata, consistent with FAIR principles. citeturn18search0

### Human review checkpoints

Human-in-the-loop oversight should be formalized as gated “review points” that produce review artifacts linked in provenance.

**Recommended checkpoints:**
- **After entity resolution:** review high-impact merges/splits (nodes with high degree or centrality potential).
- **After layer definitions frozen for a run:** review layer ontology and edge typing distribution.
- **After community/role inference:** review stability results first; only then review substantive interpretations.
- **Before publishing a derived entity as “reportable”:** require passing minimal stability thresholds (or explicitly label as unstable/exploratory).

### Method run record template

A minimal “Method Run Record” should be stored for *every* run and linked to all derived entities.

```yaml
run_id: "run:YYYYMMDD:<uuid>"
created_at_utc: "YYYY-MM-DDThh:mm:ssZ"

dataset:
  dataset_id: "ds:<id>"
  dataset_hash: "sha256:<hash>"
  entity_table_hash: "sha256:<hash>"
  edge_ledger_hash: "sha256:<hash>"
  time_window: { start: "YYYY-MM-DD", end: "YYYY-MM-DD", window_days: 90, step_days: 30 }

graph_configuration:
  layers_included: ["..."]
  layer_weights: { layerA: 1.0, layerB: 0.5 }
  coupling: { omega: 1.0 }
  directed: true
  weight_transform: "1/w"

algorithm:
  name: "leiden_multislice | dc_sbm | dynamic_sbm | ..."
  implementation: "library/package"
  version: "semver or commit"
  random_seed: 123456

parameters:
  gamma: 1.0
  sbm_variant: "degree_corrected"
  priors: "..."
  convergence_criteria: "..."

stability:
  tests_run: ["edge_dropout_0.1", "layer_ablation", "time_shift_30d"]
  key_metrics:
    community: { VI_mean: 0.12, ARI_mean: 0.84 }
    rank: { spearman_rho_mean: 0.88 }
    sbm_ppc: { pass_rate: 0.9 }
  anomalies: ["...free text..."]

outputs:
  derived_entities: ["de:sha256:<...>", "de:sha256:<...>"]
  output_hashes: ["sha256:<...>"]

human_review:
  required: true
  review_ids: ["review:<id>"]
  notes: "..."
```

## Failure mode catalogue

This catalogue is structured to support (a) detection signals that can be automated and (b) mitigations that can be encoded into pipeline guards.

### Mathematical failure modes

**Modularity resolution limit**
- **Mechanism:** modularity optimization can fail to detect communities below a scale dependent on network size and interconnection. citeturn0search6
- **Detection:** small, dense groups disappear as graph grows or as γ shifts slightly; instability in community count with size.
- **Mitigation:** multi-resolution sweeps; complement with SBM inference; avoid single “best” partition.

**Modularity degeneracy / non-uniqueness**
- **Mechanism:** many distinct partitions can have near-identical modularity scores. citeturn1search16turn1search48
- **Detection:** high variance of partitions across restarts with similar Q.
- **Mitigation:** ensemble/consensus clustering; report partition uncertainty; treat consensus as the object, not a single run.

**Partition connectivity pathologies in heuristics**
- **Mechanism:** Louvain-type heuristics can produce badly connected or even disconnected communities. citeturn7search0
- **Detection:** per-community connectivity checks fail.
- **Mitigation:** prefer Leiden-like optimization with connectivity guarantees; enforce connectivity validation gate.

**SBM degree misspecification**
- **Mechanism:** basic SBMs ignore degree heterogeneity; degree-corrected variants address this. citeturn1search0
- **Detection:** posterior predictive mismatch on degree distributions; unstable blocks.
- **Mitigation:** use degree-corrected/weighted SBMs where appropriate; apply PPC gates. citeturn14search3turn12search0

**Temporal aggregation bias**
- **Mechanism:** aggregating temporal edges into static graphs changes reachability and the meaning of paths. citeturn2search2
- **Detection:** strong dependence of findings on windowing; inconsistent temporal paths.
- **Mitigation:** keep time-scoped edges; validate across multiple window scales; prefer time-respecting metrics when needed.

**Bipartite projection bias**
- **Mechanism:** projection can create spurious edges due to heterogeneity in bipartite degrees. citeturn8search9turn8search13
- **Detection:** projected edges correlate strongly with institution degree; large changes when hubs removed.
- **Mitigation:** null-model validated projection; store projection provenance and p-values. citeturn9search1turn8search7

**Shortest-path sensitivity in brokerage**
- **Mechanism:** betweenness depends on shortest paths; small weight changes can reroute many paths. citeturn2search3turn3search4
- **Detection:** broker ranks unstable under small perturbations.
- **Mitigation:** report stability bands; use alternative flow-based metrics; avoid overinterpreting single-rank differences.

**Nonlinear iteration sensitivity in capability inference**
- **Mechanism:** iterative, nonlinear maps can amplify small data errors; convergence can be sensitive to missing/fictitious edges. citeturn11search1turn10search1
- **Detection:** rank ordering changes under small noise; slow/oscillatory convergence.
- **Mitigation:** convergence and noise-injection tests; treat as exploratory when unstable; require human review.

### Architectural failure modes

**Provenance loss or partial logging**
- **Mechanism:** derived outputs stored without full parameter and dataset signature; cannot reproduce.
- **Detection:** missing hashes/seeds/versions; orphan derived entities.
- **Mitigation:** enforce schema validation; reject writes without required provenance fields. citeturn18search3

**Schema drift across experimental iterations**
- **Mechanism:** layer ontology or edge typing changes without versioning; results incomparable.
- **Detection:** layer IDs reused with different semantics; inconsistent counts.
- **Mitigation:** versioned ontologies; migration scripts; explicit schema_version fields.

**Entity identity instability**
- **Mechanism:** entity resolution changes alter node identities; derived trends become meaningless.
- **Detection:** large changes in entity merges; “ID churn” across runs.
- **Mitigation:** stage-gate ER; track ER hash; require revalidation when ER changes.

**Confidence score incoherence**
- **Mechanism:** different extractors produce incomparable confidence scales.
- **Detection:** layer-specific confidence distributions non-comparable; downstream weighting dominated by one extractor.
- **Mitigation:** calibration layer; store confidence provenance; stratified analyses by epistemic status.

### Data bias amplification risks

**Visibility bias / missing data**
- **Mechanism:** edges exist only for observable events; under-observed actors appear peripheral.
- **Detection:** network coverage correlates with source visibility; sudden appearance/disappearance patterns.
- **Mitigation:** incorporate missingness modeling; report coverage metrics; avoid interpreting absence as non-relationship.

**Survivorship and historical bias**
- **Mechanism:** entities persist in records unevenly across time; temporal slices become incomparable.
- **Detection:** older windows much sparser; changing source mixing.
- **Mitigation:** normalize by coverage; compare within time bands; log source composition per slice.

### Over-interpretation hazards

**Causal narratives from structural proxies**
- **Mechanism:** treating centrality or community membership as causal influence.
- **Detection:** claims not supported by evidence layer; mismatch between epistemic status and narrative strength.
- **Mitigation:** enforce “structural claim taxonomy” in reporting; require evidence link-outs for any causal phrasing.

**Community ≠ organization**
- **Mechanism:** communities reflect connectivity patterns; not necessarily real groups.
- **Detection:** communities unstable; low internal cohesion.
- **Mitigation:** require stability and cohesion diagnostics; treat as hypotheses.

### Visualization-induced misinterpretation

**Hairball graphs and salience bias**
- **Mechanism:** dense visuals overemphasize hubs and hide uncertainty.
- **Detection:** stakeholder interpretations depend on layout; confusion about edge meaning.
- **Mitigation:** default to summary visuals (rank bands, stability plots, block matrices); always show uncertainty overlays; include provenance access paths.

## Open research questions

Robust experimental architecture depends on unresolved design choices that should be treated as research tasks with explicit acceptance criteria.

**Confidence semantics and calibration:** How should “fact vs allegation vs inference” propagate through derived metrics (e.g., should allegations ever create projected edges, or only influence priors)? Provenance and uncertainty need to be machine-actionable to support trust decisions. citeturn18search3turn18search2

**Layer coupling theory-to-practice mapping:** How should ω and layer weights be chosen in a principled way for person-centric multiplex graphs, especially when layers differ drastically in density? Multilayer reviews emphasize that these choices affect outcomes and require sensitivity analysis. citeturn0search5turn6search1

**Consensus representations:** What is the canonical “output” of community detection in an evidence-first system—single partition, ensemble, or posterior distribution? Modularity degeneracy and SBM uncertainty both argue for distributional outputs. citeturn1search16turn12search0

**Dynamic structure modeling:** When should temporal dynamics be modeled via multislice modularity vs dynamic SBMs vs hybrid approaches, and what stability diagnostics best detect temporal overfitting? citeturn0search2turn12search3

**Projection alternatives:** For person–institution data, should the system avoid projection entirely by using bipartite-aware models, validated projections, or higher-order representations? Null-model projection work suggests substantial gains from validated approaches. citeturn8search9turn9search1turn8search13

**Fit testing at scale:** How should posterior predictive checks and goodness-of-fit diagnostics be operationalized as automated gates for SBM outputs, especially when the SBM fits most but not all descriptors? Systematic fit-assessment work emphasizes using multiple descriptors to detect inadequacy. citeturn14search3turn12search0

**Human review ergonomics:** What UI/UX and workflow patterns enable reviewers to audit derived entities efficiently (provenance traces, perturbation summaries, and “why this edge exists” explanations) without overwhelming cognitive load? Provenance standards define what to capture; system design must define how to present it. citeturn18search3