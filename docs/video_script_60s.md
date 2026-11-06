# RecallOps Video Walkthrough Script (60–90 Seconds)

**Presenter:** Member 4 (AI/ML & Model)  
**Target Duration:** 85 Seconds (1:25)  
**Deliverable:** Phase 5 Submission Video Walkthrough  

---

### [00:00 – 00:15] INTRO & THE SRE NIGHTMARE
* **Visual:** Camera on speaker, cutting to a mock PagerDuty alert screen: `[CRITICAL] payments-db connection pool exhausted`.
* **Audio / Voiceover:**
  > "Every engineer knows the 3 a.m. nightmare: production is down, and under pressure, someone restarts the database—flushing the cache and triggering a cascade outage. The tragedy isn't just the downtime; it's that the team made that exact same mistake three weeks ago. Traditional SRE bots have zero memory of past failures. We built RecallOps to make sure teams never repeat an operational mistake."

---

### [00:15 – 00:35] CODE DEEP DIVE: NEGATIVE MEMORY & GROUNDING
* **Visual:** Screen recording of VS Code showing [`backend/app/schemas/agent_tools.py`](file:///C:/Users/jyoti/RecallOps/backend/app/schemas/agent_tools.py) and [`backend/app/prompts/system_prompts.py`](file:///C:/Users/jyoti/RecallOps/backend/app/prompts/system_prompts.py). Highlight `failed_fixes_warning` and `[INC-xxxx]` citation rules.
* **Audio / Voiceover:**
  > "Here’s how our model engine works in code. Rather than generic RAG, we split memory into organizational postmortems in `kartly-sre` and explicit negative memory records. In our system prompt, our agent is strictly penalized if it touches known dead-ends, and it's mandated to emit an explicit warning in `failed_fixes_warning`—while citing verified incident IDs like `[INC-1987]` as proof."

---

### [00:35 – 00:55] LIVE EVALUATION HARNESS: LEARNING CURVE IN TERMINAL
* **Visual:** Terminal running `python eval/verify_reproducibility.py`. Highlight the sequential Pass 1 and Pass 2 output showing 80.0% accuracy vs 32.5% baseline.
* **Audio / Voiceover:**
  > "To prove learning over time, we ran a sequential replay harness across 40 held-out development incidents. Look at the terminal: in stateless baseline mode, the agent hovers at 32.5% accuracy and repeats failed fixes 23 times. But with Hindsight memory active, accuracy jumps to 80%, MTTR drops by 53%, and repeated anti-patterns collapse to absolute zero."

---

### [00:55 – 01:15] DYNAMIC USER PERSONA ADAPTATION
* **Visual:** Switch back to code or UI showing [`eval/memory_templates.py`](file:///C:/Users/jyoti/RecallOps/eval/memory_templates.py) and the difference between Priya's output (`kubectl rollout restart ...`) vs Rahul's detailed analysis.
* **Audio / Voiceover:**
  > "RecallOps also personalizes to the on-call engineer. From bank `engineer-priya`, it recalls that Priya wants raw, runnable `kubectl` commands without conversational fluff. For Rahul, it provides deep architectural root-cause breakdowns. One autonomous engine; zero friction for whoever is on-call."

---

### [01:15 – 01:25] OUTRO & SUMMARY
* **Visual:** Split screen of the GitHub repository and the final headline metrics slide: `+47.5% Accuracy | -53.1% MTTR | 0 Repeated Bad Fixes`.
* **Audio / Voiceover:**
  > "By combining episodic postmortems, negative memory, and engineer style preferences, RecallOps turns incident triage into deterministic institutional recall. Thanks for watching!"
