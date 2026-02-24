# Brokerage and Latent Capability Inference for Power Atlas

## Executive summary

Power Atlas (experimental phase) needs two complementary families of network methods that can be implemented in a time-aware, evidence-first, source-attributed stack:

Brokerage metrics aim to quantify *structural position as an intermediary*—who sits on “between” paths or bridges otherwise weakly connected regions of a graph. In the classical lineage (weak ties / bridging intuition; centrality and shortest-path accounting), the workhorse is **betweenness centrality**: a node’s share of shortest paths between other node pairs. In practice, betweenness is powerful but brittle: it is discontinuous under small edge-weight changes (because the identity of shortest paths can flip), strongly affected by windowing in temporal graphs, and vulnerable to sampling bias. A second brokerage lens—**structural holes**—frames brokerage as *redundancy vs. non-redundancy* in an ego network. The canonical operationalization is **constraint**, which penalizes actors whose neighbors are themselves interconnected (high redundancy) and rewards actors spanning sparse, disconnected neighborhoods (low redundancy). Together, betweenness (global, path-based) and constraint (local-ish, redundancy-based) give two distinct, implementable cuts at “bridging.”

Latent capability inference (inspired by economic complexity methods associated with the country–product bipartite setting) aims to infer *unobserved capability* from relational participation patterns. The **fitness–complexity** family of algorithms defines a nonlinear, iterative scoring system on a bipartite matrix: one side’s score rises with diversified participation in “complex/selective” entities; the other side’s complexity is limited by the least-fit participants (a “weakest link” logic). This nonlinearity is the key methodological difference from eigenvector-style centralities: it is not merely “being connected to high-score neighbors,” but “being connected to entities that are not broadly accessible to low-score nodes.”

For Power Atlas, the architectural challenge is less the mathematics than *robustness and provenance*: both brokerage and capability scores must be treated as **derived entities** parameterized by (i) graph construction rules, (ii) time scope, (iii) confidence/evidence weighting, and (iv) algorithmic settings (normalization, stopping criteria, approximation regime). The system should store not only point estimates but also *uncertainty surfaces*: distributions over scores under perturbations (edge removal, weight jitter, alternate time windows), plus diagnostics (stability, convergence, and sensitivity markers).

Comparatively, brokerage and capability measure different “axes” of structure. Brokerage is primarily about *intermediation* (position on connecting paths), while capability is about *selective participation patterns* (compatibility with complex entities). They can disagree systematically: a node can bridge communities (high brokerage) without exhibiting selective capability patterns (low capability), or can sit inside a dense elite cluster (high capability) without serving as a bridge (low brokerage). In multilayer settings, the disagreement is often amplified: cross-layer connectors may look like brokers even when their within-layer capability is modest; conversely, high within-layer capability can be invisible to brokerage if the layer is internally dense and redundant.

Because Power Atlas is evidence-first and time-aware, the recommended strategy is to implement both families as **versioned computation modules** over a standardized person-centric multiplex graph and a standardized set of bipartite projections, then add a robust evaluation harness: perturbation tests, window-sensitivity sweeps, and Monte Carlo sampling over edge existence probabilities driven by evidence confidence.

## Formal mathematics

### Notation

Let a (possibly directed) weighted graph be \(G=(V,E,w)\), \(n=|V|\). For an edge \(e=(u,v)\), let \(w_{uv}\) be its weight. When weights represent *cost/distance* for shortest paths, we use \(d_{uv}\ge 0\). When weights represent *strength/affinity*, we typically map them to distances via a monotone transform (discussed later).

For time-aware modeling, let each edge carry a validity interval \([t_\text{start},t_\text{end})\) (or event time \(t\)) and possibly time-varying weight \(w_{uv}(t)\). For discrete snapshots, let \(G^{(k)}\) be the graph induced by a time window \(W_k\).

For multiplex graphs, let layers be \(\mathcal{L}=\{1,\dots,L\}\). A multiplex can be represented as layer-specific graphs \(G_\ell=(V,E_\ell,w_\ell)\) plus *interlayer coupling* (e.g., “same person across layers” links).

### Betweenness centrality

#### Standard definition (shortest-path fraction)

Let \(\sigma_{st}\) be the number of shortest paths between distinct nodes \(s\) and \(t\). Let \(\sigma_{st}(v)\) be the number of those shortest paths that pass through node \(v\) (with \(v\ne s,t\)). The **betweenness centrality** of node \(v\) is

\[
C_B(v)=\sum_{\substack{s\ne v\ne t\\ s\ne t}} \frac{\sigma_{st}(v)}{\sigma_{st}}.
\]

A common normalization (undirected) divides by \(\frac{(n-1)(n-2)}{2}\); for directed graphs, by \((n-1)(n-2)\). This puts \(C_B(v)\) roughly in \([0,1]\) for comparability across \(n\) (exact bounds depend on graph class).

This definition is classically attributed to entity["people","Linton C. Freeman","social network analyst"] (betweenness as a shortest-path mediation count), and is presented in standard network texts (e.g., the centrality chapters in *Networks: An Introduction*).

#### Weighted betweenness

Weighted betweenness uses shortest paths computed with respect to an edge-length function \(d_{uv}\). If the stored weight \(w_{uv}\) already represents a distance/cost, set \(d_{uv}=w_{uv}\). If \(w_{uv}\) represents tie strength (larger = “closer”), choose a monotone decreasing map such as:

- \(d_{uv} = 1 / (w_{uv}+\epsilon)\) (with small \(\epsilon>0\)),
- \(d_{uv} = -\log(\tilde{w}_{uv})\) if \(\tilde{w}_{uv}\in(0,1]\) is a normalized strength,
- \(d_{uv} = w_{\max}-w_{uv}\) when weights are bounded and linear reversal is defensible.

Then compute \(\sigma_{st}\) and \(\sigma_{st}(v)\) over shortest paths under distances \(d\), yielding the same summation formula.

**Key modeling warning:** the distance transform is not innocuous—it changes what “between” means. In an evidence-first architecture, the transform must be treated as an explicit, versioned parameter of the derived metric.

#### Temporal betweenness (time-respecting paths)

If edges have time stamps and traversal must respect time order, define a **time-respecting path** \(s \rightarrow \cdots \rightarrow t\) as a sequence of temporal edges with nondecreasing times (and possibly bounded waiting times). Let \(\sigma_{st}^\text{temp}\) count shortest *arrival-time* (or fastest) time-respecting paths; define:

\[
C_B^\text{temp}(v)=\sum_{s\ne v\ne t}\frac{\sigma_{st}^\text{temp}(v)}{\sigma_{st}^\text{temp}}.
\]

This is often implemented by time-expanding the graph (creating node-time copies) or by snapshot approximations (compute \(C_B\) per window and summarize).

### Structural holes and constraint

Structural holes operationalize brokerage as *low redundancy* in an ego network. Let \(i\) be the focal node. Define \(p_{ij}\) as the proportion of \(i\)’s relational investment in neighbor \(j\). In weighted graphs, a typical choice is

\[
p_{ij}=\frac{w_{ij}}{\sum_{k\in N(i)} w_{ik}}
\quad\text{(with }p_{ij}=0\text{ if }j\notin N(i)\text{)}.
\]

The **constraint** of \(i\) (canonical form associated with entity["people","Ronald Burt","structural holes theorist"] and presented in entity["book","Structural Holes","burt 1992"]) is

\[
\text{Constraint}(i)=\sum_{j\in N(i)} \left(p_{ij} + \sum_{q\in N(i)} p_{iq}p_{qj}\right)^2.
\]

Interpretation:

- \(p_{ij}\) is the direct dependence of \(i\) on \(j\).
- \(\sum_{q} p_{iq}p_{qj}\) is indirect dependence: \(i\) depends on \(j\) through \(q\) if \(i\) invests in \(q\) and \(q\) is linked to \(j\).
- Squaring emphasizes concentration: constraint rises when dependence is focused into a few, mutually redundant contacts.

Low constraint suggests brokerage capacity (spanning disconnected alters); high constraint suggests redundancy/closure.

**Time-aware extension:** compute constraint on \(G^{(k)}\) per time window, or define \(p_{ij}(t)\) using decayed weights (e.g., exponential decay) so that recent interactions dominate.

### Cross-layer brokerage candidate formalizations

Power Atlas requires brokerage that can be computed (a) within layers and (b) across layers in a coherent, implementable way. Below are three candidate formalizations that are explicit about what counts as a “path” in a multiplex.

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["betweenness centrality network diagram","structural holes brokerage diagram","multiplex network layers diagram"],"num_per_query":1}

#### Layerwise brokerage with cross-layer aggregation

Compute a brokerage metric \(B_\ell(v)\) (e.g., betweenness or 1–constraint) on each layer graph \(G_\ell\). Then aggregate:

\[
B_\text{agg}(v)=\sum_{\ell=1}^L \alpha_\ell B_\ell(v),
\]

where \(\alpha_\ell\) are layer importance weights (fixed, learned, or evidence-driven).

To make it explicitly cross-layer, compute dispersion across layers, e.g. entropy of normalized layer contributions:

\[
H(v) = -\sum_\ell \pi_\ell(v)\log \pi_\ell(v),
\quad \pi_\ell(v) = \frac{B_\ell(v)}{\sum_m B_m(v)}.
\]

Then define a “cross-layer broker” score \(B_\text{cross}(v)=B_\text{agg}(v)\cdot H(v)\), which rewards brokerage distributed across layers rather than concentrated in one.

This formalization is easy to implement and aligns with modular experimentation, but it does **not** define brokerage on genuinely cross-layer paths; it is an aggregation of within-layer roles.

#### Supra-graph betweenness (explicit interlayer traversal)

Construct a **supra-graph** \(G^\*\) whose node set is \(V^\*=\{(v,\ell): v\in V,\ell\in\mathcal{L}\}\). Within each layer \(\ell\), include edges \(((u,\ell),(v,\ell))\) with distance \(d^\*_{(u,\ell)(v,\ell)}=d^{(\ell)}_{uv}\). Add **interlayer coupling** edges \(((v,\ell),(v,m))\) representing switching layers for the same person, with “layer-switch cost” \(\lambda_{\ell m}\ge 0\). Then compute standard weighted betweenness on \(G^\*\):

\[
C_B^\*((v,\ell))=\sum_{(s,a)\ne (v,\ell)\ne (t,b)} \frac{\sigma_{(s,a)(t,b)}((v,\ell))}{\sigma_{(s,a)(t,b)}}.
\]

Aggregate back to persons:

\[
C_B^\text{supra}(v)=\sum_{\ell} C_B^\*((v,\ell)).
\]

Now you can define **within-layer betweenness** (restrict pairs to same layer \(a=b\)) versus **cross-layer betweenness** (pairs with \(a\ne b\)), enabling a principled answer to “brokerage across layers.”

This is the cleanest formal bridge between multiplex structure and shortest-path brokerage, at the cost of increased graph size by a factor of \(L\).

#### Layer-constrained or layer-typed path brokerage

If “layer switching” is semantically constrained (e.g., you only want paths that traverse a specific sequence of relation types), define a path language \(\mathcal{P}\) over layers, such as:

- allow at most one layer switch,
- disallow certain switches,
- require that paths include at least one edge of a given layer type.

Then define \(\sigma_{st}^{\mathcal{P}}\) as the number of shortest admissible paths under those constraints and compute:

\[
C_B^{\mathcal{P}}(v)=\sum_{s\ne v\ne t}\frac{\sigma_{st}^{\mathcal{P}}(v)}{\sigma_{st}^{\mathcal{P}}}.
\]

This matches evidence-first modeling well: the admissible path rule is an explicit hypothesis about how influence or resources move across relation types.

### Fitness–complexity style latent capability inference

#### Bipartite matrix representation

Let \(P\) be a set of persons and \(I\) a set of institutions (or communities, roles, layer-participation units). Build a nonnegative bipartite matrix \(M\in\mathbb{R}_{\ge 0}^{|P|\times |I|}\) where \(M_{pi}\) encodes whether and how strongly person \(p\) participates in institution \(i\) during a time scope \(W\).

Common choices:

- Binary: \(M_{pi}\in\{0,1\}\) after thresholding.
- Weighted: \(M_{pi}\) proportional to duration, intensity, or evidence-weighted confidence.
- Confidence-marginalized: \(M_{pi}\) is expected connectivity under edge existence probabilities.

#### Iterative update equations

A standard fitness–complexity update (nonlinear) proceeds with two score vectors:

- \(F^{(n)}\in\mathbb{R}_{>0}^{|P|}\): person “fitness” (latent capability proxy),
- \(Q^{(n)}\in\mathbb{R}_{>0}^{|I|}\): institution “complexity/selectivity.”

Initialize \(F^{(0)}=\mathbf{1}\), \(Q^{(0)}=\mathbf{1}\) (or other positive vectors). Iterate:

\[
\tilde{F}^{(n)}_p = \sum_{i} M_{pi}\, Q^{(n-1)}_i,
\]

\[
\tilde{Q}^{(n)}_i = \left(\sum_{p} M_{pi}\, \frac{1}{F^{(n-1)}_p}\right)^{-1}.
\]

Then normalize (scale control) with, for example, mean normalization:

\[
F^{(n)} = \frac{\tilde{F}^{(n)}}{\frac{1}{|P|}\sum_{p}\tilde{F}^{(n)}_p},
\quad
Q^{(n)} = \frac{\tilde{Q}^{(n)}}{\frac{1}{|I|}\sum_{i}\tilde{Q}^{(n)}_i}.
\]

Intuition:

- A person’s score rises with diversified access to complex/selective institutions.
- An institution’s complexity is high only if it is not “easily accessible” to low-fitness persons (harmonic-mean-like penalty), embodying a “weakest participant” limiting effect.

This family is associated with entity["people","Andrea Tacchella","fitness complexity researcher"] and is closely related (methodologically and historically) to the economic complexity program popularized by entity["people","César Hidalgo","economic complexity researcher"] and collaborators; Power Atlas can adopt the algorithmic template while keeping interpretation purely structural.

#### Convergence and fixed points

The mapping \((F,Q)\mapsto (F',Q')\) is nonlinear. In many empirical bipartite matrices it converges to a stable fixed point after normalization, but convergence is not guaranteed under all pathological matrices (e.g., disconnected components, extreme sparsity, or rows/columns with near-zero support). In an experimental architecture, convergence must be treated as a *measured property* (diagnosed and logged) rather than assumed.

A practical convergence condition is based on relative change:

\[
\Delta_F^{(n)} = \frac{\|F^{(n)}-F^{(n-1)}\|_1}{\|F^{(n-1)}\|_1},
\quad
\Delta_Q^{(n)} = \frac{\|Q^{(n)}-Q^{(n-1)}\|_1}{\|Q^{(n-1)}\|_1},
\]

stop when both are \(<\varepsilon\) for some tolerance \(\varepsilon\), or when a maximum iteration count is reached.

#### How this differs from eigenvector centrality

Eigenvector centrality and related spectral methods solve (or approximate) a linear fixed-point equation like \(x \propto A x\). Fitness–complexity uses **reciprocal dependence** on the inverse fitness of participants, making it:

- nonlinear,
- more sensitive to “ubiquity” (institutions connected to many low-score persons become low complexity),
- less reducible to a single leading eigenvector interpretation.

Power Atlas implication: capability inference is not a generic “centrality” measure; it embeds a specific hypothesis that selectivity is limited by low-capability participation.

## Implementation design

### Person-centric multiplex graph representation

A minimal implementable data model (conceptual schema) that respects evidence-first and time-awareness:

- **Person node**
  - `person_id` (stable internal identifier)
  - optional attributes (not used in computation unless explicitly modeled)

- **Layer**
  - `layer_id`
  - `layer_semantics` (relation type: employment, collaboration, membership, communication, …)
  - `directionality` and default weight interpretation

- **Edge event / edge interval**
  - `u_person_id`, `v_person_id`
  - `layer_id`
  - `t_start`, `t_end` (or `t_event`)
  - `weight_raw`
  - `weight_kind` (strength vs cost)
  - `confidence` (0–1, evidence-derived)
  - `evidence_refs[]` (pointers to sources; in Power Atlas this is a first-class provenance object)
  - `edge_id`, `graph_build_id`

This enables snapshotting, decayed weighting, and Monte Carlo sampling over edges using `confidence` as an inclusion probability (or as parameters to a noise model).

### Brokerage computation pipeline

#### Preprocessing

1. **Time scoping**
   - Choose window rule \(W=[t_0,t_1)\) or sliding windows \(W_k\).
   - Decide inclusion policy: include edges active at any time in \(W\), or integrate weights over overlap with \(W\).
   - Optional: apply time decay \(w_{uv} \leftarrow \int_W w_{uv}(t)\, \exp(-\gamma(t_1-t))\,dt\).

2. **Confidence handling (evidence-first)**
   - Option A (deterministic): set \(w\leftarrow w\cdot \text{confidence}\).
   - Option B (probabilistic ensemble): sample graphs \(G^{(b)}\) by including each edge with probability \(p=\text{confidence}\), compute metrics, store distributions.

3. **Weight-to-distance mapping (for betweenness)**
   - Store transform choice explicitly, e.g. `distance_transform = inv(w+eps)`.

4. **Multiplex construction (if cross-layer brokerage)**
   - Layerwise computation: build \(G_\ell\) per layer.
   - Supra-graph: build node copies \((v,\ell)\) and interlayer edges with switching penalty \(\lambda\).

#### Computation

- **Betweenness**
  - Exact all-pairs shortest-path betweenness is expensive; the standard practical route is the algorithm associated with entity["people","Ulrik Brandes","network scientist"], which computes betweenness in \(O(|V||E|)\) for unweighted graphs and roughly \(O(|V||E| + |V|^2\log |V|)\) for weighted graphs using Dijkstra-like routines (exact terms depend on priority-queue model and graph density).
  - For supra-graphs, replace \(|V|\) by \(|V^\*|=|V|L\) and \(|E|\) by \(|E^\*|\approx \sum_\ell |E_\ell| +\) interlayer edges. Complexity grows quickly with \(L\), motivating approximations.

- **Constraint**
  - Constraint can be computed from local neighborhoods and (optionally) 2-hop terms. If adjacency lists are available, it is typically far cheaper than betweenness and scales with local degree and neighbor overlaps.

#### Approximation regimes (recommended for experimentation)

- **Node-pair sampling betweenness**: approximate \(C_B(v)\) by sampling sources \(s\) (or pairs \((s,t)\)) and accumulating dependency scores; log the sampling seed and error estimates.
- **Ego-centric “bridging proxies”**: use constraint, effective size, or bridging coefficients as faster stand-ins where full betweenness is too costly, especially in dense layers.

### Capability inference computation pipeline

#### Data schema requirements for person–institution bipartite graphs

Define an edge table (time-aware, evidence-first):

- `person_id`, `institution_id`
- `t_start`, `t_end` (or events)
- `weight_raw` (participation intensity)
- `confidence`
- `evidence_refs[]`
- `edge_id`, `graph_build_id`

From this, build \(M\) for each time scope \(W\):

- Binary \(M_{pi}=1\) if participation exceeds threshold within \(W\).
- Weighted \(M_{pi}=\text{aggregate}_W(\text{intensity}\times \text{confidence})\).

Because fitness–complexity is sensitive to degree structure, the choice of binarization/weighting policy must be treated as a first-class experimental parameter.

#### Iterative computation steps

For each window \(W\):

1. Build sparse matrix \(M\) with nonzeros `nnz`.
2. Initialize \(F^{(0)},Q^{(0)}\) to ones (or positive priors).
3. For \(n=1,2,\dots\):
   - \(\tilde{F}^{(n)} \leftarrow M Q^{(n-1)}\)
   - \(\tilde{Q}^{(n)}_i \leftarrow \left(\sum_p M_{pi}/F^{(n-1)}_p\right)^{-1}\)
   - Normalize \(F^{(n)},Q^{(n)}\) (mean or max)
   - Compute \(\Delta_F^{(n)},\Delta_Q^{(n)}\) and log
4. Stop when convergence diagnostics pass or max iterations reached.
5. Optionally run a robustness ensemble (bootstrap edges, jitter weights, sample by confidence) to produce uncertainty intervals.

#### Stopping criteria and diagnostics (must be logged)

- `epsilon` tolerance for \(\Delta_F,\Delta_Q\)
- `max_iter`
- observed iteration count
- monotonicity checks (scores can be non-monotone early in iteration)
- component warnings (disconnected bipartite components)
- minimum fitness floor \(\epsilon_F\) to prevent division blowups (logged if used)

#### Computational complexity

- Each iteration uses sparse matrix operations and per-nonzero updates: typically \(O(\text{nnz})\) time per iteration and \(O(\text{nnz})\) memory.
- Total time scales as \(O(\text{nnz}\cdot T)\) where \(T\) is iterations to convergence.

## Stability and failure modes

### Brokerage metrics

#### Degree bias and structural confounding

- Betweenness is not purely “brokerage”; high-degree hubs in certain topologies accrue high betweenness simply because many shortest paths funnel through them.
- Constraint can also be degree-sensitive: very low degree can yield unstable or artificially low/high constraint depending on normalization and whether indirect terms dominate.

**Mitigation plan:** always report brokerage alongside degree/strength and simple baselines (e.g., compare to configuration-model nulls if implemented later), and store partial correlations or stratified summaries as diagnostics rather than as substantive conclusions.

#### Small-world amplification

In small-world or highly clustered graphs, many node pairs have very short geodesic distances. Minor changes (a single shortcut edge) can dramatically reroute shortest paths, causing large swings in betweenness for nodes near the affected corridor. This is an intrinsic *discontinuity* of shortest-path-based measures.

**Mitigation plan:**

- Prefer ensemble betweenness (averaged over perturbations) rather than single-run values.
- Consider alternative path models (e.g., k-shortest paths or random-walk/current-flow variants) in later experiments if shortest-path brittleness dominates.

#### Temporal instability

Windowing can change graph connectivity sharply:

- edges appear/disappear at boundaries,
- weights shift due to decay or aggregation rules,
- multiplex coupling can create/erase cross-layer paths.

**Mitigation plan:**

- Compute brokerage as a *time series* \(B(v,W_k)\).
- Store window parameters and provide stability metrics such as:
  - rank correlation between adjacent windows,
  - volatility \(\text{Var}_k(B(v,W_k))\),
  - “turnover” of top-K brokers across windows.

#### Sampling bias and missing edges

If the graph is built from incomplete observation, betweenness can be systematically biased: missing edges can lengthen paths and inflate intermediaries; missing nodes can collapse path counts.

**Mitigation plan (evidence-first):**

- Treat edge confidence as an observation model.
- Use Monte Carlo sampling of plausible graphs (edge included ~ Bernoulli(confidence)), computing a posterior-like distribution over betweenness/constraint.
- Record sensitivity to targeted removals: remove the least-certain edges first vs. most-certain edges first, and observe metric drift.

### Capability inference metrics

#### Initialization sensitivity

Although many implementations initialize with ones, alternative initializations can affect early iterations and, in some cases, fixed points in degenerate matrices (e.g., disconnected blocks). This matters in sparse or componentized bipartite graphs.

**Mitigation plan:**

- Run multiple initializations (ones, degree-proportional, small random noise) and compare fixed points (correlations, rank stability).
- Store initialization choice and seed as part of metadata.

#### Missing data and observation bias

If membership/participation edges are under-reported for certain subpopulations or time periods, fitness can be underestimated, and complexity can be distorted (institutions may appear selectively connected simply because many edges are missing).

**Mitigation plan:**

- Perform “edge dropout” experiments: randomly remove a fraction of edges and observe stability of scores.
- Compare binary vs weighted \(M\) constructions.
- Where confidence exists, use confidence-weighted expected adjacency or Monte Carlo marginalization.

#### Edge weighting impact

Fitness–complexity was originally framed for a binary matrix (after RCA thresholding in the country–product case). Weighted generalizations can cause a few high-weight edges to dominate, especially if weights reflect duration rather than selectivity.

**Mitigation plan:**

- Implement multiple weighting policies:
  - binary threshold,
  - capped weights (winsorization),
  - log-scaled weights,
  - row-normalized weights.
- Store the entire policy as a versioned parameter bundle.

#### Convergence pathologies

Potential issues include:

- oscillations or slow convergence,
- division instability if some \(F_p\) approaches 0,
- collapse of scores in extremely sparse matrices.

**Mitigation plan:**

- Log \(\Delta_F,\Delta_Q\) per iteration and detect non-convergence.
- Enforce floors \(F_p\leftarrow \max(F_p,\epsilon_F)\) if necessary, and record when invoked.
- Detect disconnected components; compute within components or report component-level warnings.

## Power Atlas integration notes

### Derived entities as first-class, versioned outputs

Brokerage and capability scores should be stored as **DerivedMetric** artifacts, not as attributes baked into person nodes. Each derived run is defined by a complete parameterization:

- **Input provenance**
  - `graph_build_id` (the constructed evidence-first graph version)
  - `evidence_filter_policy` (min confidence, source inclusion)
  - `time_scope` (window start/end, decay params)

- **Computation spec**
  - `metric_name` (e.g., `betweenness_weighted`, `constraint`, `fitness_complexity_person`)
  - topology scope (layerwise, supra-graph, bipartite projection type)
  - transform policies (strength→distance mapping; binarization; weight caps)
  - algorithm settings (exact vs approximate; sampling size; seeds; max_iter; epsilon)

- **Outputs**
  - point estimates per person (and per institution, for complexity)
  - diagnostics (runtime, convergence curves, approximation error estimates)
  - stability measures (below)

A practical way to implement this is a “metric run” object that is content-addressed (hash of the parameter bundle + input graph build id), enabling caching, reproducibility, and comparison across experiments.

### Uncertainty and instability representation

Because the stack is evidence-first, uncertainty is not an afterthought. Recommended storage pattern:

- **Point estimate**
  - `value[p]`

- **Distribution summary**
  - `mean`, `std`, `p05`, `p50`, `p95` over an ensemble of plausible graphs and/or perturbations
  - `rank_interval` for top-K analyses (if needed later)

- **Stability indicators**
  - window sensitivity: correlation across adjacent windows
  - perturbation sensitivity: expected change under:
    - random edge dropout at rates \(r\in\{1\%,5\%,10\%\}\),
    - weight jitter (e.g., multiplicative lognormal noise),
    - confidence-threshold shifts,
    - layer inclusion/exclusion (for multiplex)

- **Attribution hooks (non-causal)**
  - for betweenness, optionally store “edge dependency mass” contributions from Brandes-style dependency accumulation to identify which regions of the graph drive a node’s score (useful for debugging, not interpretation).

### Logging iteration parameters and convergence for capability inference

For each run of fitness–complexity:

- store the full iteration trace or compressed trace (every k steps):
  - \(\Delta_F^{(n)},\Delta_Q^{(n)}\)
  - summary moments of \(F^{(n)}\) and \(Q^{(n)}\) (min/median/max)
- store termination reason:
  - converged, max_iter, numerical floor triggered, disconnected component handling
- store matrix construction metadata:
  - binary threshold, weighting policy, confidence integration mode

This turns convergence from a hidden assumption into an auditable property.

## Open research questions

A methodological experimental phase should explicitly track unresolved design choices as hypotheses to be tested:

Cross-layer brokerage semantics remain underdetermined. The supra-graph approach is formally clean, but the meaning of interlayer switching penalties \(\lambda_{\ell m}\) is an empirical modeling choice: is layer switching “free” (the same person bridges relation types effortlessly) or “costly” (switching requires additional conditions)? Power Atlas should treat \(\lambda\) as a sweepable parameter and evaluate stability across a grid.

Temporal brokerage needs a principled choice between snapshot-based approximations and truly time-respecting path models. Snapshotting is simpler and modular but may misrepresent causal/temporal ordering. Time-respecting paths are closer to temporal semantics but require heavier computation and more stringent data assumptions.

Shortest-path brokerage brittleness suggests investigating alternative flow models. If betweenness volatility under perturbation is high, later experiments could incorporate random-walk/current-flow variants that distribute “between-ness” over many paths rather than only geodesics. The open question is whether these alternatives remain interpretable and computationally feasible in the multiplex, evidence-weighted setting.

Fitness–complexity generalization to weighted, noisy bipartite matrices needs careful calibration. The economic complexity lineage often starts from binarized matrices (after a revealed comparative advantage threshold). In Power Atlas, participation edges may be inherently weighted and confidence-scored. The open question is which matrix construction best preserves the intended “selectivity” meaning while remaining stable under missingness.

Evaluation without ground truth is itself an architectural research problem. For both brokerage and capability, Power Atlas should define internal consistency tests (null models, perturbation stability, temporal smoothness priors) and avoid any premature interpretive claims. The open methodological question is how to rank competing parameterizations using only structural diagnostics and evidence-quality constraints.

Finally, evidence provenance and uncertainty propagation deserve first-class metrics. An open direction is to couple metric outputs with “evidence coverage” summaries: how much of a node’s score is supported by high-confidence edges vs. low-confidence edges, and how that changes over time windows—turning uncertainty into a visible dimension of the derived entities rather than an implicit caveat.

## References

Burt, R. S. (1992). *Structural Holes: The Social Structure of Competition*. Harvard University Press.

Brandes, U. (2001). A faster algorithm for betweenness centrality. *Journal of Mathematical Sociology*, 25(2), 163–177.

Freeman, L. C. (1977). A set of measures of centrality based on betweenness. *Sociometry*, 40(1), 35–41.

Granovetter, M. S. (1973). The strength of weak ties. *American Journal of Sociology*, 78(6), 1360–1380.

Granovetter, M. (1974). *Getting a Job: A Study of Contacts and Careers*. (Original edition; later revised editions exist.)

Hausmann, R., Hidalgo, C. A., Bustos, S., Coscia, M., Chung, S., Jimenez, J., Simoes, A., & Yıldırım, M. A. (2014). *The Atlas of Economic Complexity: Mapping Paths to Prosperity*. MIT Press.

Newman, M. E. J. (2010). *Networks: An Introduction*. Oxford University Press.

Tacchella, A., Cristelli, M., Caldarelli, G., Gabrielli, A., & Pietronero, L. (2012). A new metrics for countries’ fitness and products’ complexity. *Scientific Reports*, 2, 723.

(Additional applied organizational network sources, including Cross and collaborators, can be layered in later if Power Atlas needs operational brokerage instruments beyond the mathematical core.)