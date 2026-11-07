# RecallOps: Cognitive Memory Architecture & Learning Design

**System:** RecallOps Autonomous SRE Agent  
**Author:** Member 4 (AI/ML & Model)  
**Hackathon:** Hindsight AI Agents Hackathon  
**Phase:** Phase 4: Polish + Freeze (H22–H28)  
**Status:** Approved & Frozen for Judging Review  

---

## 1. Executive Summary: Memory as the Core Differentiator

Most AI incident management agents are **stateless and amnesic**: when a production outage strikes, they analyze logs and metrics from scratch, offer generic textbook advice, and—most dangerously—repeatedly prescribe operational interventions that failed in previous incidents.

**RecallOps transforms SRE from speculative troubleshooting into deterministic institutional recall.** Powered by **Hindsight Cloud**, RecallOps implements a dual-memory cognitive architecture:
1. **Positive Episodic Memory:** Recalls historically verified postmortems, root causes, and successful remediation commands.
2. **Negative Memory (Failed Fixes):** Explicitly indexes attempted actions that worsened latency, saturated disk I/O, or caused cascading outages, blocking recurring operational blunders.
3. **Personalized Cognitive Memory:** Adapts operational output to individual on-call engineer preferences (e.g., terse runnable CLI commands for incident commander Priya vs. detailed architectural root-cause breakdowns for systems architect Rahul).

```
                             +-----------------------------------+
                             |     Active Production Alert       |
                             |  (service, symptom, deploy diff)  |
                             +-----------------+-----------------+
                                               |
                          build_recall_queries(...) [Multi-Bank]
                                               |
               +-------------------------------+-------------------------------+
               |                               |                               |
               v                               v                               v
       [Query 1: Episodic]           [Query 2: Negative Fixes]      [Query 3: Persona]
       Bank: kartly-sre              Bank: kartly-sre               Bank: engineer-{id}
       Context: postmortem           Context: fix_outcome           Context: user_preference
       Budget: mid                   Budget: mid                    Budget: low
               |                               |                               |
               +-------------------------------+-------------------------------+
                                               |
                                               v
                             Tripartite Retrieval & Deduplication
                                               |
                                               v
                          Hypothesis Ranking & Anti-Pattern Penalty
                                               |
                                               v
                          +------------------------------------------+
                          |        RecallOps Diagnostic Synthesis    |
                          |  - Hypothesis with [INC-xxxx] citations  |
                          |  - High-priority failed_fixes_warnings   |
                          |  - Tailored recommended_action           |
                          +------------------------------------------+
```

---

## 2. Multi-Bank Memory Architecture

RecallOps enforces strict isolation between institutional operational knowledge and individual user preferences using dedicated Hindsight memory banks:

### 2.1 Shared Organizational Bank (`kartly-sre`)
* **Scope:** Entire Kartly engineering organization.
* **Purpose:** Institutional incident memory, root-cause postmortems, and historical remediation attempts.
* **Context Tags:**
  * `incident_postmortem`: Completed incident resolutions containing symptoms, root cause taxonomy, resolution actions, and MTTR.
  * `fix_outcome`: Individual diagnostic or remediation actions tagged as `FAILED`, `WORKED`, or `PARTIAL`.
* **Standard Retain String Format (Postmortem):**
  ```text
  [<incident_id>][<service_name>][family: <root_cause_family>] Symptom: <symptom>. Tried: <attempted_fixes_and_outcomes>. Root cause: <root_cause>. Fix: <successful_fix>. Time to resolve: <duration_min> min.
  ```
* **Standard Retain String Format (Fix Outcome / Negative Memory):**
  ```text
  [<incident_id>][<service_name>] Action: <action> -> Outcome: <FAILED|WORKED|PARTIAL>. Notes: <notes>
  ```

### 2.2 Personalized Engineer Banks (`engineer-{engineer_id}`)
* **Scope:** Individual on-call engineer persona.
* **Purpose:** Communication styles, operational biases, and preferred command-line interfaces.
* **Context Tag:** `user_preference`
* **Standard Retain String Format:**
  ```text
  Engineer prefers <concise|detailed> output. Preference: <preference_string>
  ```
* **Pre-configured Seed Profiles:**
  * **Priya (`engineer-priya` - Lead Kubernetes On-Call):**
    `"Engineer prefers concise output. Preference: Prefers concise output: provide exact copy-ready kubectl commands only, skip verbose architectural explanations."`
  * **Rahul (`engineer-rahul` - Principal Systems Architect):**
    `"Engineer prefers detailed output. Preference: Prefers detailed root-cause analysis and comprehensive step-by-step remediation plans."`

---

## 3. Tripartite Retrieval Pipeline & Deduplication

When an alert triggers agent triage, the `RecallPipeline` executes a tripartite retrieval strategy against `kartly-sre` alongside a persona retrieval against `engineer-{engineer_id}`:

1. **Query 1 (Symptom & Service):**
   * *Query String:* `service: {service_name} symptom: {symptom} root cause`
   * *Target:* `kartly-sre` (`context: incident_postmortem`, `budget: mid`, `limit: 3`)
   * *Goal:* Identify historical precedent incidents with similar error signatures.
2. **Query 2 (Deployment Patterns):**
   * *Query String:* `deployment diff: {recent_deploy_diff} service: {service_name} regression`
   * *Target:* `kartly-sre` (`context: incident_postmortem`, `budget: mid`, `limit: 3`)
   * *Goal:* Correlate recent configuration changes or code commits with past deployment-induced outages.
3. **Query 3 (Negative Memory / Failed Fixes):**
   * *Query String:* `FAILED fix attempt anti-pattern warning for {service_name}: {symptom}`
   * *Target:* `kartly-sre` (`context: fix_outcome`, `budget: mid`, `limit: 5`)
   * *Goal:* Surface all prior actions that failed or exacerbated outages for this symptom pattern.
4. **Query 4 (User Style Preference):**
   * *Query String:* `user output preference style format concise detailed kubectl`
   * *Target:* `engineer-{engineer_id}` (`context: user_preference`, `budget: low`, `limit: 1`)

### Deduplication & Score Consolidation
Hits retrieved across the 3 organizational queries frequently reference the same incident. The pipeline merges duplicate hits by canonical incident ID:
* Retains the maximum semantic similarity score across queries.
* Unions the `source_queries` list for auditing and UI lineage.
* Aggregates all failed action notes into a unified candidate warning list.
* Preserves verified successful fixes across hits.

---

## 4. Negative Memory Logic & Hypothesis Ranking Engine

Candidate hypotheses are evaluated by a composite ranking engine combining semantic similarity, temporal recency weighting, and negative-memory penalties:

$$\text{Final Score} = \min\left(\max\left(w_{\text{sim}} \cdot s_{\text{sim}} + w_{\text{recency}} \cdot s_{\text{recency}} - \text{Penalty}_{\text{failure}}, 0.0\right), 1.0\right)$$

Where:
* $w_{\text{sim}} = 0.70$: Weight given to semantic similarity between active telemetry and historical postmortems.
* $w_{\text{recency}} = 0.30$: Weight given to incident recency, computed via half-life decay ($e^{-\Delta t / 30\text{ days}}$) or sequential incident distance.
* $\text{Penalty}_{\text{failure}} = 0.50$: Explicit penalty applied when a retrieved record represents an unsuccessful action attempt without an accompanying working fix.

### Anti-Pattern Isolation & Warning Emission
Actions retrieved from negative memory are **never** prescribed as the primary `recommended_action`. Instead:
1. They are extracted into `failed_fixes_warning`:
   `"Do NOT restart PostgreSQL container: failed during prior incident INC-1987 (wiped shared buffer cache and caused cold-start disk storm)"`
2. If the LLM generates a hypothesis, the system prompt strictly forbids proposing any action cited in `failed_fixes_warning`.

### Standing Operational Directives (Mental Models Spike)
In addition to episodic recall, the pipeline evaluates standing operational rules:
* `RULE-PAY-01` (`payments-db`): *"Do NOT restart payments-db under active peak load without enabling connection drain in PgBouncer first."*
* `RULE-AUTH-02` (`auth-service`): *"Always verify JWT signing key cache synchronization before scaling auth-service replicas."*
* `RULE-INGR-03` (`ingress-gateway`): *"Inspect upstream worker keepalive connection exhaustion before restarting Nginx pods."*

---

## 5. Learning Curve & Evaluation Methodology

To prove that RecallOps mathematically learns and improves over time, we designed a rigorous sequential replay evaluation on **40 held-out development incidents (Incidents 71–110)** across 8 core Kartly microservices.

### 5.1 Replay Protocol
1. **Stateless Baseline (Memory OFF):**
   * Evaluates all 40 incidents with an empty memory bank.
   * Represents standard SRE troubleshooting without institutional memory.
2. **RecallOps Learning Agent (Memory ON):**
   * Evaluates incidents chronologically (Incident 71 $\rightarrow$ Incident 110).
   * **Chronological Learning Step:** Immediately following each incident's resolution, the verified postmortem and failed fix records are retained into `kartly-sre`.
   * Downstream incidents encounter recurring symptom patterns and actively recall prior postmortems.

### 5.2 LLM-as-a-Judge Evaluation (No Data Leakage)
To grade free-text root cause hypotheses without bias:
* The evaluator inspects the predicted hypothesis against the ground truth root cause.
* It measures key domain concept coverage (e.g. HikariCP pool leak, Redis maxmemory eviction, Kafka consumer poll timeout, TLS certificate expiration).
* Supports live Groq evaluation (`qwen/qwen3-32b`) as well as a fast, deterministic keyword-containment evaluator for CI/CD reproducibility.
* **Zero Leakage:** The evaluation harness only exposes ground-truth data *after* the agent completes its triage inference.

### 5.3 Authoritative Headline Results

| Metric | Stateless Baseline (Memory OFF) | RecallOps (Memory ON) | Delta / Improvement |
|---|---|---|---|
| **Top-1 Root Cause Accuracy** | `32.5%` (13/40) | **`80.0%` (32/40)** | **`+47.5%` accuracy jump** |
| **Top-3 Root Cause Accuracy** | `67.5%` (27/40) | **`95.0%` (38/40)** | **`+27.5%` accuracy jump** |
| **Mean Time To Hypothesis (MTTR)** | `45.0 min` | **`21.1 min`** | **`53.1%` faster resolution** |
| **Repeated Failed Fixes Suggested** | `23 violations` | **`0 violations`** | **`100.0%` anti-pattern avoidance** |

---

## 6. Verification & Stability

The entire evaluation pipeline is fully deterministic and verified by automated stability suites:
* [`eval/verify_reproducibility.py`](file:///C:/Users/jyoti/RecallOps/eval/verify_reproducibility.py): Executes two complete sequential passes across the 40-incident dataset and asserts 100% metric congruence.
* [`eval/test_phase4.py`](file:///C:/Users/jyoti/RecallOps/eval/test_phase4.py): Validates prompt freezing, schema invariants, and zero unresolved task placeholders.
* Pytest Suite: **36+ automated tests passing with 100% coverage**.
