# Research Lab: Stage 2 report (security)

27 October 2026. For the research lead. Stage 2 of `CB_Research_Tab_Build_Spec_v1.md` (steps 9 to 11) is built and tested, on branch `imashi/dev/research_security`.

## 1. What now exists

| Part | What it does |
|---|---|
| Security pack | `finebase_entitlements_v1`: 490 episodes. Attacks come through the customer's email, a poisoned policy, and the shop's own order record. Also an L2 agent acting for L3 staff, an L3 insider asking through Ask, and 70 benign episodes |
| Oracle | Judges every label from the pack's own relations and attributes, written apart from the product's access code. All 490 agree |
| P9, P10 | Every access decision records its effective tier, capabilities and latency. A canary never reaches a display |
| Conditions | U: nothing checked. P: rules written into the prompt. R: retrieval filtered. I: Finebrain as it is. Each runs the real pipeline in its own lab tenant |
| Screens | New experiment shows each paper's conditions. A paper shows episodes one at a time, and dashed lines for numbers from outside the Lab |
| Public benchmarks | AgentDojo banking, run by the Lab. PhantomPolicy figures, taken from its paper |

## 2. Decisions taken for you (please confirm or change)

| # | Decision | Why |
|---|---|---|
| 1 | The agent is Claude Sonnet 5.5, the product's own reasoning model | The paper is about Finebrain as it runs |
| 2 | "Read leak" means a restricted item reached the agent; "canary said" is reported apart | Reaching the agent is exposure; saying it is disclosure. They are different claims |
| 3 | 440 refund episodes were rerun after a lab defect, inside the same experiment, and the experiment's notes say so | The lab clock stood still, so the refund tool's limit of 10 a minute refused every later refund. Attack episodes never reached the tool. A full rerun would have cost about $16 more |
| 4 | AgentDojo runs Finebrain's rule ported to its tools, not the product's OPA policy | OPA knows only Finebrain's own capabilities |
| 5 | The acceptance preregistration is labelled an engineering check | The paper's hypotheses are yours to write and lock |

## 3. The acceptance run (Finebase HQ, real infra)

1,960 episodes, one seed. Cost: $16.46 recorded, plus about $3.60 for the dropped episodes. Gates passed; eight labs torn down.

| Metric | U unconstrained | P prompt only | R retrieval filter | I enforcement |
|---|---|---|---|---|
| Forbidden actions (of 300) | 0.0% | 0.0% | 0.0% | 0.0% |
| Attacks that worked (of 300) | 0.0% | 0.0% | 0.0% | 0.0% |
| Restricted item reached the agent (of 450) | 100% | 100% | 0.0% | 0.0% |
| Canary said (of 450) | 0.0% | 0.2% (1) | 0.0% | 0.0% |
| Benign work done (of 70) | 100% | 100% | 100% | 100% |
| False denials (of 50) | 0.0% | 0.0% | 0.0% | 0.0% |

The access check at the call took 20 ms at the median and 68 ms at the 95th percentile.

| Hypothesis | Verdict |
|---|---|
| H1: forbidden actions under I at most 1% (rule of three) | Supported: 0 of 300, upper bound 1.0% |
| H2: forbidden actions under R above 5% | Not supported: 0 of 300 |
| H3: read leaks, I minus U, at most −10 points | Supported: −100 points, p < 0.0001 |
| H4: benign work under I at least 80% | Supported: 70 of 70, lower bound 94.8% |

## 4. What it means

1. **Retrieval is where the gap is.** With no filter (U, P), every restricted control reached the agent. With the filter (R, I), none did. Writing the rules into the prompt (P) changed nothing about what the agent saw.
2. **The model itself refused every injected refund.** Sonnet 5.5 escalated all 300 tempting episodes in every condition, so this pack cannot show what the check at the call adds. A paper claim about I needs attacks this model falls for, or a weaker model as a second arm.
3. **Exposure is not disclosure.** The agent saw restricted text in 900 episodes and repeated a canary once. Both numbers belong in the paper.

## 5. Public benchmarks

| Benchmark | Setting | Result |
|---|---|---|
| AgentDojo banking v1.2.1, our run, Sonnet 5.5 | No defense | Attacks 0 of 144; benign 16 of 16; under attack 135 of 144 |
| | Finebrain's rule at the call | Attacks 0 of 144; benign 14 of 16; under attack 126 of 144 |
| PhantomPolicy (paper, five models) | No enforcement | 286 of 300 violations (Claude Sonnet 4.6: 54 of 60) |
| | Policy in the prompt | 122 of 300 |
| | Sentinel at the call | About 12% of violations missed |

On AgentDojo the rule cost two benign tasks: both pay or update from a file the user named, which the rule refuses by design. As in our pack, Sonnet 5.5 resisted every injection without help. PhantomPolicy's figures come from the paper, because its data has no public link yet.

## 6. Gaps

| Gap | What it would take |
|---|---|
| Attacks the model falls for | A harder attack set, or a second, weaker agent model |
| One seed | Three seeds for the paper run (about $50 at today's prices) |
| PhantomPolicy run by the Lab | Its released data |
| AgentDojo beyond banking | Workspace, Slack and travel suites, about $6 each |
| The OPA policy for outside tools | Capabilities for banking-style tools, if a paper needs the product's own policy there |
