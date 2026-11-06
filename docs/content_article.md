# Beyond Vector RAG: How We Built an Incident-Response Agent That Remembers Failed Fixes

**Author:** Member 4 (AI/ML & Model)  
**System:** RecallOps Autonomous SRE Agent  
**Hackathon:** Hindsight AI Agents Hackathon  

---

It is 3:14 a.m. Your pager screams. `payments-db` is throwing HTTP 500 timeouts, checkout is stalling, and revenue is bleeding. A bleary-eyed engineer logs onto the bastion host, sees connection pool saturation, and runs the first command that comes to mind:

```bash
docker restart payments-db
```

Within sixty seconds, the outage turns catastrophic. Restarting flushed the shared buffer cache. Millions of read queries hit cold disks simultaneously, disk I/O hits 100%, and every dependent microservice collapses in an uncontrollable cascade.

The worst part? **The exact same mistake was made three weeks ago.**

Tribal knowledge in SRE is fragile. Postmortems get buried in wikis. Shifts rotate. Engineers leave. When an outage strikes, on-call responders operate under intense pressure and repeatedly try intuitive "fixes" that have already proven harmful.

When we built **RecallOps** for the Hindsight AI Agents Hackathon, we knew that basic vector search over incident tickets was not enough. To truly assist SREs, an autonomous agent needs more than text retrieval—**it needs institutional cognitive memory that remembers what *failed*.**

---

## Why Naive Vector RAG Fails in SRE

Traditional Retrieval-Augmented Generation (RAG) treats all retrieved chunks as undifferentiated ground truth. If a postmortem states *"We restarted PostgreSQL to clear stalled threads,"* naive semantic search retrieves that text and prompts the LLM to recommend restarting the container. 

Vector embeddings do not understand outcome semantics: they cannot distinguish between the remediation that saved the system and the five desperate attempts before it that made things worse.

Furthermore, naive RAG lacks temporal grounding. Without structured retention, recency weighting, and namespace isolation, generic bots generate hallucinated runbooks that senior engineers cannot trust.

---

## Dual-Memory Architecture: Retain, Recall, and Reflect

RecallOps solves this by leveraging **Hindsight Cloud** to partition memory into isolated operational namespaces:

1. **Shared Organizational Bank (`kartly-sre`):** Stores episodic incident postmortems (`context: incident_postmortem`) alongside discrete remediation outcomes (`context: fix_outcome`).
2. **Personalized Engineer Banks (`engineer-{engineer_id}`):** Stores the operational preferences and communication styles of individual engineers (`context: user_preference`).

When an active alert arrives, RecallOps executes a **Tripartite Retrieval Pipeline**:
* **Query 1 (Symptom & Service):** Queries `kartly-sre` for historical postmortems matching the error signature.
* **Query 2 (Deployment Patterns):** Correlates active commit diffs with historical deployment regressions.
* **Query 3 (Negative Memory):** Queries `kartly-sre` specifically for prior actions tagged with `Outcome: FAILED`.

---

## Negative Memory: Eliminating Operational Anti-Patterns

Negative memory is the core differentiator of RecallOps. When our ranking engine scores candidate hypotheses, it calculates:

$$\text{Final Score} = w_{\text{sim}} \cdot s_{\text{sim}} + w_{\text{recency}} \cdot s_{\text{recency}} - \text{Penalty}_{\text{failure}}$$

If an action failed in the past, it receives an aggressive score penalty ($-0.50$). Crucially, the agent isolates that action from recommendations and injects it into a high-priority warning list:

```json
"failed_fixes_warning": [
  "Do NOT restart payments-db: failed 2x in Sept during INC-1987 (wiped buffer cache and caused cold-start I/O storm)"
]
```

The system prompt strictly forbids the agent from prescribing actions listed in negative memory, mathematically eliminating the recurring blunder loop.

---

## Empirical Proof: 40-Incident Chronological Replay

To prove RecallOps learns over time, we evaluated the agent against **40 held-out historical incidents (Incidents 71–110)** across 8 core microservices. We ran two complete sequential passes:
1. **Stateless Baseline (Memory OFF):** Evaluated each alert with an empty memory bank, mimicking current state-of-the-art incident bots.
2. **RecallOps (Memory ON):** Evaluated incidents chronologically. After resolving each incident, verified postmortems and failed actions were retained into `kartly-sre`, allowing downstream incidents to learn from earlier ones.

The results proved decisive:

* **Top-1 Diagnostic Accuracy:** Jumped from **32.5%** without memory to **80.0%** with memory (**+47.5% absolute jump**).
* **Mean Time to Hypothesis (MTTR):** Dropped from **45.0 minutes** down to **21.1 minutes** (**53.1% reduction** in diagnostic time).
* **Repeated Failed Fixes:** The baseline agent recommended known anti-patterns **23 times**. RecallOps with negative memory made **0 repeated mistakes** (**100% avoidance**).

---

## Personalization: Adapting to the On-Call Engineer

SRE teams are not homogenous. During an active Sev-1 outage, incident commander **Priya** wants zero conversational pleasantries—she needs exact, copy-ready `kubectl` commands. Meanwhile, principal architect **Rahul** wants deep causal reasoning and rollback safety checks.

By querying `engineer-{engineer_id}`, RecallOps dynamically shifts its output style:
* For **Priya (`engineer-priya`)**, the agent strips narrative prose and formats `recommended_action` strictly as runnable bash commands.
* For **Rahul (`engineer-rahul`)**, the agent outputs structured architectural breakdowns with validation gates.

---

## Conclusion

Incident response is not a search problem; it is a learning problem. By combining Hindsight's episodic retention with explicit negative memory and engineer personalization, RecallOps ensures that when production breaks at 3 a.m., your team never pays for the same mistake twice.
