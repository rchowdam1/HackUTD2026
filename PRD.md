---
title: "CallSafe — Product Requirements Document"
version: "1.4"
status: "Hackathon product specification and build plan, revised after two validation reviews, the SMS/operator-console operating model, and four model-council reviews; integration and production assumptions unvalidated"
created: "2026-11-07"
updated: "2026-11-07"
owner: "CallSafe hackathon team"
method: "BMAD-aligned PM PRD: essential spine + enterprise/privacy adaptations + five-gate verification lifecycle"
---

# CallSafe
## Product Requirements Document | Hackathon v1.4

**One-line pitch:** *Protect the person, not just the phone number.*

**Product thesis.** A phone number's reputation can't tell you what a caller will ask once you pick up. CallSafe listens, only with the subscriber's opt-in, for the moment a call turns dangerous (a request for a code, password, SSN, money or remote access), texts the subscriber one clear, safe next step, and follows up after the call. There is nothing to install and no browser to open: it works on any phone that can receive a text. T-Mobile's fraud and scam protection team runs the service from an operator console, and every claim that we are doing better has to pass five verification gates (§8). Delivered at the carrier layer, the same protection could reach subscribers whose phones lack on-device scam detection. **[ASSUMPTION]**

**Scope.** The hackathon demonstrates the pipeline on replayed and controlled calls with mocked carrier signals, sends real texts to a team-owned test phone, and reports measured results against the comparison arms in §9. Real carrier integration and broader device coverage are future work behind gates G-01 to G-07 (§15). We are not claiming to have invented AI scam detection; Google, Samsung and Apple already ship versions of it (§1.3).

| Item | Decision |
|---|---|
| Primary customer | Opted-in T-Mobile subscriber, including people on older or basic phones who want protection with nothing to install |
| Buyer / operator | Hypothetical T-Mobile fraud and scam protection team, working entirely in the operator console; no endorsement assumed |
| Form factor | Carrier-side service with no subscriber app or browser. Subscribers get SMS; operators use a web console. Replay-driven demonstrator (controlled VoIP call is P1) |
| MVP threat scope | Voice-call social engineering: OTP, credentials/SSN, payment transfers, remote-access requests, impersonation |
| Core capability | Opt-in in-call monitoring + SMS intervention + post-incident follow-up SMS; pre-answer screening is optional (P1) |
| Decision policy | Deterministic Python rules and versioned evidence fusion; pretrained Intent Evidence model (P0) and Voice Evidence model (P1, conditional on Gate 0), each evaluated independently |
| Verification | Five gates, V1 Workflow grounding through V5 Continuous improvement, tracked on the console's gate board (§8) |
| Release target | Demonstrable, measured hackathon prototype; not production carrier deployment |
| Status | Build plan and three-developer split frozen in §19 (v1.4); §19 wins where it conflicts with earlier sections; external access, consent and validation gates remain open |

## 0. Document purpose and evidence posture

This PRD directs the hackathon's product, frontend, backend, model-evaluation, and demonstration work. It distinguishes **[DECIDED]** team choices, **[ASSUMPTION]** unverified dependencies, and **[GATE]** conditions required before real customer deployment. Tags appear in the opening thesis, inline wherever a statement depends on an assumption or gate, in the gate table (§15) and in the decision register (§16); untagged requirements are team decisions. The grouped functional requirements use stable IDs (`FR-01` onward); journeys use `UJ-01` onward; metrics use `SM-01` onward. Two reviews of v1.0 inform this version: the validation review `review-prd.md` and a later adversarial final review (both 2026-11-07). Changes made in response to each, and to the v1.3 operating-model change, are logged in §18.

**Three kinds of gate:** **Gate 0** is the early feasibility and kill test (§6). **V1–V5** are the verification gates that every claim and every policy change must pass (§8). **G-01–G-07** are external approvals needed before any real customer (§15).

**Build plan (v1.4):** §19 is the document agents build from: the 3-minute judging loop, scope, frozen stack, interface contracts, SMS copy, evaluation, milestones and the three-developer split. Where §19 conflicts with §1–§18, §19 wins.

**Sources of insight:** the T-Mobile CallSafe challenge slide (user-provided), the team's judge interview notes (not independently verified as corporate commitments), the five-step AI evaluation lifecycle graphic provided to the team, team-compiled summaries of public T-Mobile job postings (third-party summaries, not independently verified), previously discussed research on audio deepfake detection, and public product/platform documentation listed in §17. No proprietary T-Mobile API, actual customer dataset, production model checkpoint, legal approval, or real carrier integration has been verified.

## 1. Vision and positioning

### 1.1 Problem

Caller reputation and number-based filtering are useful, but cannot reliably determine what a caller will ask *after* a connection. A seemingly ordinary conversation can become an OTP theft, fake bank transfer, or account-takeover attempt. The customer then needs a short, trustworthy action, not merely a fraud score. Meanwhile, a false alarm may interrupt a legitimate bank, school, pharmacy, or healthcare call. Repeated false warnings can undermine confidence.

### 1.2 Product vision

CallSafe extends existing call protection with an **opt-in, conversation-aware layer** that the subscriber never has to open. The subscriber opts in by replying to a text. On calls routed through a controlled telephony path, CallSafe analyzes conversational risk and, when it identifies an actionable high-risk request, sends a short SMS with a plain-language warning and an independent next step. After the call, a follow-up SMS repeats the advice and offers recovery steps by reply keyword. T-Mobile's fraud and scam protection team configures policy, reviews evidence, monitors quality and approves every change from an operator console. Optionally (P1), the system may also answer before the subscriber and ask the caller to state the reason for calling. Synthetic-voice evidence may inform triage but never proves fraud or legitimacy.

**Customer promise:** *You remain in control of your calls. When a caller asks you to do something risky, we text you what the concern is and a safer next step. We will never tell you a caller is safe, and we will never ask you for codes, passwords, money or personal information. Replies are optional, and no text doesn't mean a call is safe.*

### 1.3 Why this could win where smartphone features exist

The competitive hypothesis **[ASSUMPTION]** is **device-independent, carrier-operated intervention** combined with authorized carrier signals and accessible, text-based guidance. This is differentiated from a device-exclusive on-device feature **only if** the carrier makes real audio-routing and consent integration available, coverage increases, and measured incremental safety exceeds privacy/latency costs. Apple already screens unknown callers; Pixel and some Samsung devices already provide in-call scam detection. Consequently **pre-answer screening and “AI listens for scams” are not standalone differentiators**. T-Mobile's own Scam Shield already labels likely scam calls (Scam Likely), can block them (Scam Block), and warns subscribers who dial a Scam Likely number (Callback Protection); these are number-based checks, and its public page describes no in-call conversation analysis.

**Additive claim:** calls that pass number and reputation filters can still turn into a request for a code, credential or transfer after connect. CallSafe detects that *request*, not the caller's identity, texts one specific independent next step, and follows up afterward. Because the subscriber side is only SMS, it works on phones that can't run on-device detection, including basic phones. The hypothesis remains unproven until the benchmark in §9, and lift is claimed only against our own baselines. Prepared answers to the hard judge questions are in §9.4.

**Positioning (v1.4) [DECIDED]:** T-Mobile Live Translation (beta February 2026, live May 21, 2026) already runs network-native AI inside live calls on any phone, including flip phones, started by dialing \*87 (§17). "Nothing to install, any phone" is therefore not novel on its own; Live Translation is precedent that carrier in-call AI works, and CallSafe points that path at scam requests. Hiya pairs scam alerts with post-call summaries, Aura monitors conversations with unknown callers and offers family access, ABA and AT&T run scam education, and Bitdefender Scamio answers "is this a scam?". Each owns one piece, so we claim no unique combination. Our wedge: **we don't ask you to trust AI.** Each alert names the request the caller made (not a verdict about the caller, unlike Pixel's "Likely scam"), gives one step that is safe even if the alert is wrong or forged, and the follow-up teaches the tactic so the subscriber spots it next time. The coverage argument leads with iPhones, which have pre-answer screening but no in-call scam detection (secondary sources), ahead of basic phones, where reading a text mid-call is hardest.

### 1.4 Jobs to be done

- **Functional:** When someone calls unexpectedly, help me understand the request without making a false authenticity guarantee.
- **Protective:** When someone asks me to share a code, password, SSN, money, or device access, warn me quickly and suggest independent verification.
- **Emotional:** Help me feel supported without making me afraid of every unfamiliar call.
- **Access:** Give me protection that works on the phone I already have, with nothing to install, even on an older phone or under poor connectivity.
- **Enterprise:** Let the fraud team run the service, see outcome quality, privacy posture and service health, and approve changes without viewing customer conversations.

## 2. Users and user journeys

### 2.1 Primary user and boundaries

**Primary subscriber:** T-Mobile subscriber who has deliberately enabled the feature from their own phone. Subscribers interact only through calls and SMS. Accessibility considerations include older adults, customers in rural communities, limited technical familiarity, visual/hearing accommodations, and intermittent connectivity. Age or geography is **not** a fraud-risk proxy. **Primary operator:** T-Mobile's fraud and scam protection team (hypothetical; no endorsement assumed), working entirely in the operator console. **Secondary:** privacy/security reviewer and network integration owner. **Non-users in v1:** enterprise contact-center agents and users sending image attachments or email phishing reports.

### 2.2 Named journeys

**UJ-01 — Ruth receives a legitimate call that mentions a code.** Ruth uses an older phone, is expecting a clinic callback, and opted into monitoring by replying YES to an invitation text. The caller confirms her appointment and says, “We'll text you a confirmation code. Please don't share it with anyone who calls.” Because the code is mentioned in a warning and nothing is asked of Ruth, no text is sent and the call continues uninterrupted. CallSafe never sends an “all clear” either. If the optional Screening Proxy (P1) is built, Ruth hears the clinic's stated name and reason when she picks up, labeled as what the caller stated, and presses 1 to connect; if screening fails, the call rings through normally. **Value:** important calls are preserved and benign mentions of codes don't cause alarms. **Edge:** a blocked/withheld number is not classified as criminal merely because caller ID is missing.

**UJ-02 — Daniel hears a bank impersonator request an OTP.** An unfamiliar caller opens with a generic, benign introduction. Daniel opted into monitoring. The caller later asks Daniel to read out a six-digit verification code. Python rules identify a high-risk request, and within seconds Daniel's phone buzzes with a text from CallSafe's fixed sender: **“CallSafe: caller is asking for a code. Don't share it. Hang up, call your bank's number yourself.”** (§19.5) Daniel glances at it and ends the call. After he hangs up, a follow-up text (FR-23) repeats the advice and lists reply keywords: SHARED for next steps if he already gave the code, WRONG if the warning was a mistake, STOP to end CallSafe. If Daniel's phone is at his ear, the text's vibration and tone are the in-call cue; an audible in-call cue is P1 (FR-17). **Value:** CallSafe intervenes when the *request* becomes dangerous, irrespective of whether the voice is genuine or synthetic, doesn't leave Daniel on his own afterward, and needs nothing but his phone. **Edge:** if classification is inconclusive, nothing is sent and no definitive scam label is shown anywhere.

**UJ-03 — Sofia receives a family-impersonation call with no explicit scam phrase.** A caller claiming to be her grandson says he's in trouble, needs her help with bail today, and asks her not to tell his parents. No deterministic rule fires because the script avoids the FR-07 payment phrases (send, transfer, wire, gift card); if a payment phrase appears, this becomes a rule case, not a model-coverage case. The weak-signal trigger (FR-12, T2) sees a relationship claim, urgency, secrecy and a payment request in the same window and invokes the scam-intent model, which returns urgency/payment Intent Evidence. Versioned policy sends a text: **“CallSafe: caller is asking for money. Don't send any. Call your relative back on a number you already have.”** If the Voice Evidence model passed Gate 0, it runs on the same window and may add “voice authenticity uncertain” to the operator console as supporting context. **Value:** help under an unfamiliar attack pattern, whether the voice is synthetic or a human impersonator. **Edge:** a suspicious voice score alone produces “voice authenticity uncertain,” never “fraud confirmed”; if Intent Evidence is insufficient, policy abstains and nothing is sent.

**UJ-04 — A fraud-operations analyst runs the service.** An analyst on T-Mobile's fraud and scam protection team signs in to the operator console. The gate board shows V1–V5 status with links to the evidence. Monitoring panels show aggregate alert rates, A/K/B/C comparison results, rule IDs, model invocation rates, SMS dispatch latency and delivery receipts, reply-keyword counts, and queue depth. The analyst cannot retrieve raw audio, transcripts, caller or subscriber phone numbers, or SMS bodies beyond template IDs. A simulated inference outage is visible as “enhanced analysis unavailable.” **Value:** the team runs and governs the service without seeing personal content.

**UJ-05 — An analyst promotes a policy fix.** On replayed traffic, the console flags a rising WRONG-reply rate on one rule: appointment-reminder calls that say “we need to reset your appointment” trip the account-reset rule. The analyst first writes a regression fixture, then drafts a lexicon change that requires an account or password near “reset.” (If built, the P1 Nemotron agent can draft the change and run the development-set evaluation instead.) The evaluation owner scores the candidate on a held-out batch (in the hackathon, H1 reused and labelled as such; H2 is dropped, §19), and the gate board shows SM-10 met: recall unchanged, hard-benign false alerts down. The analyst approves, policy v1.1 goes live, and the audit log records who approved it, why, the evidence, and the rollback version. **Value:** “doing better” is earned on data the change was never tuned on, and every change is traceable. **Edge:** if the batch shows recall falling, the console blocks promotion. At hackathon sample sizes this is a workflow demonstration ("no regression observed on n=..."), not proof of improvement.

## 3. Glossary

| Term | Meaning |
|---|---|
| Reputation Signal | Existing carrier-derived caller reputation or verification metadata made available through an authorized adapter; may be unknown. |
| Screening Proxy | Optional (P1) controlled telephony component that answers before a subscriber, asks for a caller introduction and plays it to the subscriber. |
| Monitoring Session | Explicitly authorized audio-analysis period on a supported call route; not general access to cellular audio. |
| Risk Event | Structured evidence of a potentially harmful requested action with category, timestamp, source, and provenance. |
| Voice Evidence | Acoustic evidence that audio may be synthetic; not evidence of criminal intent. |
| Intent Evidence | Text/audio-derived evidence of requests, coercion, or fraud-associated behaviors; not proof of a crime. |
| Model Trigger | Versioned policy condition (T1–T4, FR-12) that decides when a pretrained model runs. |
| Policy Engine | Deterministic, versioned Python component mapping Risk Events and evidence to responses. |
| Intervention | Customer-facing warning SMS with a clear, independently verifiable next step. |
| Follow-up Text | Template-only SMS sent after a call that triggered an `action_warning`, built solely from the Risk Event's category and recommended next step (FR-23). |
| Reply Keyword | A word the subscriber texts back (YES, SHARED, WRONG, STOP, HELP) to opt in, get recovery steps, report a false alert, stop the service, or get help (FR-26). |
| Messaging Gateway | The Provider Adapter's SMS interface: a mock, an SMS API (hackathon), or the carrier's SMS center (production). |
| Class 0 (flash) SMS | SMS class that supporting handsets show immediately on screen; providers describe it as not saved to the inbox. Optional P1 attention cue only, never the only copy (FR-16). |
| Abstention | Explicit output when a component or the Policy Engine lacks sufficient evidence. No SMS is sent. |
| Operator Console | Web app the fraud and scam protection team uses to configure policy, review gate evidence, monitor aggregates and approve changes. The product's only UI. |
| Verification Gate (V1–V5) | One of five lifecycle checkpoints (§8) that must be passed, with recorded evidence, before a claim or change goes forward. |
| Gate 0 | Early feasibility and kill test (§6). Distinct from V1–V5 and from the external approval gates G-01–G-07 (§15). |
| Policy Promotion | Putting a new policy version into use after it passes V3 on a sealed held-out batch and an operator approves it (FR-25). |
| Demo Baseline | Comparator arm A using only the simulated/available Reputation Signal; not a measured production T-Mobile system. |
| Keyword Baseline | Comparator arm K: ASR plus the same request keyword lists the rules use, with no negation, context, or dialogue state; any keyword hit warns. |
| Provider Adapter | Typed integration interface allowing a mock or a separately authorized carrier/telephony/messaging provider. |

## 4. Features and functional requirements

### 4.1 Eligibility, control and call screening

**Description:** Respect caller routing and user choice, get authorized signals before any analysis, and (P1) provide optional pre-answer context. Real subscriber traffic is outside hackathon scope. Realizes UJ-01, UJ-02 and UJ-03.

| ID | Requirement | Priority | Testable acceptance |
|---|---|---|---|
| **FR-01** | Accept call audio only from approved synthetic replay (P0) or a controlled call path (P1). | P0 | Unauthorized stream is rejected; replay enters the pipeline; a controlled demo call, if built, enters the same pipeline. |
| **FR-02** | Retrieve typed Reputation Signal through Provider Adapter, supporting `known`, `flagged`, `unknown`, `unavailable`; never promote unknown to safe. | P0 | Mock API can emit every state; engine follows documented mapping. |
| **FR-03** | Honor explicit opt-in for the Monitoring Session, given by the subscriber from their own phone by replying YES to an invitation text, and a separate opt-in for the Screening Proxy when it is built; STOP ends monitoring and texts. Opt-in through an existing carrier account channel is a pilot alternative **[ASSUMPTION]**. | P0 | Monitoring never starts without a recorded opt-in for that line; STOP ends ingestion for subsequent calls and is confirmed by text. |
| **FR-04** | Answer before the subscriber, ask the caller for name and reason, and play the stated intro to the subscriber, who presses a key to connect; never certify identity. | P1 | Intro is presented as what the caller stated; no verified-identity assertion. |
| **FR-05** | Preserve legitimate call access on screening timeout, nonresponse, accessibility failure, and provider outage by defined bypass/normal-routing policy. | P1 (with FR-04) | Failure-injection fixture does not hard-block a call or claim safety. |

### 4.2 Deterministic conversation risk analysis

**Description:** Incremental transcription feeds a conversation state machine that recognizes high-risk requests, direct speech acts, and relevant preceding context. A phrase match is an event, not a criminal verdict. Realizes UJ-01, UJ-02 and UJ-03.

| ID | Requirement | Priority | Testable acceptance |
|---|---|---|---|
| **FR-06** | Transcribe authorized audio incrementally, preserving segment timing and a transient per-call buffer. | P0 | Scripted audio emits timed transcript events; buffers expire per configuration. |
| **FR-07** | Detect requests involving OTPs, passwords, SSNs, transfers, gift cards, account resets, and remote-access software using tested Python rules. | P0 | Positive/benign minimal pairs trigger expected structured Risk Events. |
| **FR-08** | Incorporate dialogue context: caller claim, urgency, customer action requested, negation, and recent prior turns. | P0 | “Never share your code” and “Read me your code” do not receive the same action classification. |
| **FR-09** | Emit a versioned Risk Event with `type`, `source`, `rule_id`, `span_start`, `span_end`, `confidence_class`, and `evidence_summary`, with no raw PII in persistent logs. | P0 | Schema validation rejects malformed events and logging test finds no test PII. |

### 4.3 Separate pretrained model fallbacks

**Description:** Use existing inference weights; do **not** train a foundation model. Intent Evidence is P0. Voice Evidence is P1 and is built only if it passes the Gate 0 kill criterion below. The two capabilities are measured separately, and their outputs are advisory signals to the Policy Engine. Realizes UJ-03.

| ID | Requirement | Priority | Testable acceptance |
|---|---|---|---|
| **FR-10** | Support an existing pretrained acoustic anti-spoof / deepfake detector on short waveform windows; report uncertain/insufficient audio when applicable. | P1 (Gate 0-conditional) | Synthetic/genuine/low-quality clips at 8 kHz μ-law yield structured outputs; no raw score shown as a calibrated probability. |
| **FR-11** | Support a separate existing text/audio scam-intent model for semantically ambiguous conversations. | P0 | Model classifies held-out intent scenarios into controlled categories and abstention. |
| **FR-12** | Invoke models only through versioned triggers. **T1 ambiguity:** a rule matched below `high` confidence, or negation/context is unresolved. **T2 weak-signal accumulation:** two or more weak cues from versioned lexicons (relationship or authority claim, urgency, secrecy, payment or value transfer) within a rolling window, with no rule match. **T3 audit sampling:** a configured fraction of windows on calls with no rule match. **T4 voice check:** if FR-10 is enabled, one early window per session plus any T1/T2 window. Window sizes, cue counts and sampling rates are policy parameters, tuned only on the development set. | P0 | Each trigger has a fixture that fires it and a near-miss fixture that doesn't; a call with no rule match still enters the T3 audit path. |
| **FR-13** | Enforce per-session and global model budgets and bounded queues. On timeout/unavailable, emit model-unavailable rather than safe. | P0 | Simulated GPU saturation does not produce “safe” results or unbounded queue growth. |

**Model-selection gate [GATE]:** an open-source/open-weight checkpoint is eligible only if its code and weights may be used under the actual hackathon/deployment terms, run on available compute, and pass independent telephone-quality, unseen-generator and unseen-scenario evaluations. Candidate anti-spoof baselines include AASIST and XLS-R/wav2vec 2.0 + AASIST. A separate pretrained text classification/NLI model can bootstrap Intent Evidence; its scam-domain quality must be measured. Do not imply that any model is already licensed, deployed, or proven generalizable.

**Voice Evidence kill criterion [DECIDED]:** Twilio Media Streams deliver 8 kHz μ-law mono audio, while AASIST-family checkpoints are typically trained on 16 kHz research corpora such as ASVspoof. Upsampling cannot restore the missing bandwidth. At Gate 0, evaluate the candidate on a small codec-matched set (team-recorded genuine and synthetic clips round-tripped through 8 kHz μ-law). Drop FR-10 from the build if EER on that set is 25% or worse, or later if the §9.2 ablation shows zero or negative incremental contribution. The 25% figure is a proposed team threshold, not a literature value. Intent Evidence and the deterministic rules do not depend on this pathway.

**Intent Evidence contract [DECIDED]:** the input is the rolling transcript window from the current session (the last few turns plus the triggering span), processed in-session and never sent to a third-party general-purpose LLM service (§5). The output is one category from a versioned list (`credential_or_code_request`, `payment_or_transfer_request`, `remote_access_request`, `authority_or_relationship_claim_with_urgency`, `none`) or `abstain`, plus a `confidence_class`. The first candidate is a zero-shot NLI checkpoint scored against one hypothesis template per category. If the team enters the NVIDIA track (§6.1), a self-hosted Nemotron model is a second candidate, run on redacted windows (digit strings and names masked before inference) and judged by the same V3 criteria. A small fine-tuned classifier is a post-hackathon option, and only if a licensed scam-domain dataset is available.

**Lead with rules [DECIDED]:** if C adds no true warnings over B on the held-out paraphrase scenarios, or adds more false alerts than true warnings, B is presented as the product and the intent model as an experiment that didn't help, with the numbers shown.

### 4.4 Deterministic fusion, SMS interventions and subscriber messaging

**Description:** Interpret risk evidence conservatively, warn about actions by SMS, and give meaningful next steps. The subscriber needs no app, browser or reply to benefit. Realizes UJ-01, UJ-02 and UJ-03.

| ID | Requirement | Priority | Testable acceptance |
|---|---|---|---|
| **FR-14** | Version Policy Engine thresholds, precedence and abstention outcomes; expose matched policy ID. | P0 | Fixed inputs produce repeatable outcomes in regression tests. |
| **FR-15** | Never turn a Reputation Signal, Voice Evidence, or uncalibrated model score into a definitive “fraudulent,” “human,” or “verified safe” classification. | P0 | Output-contract tests reject prohibited labels in uncertain cases. |
| **FR-16** | Map qualifying Risk Events to a standardized, high-priority out-of-band SMS dispatched via the Provider Adapter messaging gateway. The message must include: (1) an unambiguous threat indicator, (2) an explicit instruction not to disclose credentials or funds, and (3) an independent next step. Zero PII and no external clickable links. | P0 | Every alert uses a versioned template per Risk Event category. The threat indicator names the risky request (“caller wants a code”), never a fraud verdict (FR-15). The next step uses only a route the subscriber already has (the number on their card, a number they already have, the official app). Output-contract tests find no PII, URLs, phone numbers, emoji or curly quotes (either of the last two forces a non-GSM encoding and splits the message). Sent from one fixed sender ID. “High-priority” means a standard SMS dispatched immediately; a Class 0 flash cue is optional (P1) and never the only copy. |
| **FR-17** | Deliver the intervention via out-of-band SMS requiring zero subscriber app installation. The subscriber acts naturally by ending the voice call or referring to the received text advice. The delivery payload must be readable in under 5 seconds. | P0 | No app, browser, reply or tap needed to act on the advice. Core alert is at most 20 words in one 160-character GSM-7 segment, and its first line carries the warning on its own (visible in a lock-screen preview). Median read time under 5 s in the SM-09 timed check. Delivery receipt logged by message ID. An audible in-call cue for subscribers holding the phone to their ear is P1 (§11.2). |
| **FR-18** | *Retired in v1.3.* A post-call summary needs a subscriber UI, which the product no longer has; FR-23 covers follow-up. | — | — |
| **FR-23** | After a call that triggered an `action_warning`, send one stored follow-up SMS built only from the versioned Risk Event and Intervention: the risk category in plain language, the same independent next step, and reply keywords SHARED and WRONG (FR-26). It names the tactic the caller used and ends with the rule "Hang up, look up, call back" (templates in §19.5). | P0 | Sent after call end, at most once per call, and never for abstention outcomes; contains no transcript, audio, phone number or other PII; output-contract test rejects URLs, requests for codes or personal details, contact routes the subscriber doesn't already have, and any “you were scammed,” account-monitoring or reversal language. A follow-up-only opt-out (without stopping monitoring) is P1. |
| **FR-26** | Handle reply keywords sent from the subscriber's own number: YES (opt in, FR-03), SHARED (category-specific recovery steps for the last alert), WRONG (false-alert report), STOP (end monitoring and texts), HELP (what CallSafe is and how to stop it). Count replies by keyword and template in aggregate; store no free text. | P0 | Each keyword has a fixture and a template response; unrecognized replies get the HELP text; free-text replies are discarded after keyword matching; STOP and HELP follow standard messaging conventions **[GATE: G-05]**. Keyword normalisation, STOP variants and deduplication are specified in §19.4. |

**Messaging guardrails:** a security text that arrives right after a scam attempt looks a lot like a scam text, and once CallSafe is known, scammers will try to fake it. So every CallSafe text comes from one fixed sender, never asks for codes, passwords, money or personal information, contains no links or phone numbers, and points only to contact routes the subscriber already has. The invitation, enrollment and follow-up texts repeat the stop-and-check rule: *CallSafe only ever says stop and check. Any text saying a caller is fine, or asking for codes, money or info, is not us.* A text that follows this rule still proves nothing about who sent it. The rule works because the advice is safe even if forged: a fake that copies us gives safe advice, and a fake that says "go ahead" breaks the rule. The SHARED reply returns category-specific, independent steps: for a shared code, contact the organization through its official app or the number on your card and change the related password there; for remote access, disconnect the device from the internet and then contact the organization. No text claims that CallSafe or T-Mobile can reverse, monitor or report anything on the subscriber's behalf. Messages are template-only; they need no model and no stored content.

**Illustrative policy (not learned truth):** an explicit request to share an OTP yields a high-risk *behavior* alert even if voice authenticity is unknown. A high Voice Evidence score alone causes no fraud warning. A context-dependent payment request can trigger verification advice if the intent model plus rules provide enough evidence; otherwise abstain. False positives and missed threats drive changes to thresholds, not intuition. Cases where CallSafe sends nothing are listed in §8.2.

### 4.5 Operator console, governance and measurable evals

**Description:** The operator console is the product's only UI. It lets T-Mobile's fraud and scam protection team run the service and the verification lifecycle (§8) without storing or viewing sensitive conversations. Each console view is a thin layer over artifacts the eval harness and policy repository already produce. Realizes UJ-04 and UJ-05.

| ID | Requirement | Priority | Testable acceptance |
|---|---|---|---|
| **FR-19** | Operator console, protected by a single operator credential, shows only aggregates, template IDs and synthetic scenario metadata. Role-based access is deferred to pilot. | P0 | Unauthenticated requests return 401; test PII, phone numbers and SMS bodies absent from all responses. |
| **FR-20** | Run repeatable comparative evaluations of four arms (A reputation-only, K keyword-only, B deterministic, C full; §9.2) on sealed held-out batches authored independently of the rules (H1 for V3, H2 reserved for the first V5 promotion; §9.1), with policy frozen before each scored run. | P0 | One command emits confusion matrices, denominators, latency distributions, policy version, held-out batch hash, and run/config IDs. |
| **FR-21** | Expose health metrics: session count, active streams, queue depth, model invocation rate, SMS dispatch latency and delivery receipts, drops, errors and latency by stage. | P0 | Load test records metrics at 1 and 10 simulated concurrent sessions (P0); 50 and 100 sessions if time allows (P1). |
| **FR-22** | Provide clear attribution to existing infrastructure/model components and explain only the original integration, policy, UX and measured lift as team contribution. | P0 | Demo credits show model/source/provider names and licenses; slide uses measured rather than invented improvement. |
| **FR-24** | Show V1–V5 on a gate board: for each gate, its exit evidence (linked artifacts such as the grounding pack, frozen evaluation spec, eval reports, audit export), pass/fail against the criteria in §8, owner and date. Export the board, eval reports and policy history as one audit-ready report. | P0 | A gate can't show “passed” without linked evidence; the export is one document with run IDs and policy versions. |
| **FR-25** | Manage policy versions (rules, lexicons, triggers, thresholds, SMS templates) as versioned artifacts. A new version is promoted only after development-set evaluation, a passing V3 run on a sealed held-out batch it was never tuned on, and operator approval. Every promotion records who, when, why and the evidence. No automatic promotion, including by any agent. | P0 (one promotion demonstrated) | Console blocks promotion without a passing sealed-batch run and approval; audit entry includes old and new version, run IDs and approver; rollback restores the previous version and is tested once. |
| **FR-27** | Compare live (in the demo, replayed) alert rate per 100 monitored calls, trigger rates, category mix and WRONG-reply rate against the V3 baseline, and flag values outside configured bands for analyst review. | P0 (display); P1 (paging) | An injected shift in a replay batch raises a flag on the console; flags link to aggregate counts only. |

## 5. Non-goals and safety boundaries

- **No** general capability to intercept ordinary subscriber phone audio without authorized carrier-side or VoIP routing.
- **No** recording or analyzing real customer calls without appropriate permission, notice and legal review.
- **No** subscriber app, browser page or in-app UI; subscribers interact only through calls and SMS.
- **No** final “the caller is safe,” “the voice is human,” “this is definitely a scam” claim.
- **No** sending live OTPs, SSNs, phone numbers, medical records or financial information to third-party general-purpose LLM services.
- **No** call blocking/termination solely because a model assigns a high risk score.
- **No** CallSafe text that says a caller is safe or that the subscriber was scammed, asks for information, contains links or phone numbers, or implies account monitoring, transaction reversal or reporting on their behalf.
- **No** monitoring of calls the subscriber placed (outbound) in v1 (§8.2).
- **No** model or agent that changes live policy on its own; every policy change needs operator approval (FR-25).
- **No** new foundational multimodal training; no dependency on one untested “universal” voice model.
- **No** image phishing, attachment malware scanning, SMS/email phishing detection, payment reversal, real-time bank verification, or automatic incident reporting in the hackathon MVP.
- **No** unsupported claims of T-Mobile endorsement, access to internal APIs, general device coverage, scale readiness, or reduction of real customer fraud losses.

## 6. MVP boundaries and release plan

**v1.4 override:** for the hackathon build, the must-work scope, stretch order and cuts are §19.2, and the slip plan is §19.10. "P0 items are never cut" no longer applies, and real SMS has a labelled simulated fallback. The lists below are kept as the full product scope.

**P0 — Must demo [DECIDED]:** (a) Mock Reputation Signal adapter; (b) reproducible synthetic call replay through the same ingestion interface a live call would use; (c) opt-in and STOP by reply keyword; (d) incremental transcript; (e) Python Risk Event detection with negation and dialogue context; (f) existing Intent Evidence model with triggers T1–T3; (g) versioned Policy Engine; (h) real alert SMS and follow-up SMS to a team-owned test phone through an SMS API behind the messaging gateway (FR-16/17/23); (i) reply keywords (FR-26); (j) credential-protected operator console with gate board, policy history and drift/feedback panel (FR-19/24/25/27); (k) A/K/B/C evaluation on sealed batch H1, with counter-metrics, privacy log test and 1/10-session load test; (l) one gated policy promotion scored on sealed batch H2 (V5); (m) attribution; (n) lightweight comprehension check with timed reading (SM-09).

**P1 — Built only after the P0 slice runs end to end [DECIDED]:** Screening Proxy (FR-04/05); real controlled Twilio call; audible in-call cue; Class 0 flash cue, paired with the stored SMS and tested on demo handsets; Voice Evidence model (FR-10, also subject to the Gate 0 kill criterion); Nemotron policy-improvement agent (§6.1); follow-up-only opt-out; drift paging; 50/100-session load tests; usability study (SM-03); real authorized sandbox reputation endpoint (depends on G-01). Failure to complete P1 must not be disguised as a carrier integration.

**Cut order when behind schedule [DECIDED]:** drop P1 items in this order:
1. Screening Proxy, since it isn't a differentiator (§1.3) and adds telephony risk.
2. Live Twilio call and audible in-call cue, since replay and real SMS demonstrate the same pipeline.
3. Class 0 flash cue.
4. Voice Evidence model.
5. Nemotron policy-improvement agent.
6. Usability study.
7. 50/100-session load tests, drift paging and the follow-up-only opt-out.

P0 items are never cut. If P0 itself is at risk, shrink the held-out batches (H1 not below the 30/30 smoke test in §9.1) before dropping any arm, gate or counter-metric.

**Demo-critical path [DECIDED]:** four things must work flawlessly before any P1 work starts: (1) an OTP request after a benign introduction, with the alert SMS arriving on the test phone and the follow-up after hang-up; (2) one paraphrased case the rules miss, showing either a model-added alert or an honest abstention; (3) the benign clinic call with no text sent; (4) one gated policy promotion on the console. A polished, measured version of these beats a half-working full stack.

**Suggested build sequence (not a claim about schedule):**
1. **Gate 0 / kill test:** confirm the replay harness feeds the ingestion interface; confirm the Intent Evidence checkpoint loads and returns results on available hardware; run the Voice Evidence kill criterion (§4.3); send one alert SMS end to end to the test phone and check whether a Class 0 cue displays on it (§11.2); if P1 telephony will be attempted, validate the call topology in §11.2 and make the live-call go/no-go decision then. If it fails, stop live-call work; don't retry it the night before.
2. **V1 grounding pack** (§8.1).
3. **V2 evaluation spec frozen** (§8.2): contract tests and do-not-act fixtures written before the rules; development set and sealed batches H1/H2 authored.
4. **Vertical slice:** synthetic scenario -> ASR -> rules -> policy -> SMS -> console trace.
5. **Model slice:** Intent Evidence inference with triggers T1–T3; out-of-distribution fixtures; deterministic fusion. Add Voice Evidence and T4 only if it passed Gate 0.
6. **V3 validation** on H1 (§8.3), plus the comprehension check (SM-09).
7. **V4 instrumentation** (§8.4): gate board, monitoring, drift/feedback panel, audit export, reply keywords.
8. **V5 improvement cycle** (§8.5): one feedback-driven change promoted on H2.
9. **P1 extensions:** in reverse cut order, as time allows.
10. **Demo rehearsal:** legitimate callback, OTP theft after benign intro, family-impersonation paraphrase, inference overload, and the promotion. Rehearse the §9.4 answers until each one is short and non-defensive.

### 6.1 Sponsor tracks considered

| Sponsor track | Fit | Decision |
|---|---|---|
| NVIDIA — Nemotron beyond a chatbot | Strong if scoped to operators. A Nemotron agent in the console can run the V5 loop with tools: read aggregate feedback and drift flags, draft a policy change, run development-set evaluations, and write a promotion proposal for operator approval. Nemotron can also be benchmarked as an Intent Evidence candidate (§4.3). | Skip for the hackathon **[DECIDED, v1.4]**: not in §19.2 scope, and the Devpost deadline leaves no time. If revisited after the hackathon, the agent never promotes a change, never reads sealed held-out batches, never sees raw content, and never controls a live intervention. Brev credits can host it. |
| Photon API | Partial. Photon describes itself as infrastructure for AI agents in messaging apps and phone calls; we found no public detail on SMS or voice features. Its natural fit is the P1 Screening Proxy, an agent that answers and asks the caller's reason, which could target the voice-call prize. | Skip **[DECIDED, v1.4]**: the Screening Proxy is Out (§19.2). Don't use iMessage or other app channels for alerts: anyone can message there, which weakens the fixed-sender trust signal. |
| Capital One — Nessie | Weak. Mock bank accounts and P2P data would pull the product toward bank-account integration, which §5 rules out. | Skip. |
| Spacetime — main track and ScrabbleBot | None. The main track requires a majority SpacetimeDB backend, which conflicts with the T-Mobile-aligned stack story (§11.4); ScrabbleBot is unrelated. | Skip. |

## 7. Success measures and acceptance gates

**All thresholds below are proposed engineering/demo acceptance criteria, not observed performance or approved T-Mobile SLAs.** Keep denominators visible and report confidence intervals where feasible.

| ID | Metric / definition | Proposed hackathon target | Verifies |
|---|---|---|---|
| **SM-01** | Actionable scam recall = correctly warned high-risk scenarios / all labeled high-risk scenarios | Report for all arms. Headline comparisons are B vs K (value of context handling) and C vs B (value of models); A is shown for context only (§9.2) | FR-02/07/08/14/16/20 |
| **SM-02** | Additional actionable coverage = high-risk held-out scenarios missed by B but warned by C | At least one novel held-out category demonstrated, with counts; report zero or negative contribution as such | FR-10/11/12/20 |
| **SM-03** | Safe-action rate in usability simulation = users choosing independent verification or refusing disclosure / tested risky scenarios (P1) | Directional improvement vs baseline prompt; report sample size; make no claim if not run | FR-16/17 |
| **SM-04** | Policy reproducibility = identical decisions and SMS template outputs for fixed inputs and policy version | 100% regression-test agreement | FR-09/14/16/23 |
| **SM-05** | Alert latency = time from end of identifiable high-risk utterance to SMS dispatched by the messaging gateway; dispatch-to-handset time reported separately because it depends on the SMS provider and network | p95 <= 3 s to dispatch on controlled test setup, if feasible; report observed handset receipt times | FR-06/13/16/17 |
| **SM-06** | Privacy and access checks | 100% of unauthenticated console and unsigned provider requests rejected in scripted tests; no deliberately inserted test PII in persistent logs, console responses or SMS bodies | FR-01/03/09/16/19/23/26 |
| **SM-07** | Resilience under simulated concurrent sessions | Complete 1- and 10-session tests (P0) and 50/100 if time allows (P1); publish p95, drops, queue depth; no unsupported capacity claim | FR-13/21 |
| **SM-08** | Evaluation integrity = held-out batches authored by a non-rule-author, hashes recorded before the first scored run, policy version frozen, evidence linked for every gate decision, and every third-party component credited | 100% of reported runs traceable to a frozen policy version and held-out hash; any post-run tuning reported as such | FR-20/22/24 |
| **SM-09** | Comprehension check (P0, lightweight) = non-team testers who, after reading the alert SMS and the follow-up once on a phone, can state the safe next step / testers; plus median time to read the alert | Report n of m with 3–5 testers, including at least one outside the team's age group and technical background; median read time under 5 s (FR-17); if not run, drop accessibility claims from the pitch | FR-16/17/23 |
| **SM-10** | Improvement between policy versions = change in recall and hard-benign false alerts from the current to the candidate version on a sealed held-out batch neither was tuned on | Promote only if recall does not fall and hard-benign false alerts do not rise (proposed); report deltas with denominators. At hackathon sample sizes this is a no-regression check, not evidence of improvement | FR-20/25 |
| **SM-11** | SMS quality = alert word count and segments, templates passing the three-element check, delivery receipts logged | Alert at most 20 words in 1 GSM-7 segment with the warning in the first line; 100% of templates pass FR-16; 100% of demo alerts have a logged receipt | FR-16/17/23 |
| **SM-C01** | False alerts per 100 benign calls, reported separately for hard benign negatives (benign calls containing scam-associated keywords); each false `action_warning` also sends a false follow-up text | Headline metric alongside SM-01, reported for K, B and C; do not accept lift without understanding this cost | FR-08/15/20/23 |
| **SM-C02** | Legitimate-call interruption / screening abandonment | Report in scripted runs; screening abandonment only if FR-04 is built | FR-04/05/17 |
| **SM-C03** | Audio processed per call, inference cost per monitored minute, average model calls, SMS sent per 100 monitored calls | Lower is preferable subject to protecting recall | FR-12/13/21 |
| **SM-C04** | Differential missed threats / false alerts under channel noise, accents and accessibility scenarios | Report disaggregated slices without unsupported fairness claims | FR-06/10/11/20 |
| **SM-C05** | WRONG replies per 100 alerts (subscriber-reported false alerts) | Report; a rising rate is a V4 drift flag | FR-26/27 |

**Measurement discipline:** arm A is a **mock number-reputation comparison**, not actual T-Mobile deployment accuracy, and its recall depends entirely on how the team assigns mock reputation states to scenarios, so it is never a headline claim. Model deepfake accuracy must be reported separately from call-level scam-action detection. Do not equate a model's classification score or EER with the probability that a particular call is synthetic or fraudulent.

## 8. Gated verification lifecycle (V1–V5)

CallSafe adopts the five-step evaluation lifecycle the team was given (workflow grounding, eval-driven design, AI testing and validation, traceability and monitoring, continuous improvement) as five verification gates. A gate passes only when its exit evidence exists and meets its pass criteria; the operator console's gate board (FR-24) shows status and links the evidence. **“We are doing better” is a claim the gates must earn twice:** once against the baselines (V3), and again for every change against the version it replaces (V5). Pass criteria below are proposed team thresholds, not observed performance. **[DECIDED]**

### 8.1 V1 — Workflow grounding (real-world context for meaningful evaluation)

- **Map business processes and user personas:** subscriber journeys UJ-01–UJ-03, operator journeys UJ-04–UJ-05, and the call → Risk Event → SMS → reply flow (§11.1).
- **Identify data sources, systems and documents:** Provider Adapter interfaces (reputation, call media, messaging), the scenario library, the public documentation in §17, and each source's access status (mock, sandbox or real).
- **Capture policies, controls and decision logic:** the policy catalog (rule IDs, lexicons, triggers T1–T4, thresholds, SMS templates) with a one-line rationale per rule and template; consent states; non-goals (§5).
- **Define exceptions and human escalation points:** abstention, model unavailable, consent missing or revoked, do-not-act cases (§8.2), and an escalation matrix naming who reviews feedback clusters and drift flags, who approves promotions, and who is alerted for outages.
- **Exit evidence:** grounding pack (process map, persona list, data-source inventory, policy catalog v1.0, escalation matrix).
- **Pass when:** every FR traces to a journey (§16); every rule and template has a rationale; every exception has a defined, operator-visible outcome; every escalation point has an owner.

### 8.2 V2 — Eval-driven design (clear, measurable success criteria)

- **Set business-specific success criteria:** SM-01–SM-11 and SM-C01–SM-C05 with the targets in §7; headline comparisons B vs K and C vs B.
- **Define evaluation datasets and test scenarios:** the development set; sealed held-out batches H1 and H2 written by a non-rule-author (§9.1); hard benign negatives; codec-matched audio; multi-turn scripts.
- **Establish risk thresholds and guardrails:** policy thresholds and model budgets; FR-15 prohibited labels; the SMS content contract (FR-16/23); per-call message limits (one alert per Risk Event category and one follow-up per call).
- **Identify “do not act” scenarios.** CallSafe sends nothing when:
  - the only evidence is Voice Evidence or the Reputation Signal;
  - the risky phrase is negated or is itself a warning (“never share your code”);
  - the policy abstains or models are unavailable (no “safe” message either; rule-based alerts still go out);
  - the subscriber hasn't opted in or has sent STOP;
  - the subscriber placed the call. Outbound calls are excluded in v1 because a bank the subscriber called may legitimately ask for a code the subscriber just requested. Callback scams on outbound calls remain a known gap, partly covered by Scam Shield's Callback Protection.
- **Align with regulatory and enterprise policies:** consent and monitoring rules (G-03), messaging conventions for opt-in, STOP, HELP and sender identity (G-05), and the privacy design in §12.
- **Exit evidence:** frozen evaluation spec v1.0 (metrics and targets, batch hashes, do-not-act fixtures, contract tests), committed before rules are tuned.
- **Pass when:** every success measure has a target and a data source; every do-not-act case has a fixture; held-out hashes are recorded; contract tests exist and fail against an empty implementation, because the tests come first.

### 8.3 V3 — AI testing and validation (robust validation to move from pilot to production)

- **Test for accuracy, relevance and completeness:** A/K/B/C on H1 (§9.2); every alert SMS carries all three FR-16 elements.
- **Validate groundedness and evidence citation:** every alert and console entry cites its basis (rule ID or trigger, policy version, template ID); no SMS is sent without a Risk Event behind it.
- **Assess policy and compliance adherence:** consent tests, reply-keyword tests, and output-contract tests (no PII, links, phone numbers or verdicts).
- **Evaluate safety and risk behavior:** hard-benign false alerts (SM-C01), do-not-act fixtures, overload and degraded mode (never “safe,” never a dropped call), and the Voice Evidence kill criterion (§4.3).
- **Test multi-turn and agent workflows:** benign-then-dangerous calls, negation across turns, and paraphrases. If the Nemotron agent is built (§6.1), test its tool use: it can propose changes and run development-set evaluations but cannot promote or read sealed batches.
- **Exit evidence:** eval report from one command (FR-20) with run IDs, policy version and held-out hash.
- **Pass when (proposed):** B's recall is at least K's with fewer hard-benign false alerts; 100% of contract, consent and do-not-act tests pass; SM-04 is at 100%; C is kept only if it meets the “lead with rules” test (§4.3). A failed V3 isn't hidden: it changes what we pitch (for example, rules only).

### 8.4 V4 — Traceability and monitoring (lifecycle visibility and governance)

- **Monitor performance and quality:** per-stage latency, SMS dispatch and delivery receipts, alert rate per 100 monitored calls (FR-21).
- **Detect bias and drift:** SM-C04 slices; drift flags on alert rate, trigger rates, category mix and WRONG-reply rate against the V3 baseline (FR-27).
- **Ensure explainability and traceability:** each intervention traces Risk Event → rule or trigger → policy version → template ID → SMS message ID → delivery receipt, with no content stored.
- **Track usage, feedback and incidents:** reply-keyword counts (SHARED, WRONG, STOP), opt-ins and opt-outs, degraded-mode incidents.
- **Provide audit-ready reports:** one export of the gate board, eval reports and policy history (FR-24).
- **Exit evidence:** the console showing replayed-traffic metrics, one intervention traced end to end, and an audit export.
- **Pass when:** a reviewer can trace any demo alert from its SMS message ID back to its rule and policy version without seeing content; an injected drift batch raises a flag; the export opens as one document.

### 8.5 V5 — Continuous improvement (a self-improving, trusted system)

- **Use evaluation results and production feedback:** WRONG-reply clusters, drift flags and V3 misses become candidate changes. In the hackathon, feedback comes from scripted test phones.
- **Refine prompts, models and workflows:** changes are versioned policy edits (rules, lexicons, triggers, thresholds, templates) or model swaps.
- **Incorporate human review and domain expertise:** an analyst reviews every candidate; only an operator can promote (FR-25).
- **Update test cases and guardrails:** each false alert or miss becomes a regression fixture before the fix is written.
- **Drive ongoing performance and business impact:** promotion requires SM-10 on a sealed batch the candidate was never tuned on (H2 for the first promotion; later promotions need fresh batches).
- **Exit evidence:** one promoted policy version with its audit record and SM-10 result.
- **Pass when:** the candidate meets SM-10; the audit record names the approver, evidence and rollback version; rollback has been tested once.
- **v1.4:** in the hackathon, promotion is a stretch workflow demonstration on H1 reused (labelled), reported as "no regression observed on n=...", never as proof of improvement. H2 is dropped.

### 8.6 Evaluation dimensions map

| Dimension | How CallSafe measures it | Where |
|---|---|---|
| Business correctness | Right action on the right calls: alerts on risky requests, stays silent on benign calls and do-not-act cases | SM-01, SM-C01, §8.2 |
| Accuracy & quality | Precision, recall and FPR for every arm; three-element SMS completeness | SM-01, SM-02, SM-11 |
| Groundedness & evidence | Every SMS and console decision cites rule or trigger, policy version and template | FR-09, FR-14, SM-04 |
| Policy compliance | Consent, output contract, reply-keyword handling | FR-03, FR-15, FR-16, FR-26, SM-06 |
| Safety & risk | Hard-benign false alerts, do-not-act fixtures, degraded mode never says “safe” | SM-C01, FR-13, NFR-03 |
| Bias & fairness | Slices by channel noise, accent and accessibility scenario; age and geography never used as risk signals | SM-C04, §2.1 |
| Explainability & traceability | Risk Event → policy → template → message ID chain; audit export | FR-24, FR-25, NFR-07 |
| Human escalation | Abstention sends nothing; feedback clusters and drift flags go to an analyst; every promotion needs an operator | FR-25, FR-27, §8.1 |
| Performance & reliability | Latency to dispatch, delivery receipts, load tests | SM-05, SM-07, SM-11 |
| Drift detection | Alert, trigger, category and WRONG-reply rates against the V3 baseline | FR-27, SM-C05 |

### 8.7 Release ladder

| Stage | Required |
|---|---|
| Hackathon demo | Gate 0; V1–V3 passed on H1; V4 instrumented on replayed traffic; one V5 promotion on H2 |
| Pilot | V1–V5 passed on pilot-representative data, plus external gates G-01–G-07 (§15) |
| Production | Out of scope for this PRD |

## 9. Evaluation plan and judge demonstration

### 9.1 Controlled dataset

Use only team-authored synthetic scripts, consented voice recordings, and properly licensed evaluation datasets. Never use real customer conversations. Pass all replay audio through an 8 kHz μ-law round trip so it matches telephony conditions. Include hard benign negatives, meaning legitimate calls that contain scam-associated keywords (e.g., a bank or clinic warning a user *not* to share a code); aim for at least a third of benign calls. Include scam attempts by human (non-synthetic) speakers, and outbound-call scripts as do-not-act fixtures. Use held-out scripts, speakers, codec conditions and synthetic generator families to avoid leakage. Suggested minimum **smoke-test** for H1: 30 malicious-request and 30 benign calls; this sample is too small for a credible production accuracy claim. H2 may be smaller (at least 15 and 15, weighted toward the category being changed). **v1.4:** H2 is dropped for the hackathon; H1 needs at least 20 hard-benign calls, runs on scripted text, and is sealed by hash (§19.6). More varied blind holdouts are preferred when time permits.

**Held-out independence [DECIDED]:** to keep the rules from simply fitting the team's own scripts:
- The held-out batches (H1 for V3, H2 sealed for the first V5 promotion) are written by a team member who doesn't write rules, lexicons, triggers, templates or policy thresholds, and rule authors don't see them before the scored run.
- Rules, lexicons, triggers and thresholds are tuned only on a separate development set.
- Before the first scored run, record each batch's hash and freeze the policy version.
- Any change made after a scored run is either evaluated on a fresh held-out batch or reported as tuned on test data. A batch used to score a promotion is retired from future promotion decisions.

### 9.2 Four controlled arms

- **A / Demo Baseline:** same mock Reputation Signal and established routing logic; no CallSafe speech intelligence. Its recall reflects how mock reputation states were assigned, so it is shown for context only.
- **K / Keyword Baseline:** A plus ASR and the same request keyword lists that B's rules use, with no negation, context or dialogue state; any keyword hit warns. This is the strong naive comparator.
- **B / Deterministic:** A plus ASR, Risk Events, stateful Python rules and policy.
- **C / Full:** B plus the Intent Evidence model (and Voice Evidence, if it passed Gate 0), triggers T1–T4 and evidence fusion.

Run *the same* held-out scenarios through all arms; report TP, FP, FN, TN, precision, recall, FPR, warning latency, cost, and hardware. **Headline comparisons:** B vs K shows what context handling buys, C vs B shows what the models buy, and hard-benign false alerts (SM-C01) show the cost. Include model ablations (C without the intent model; C without the voice model, if built) to identify actual contribution. Flag any weak model whose incremental value is zero or negative rather than manufacturing an improvement number.

### 9.3 Demo script (about 3-4 minutes; adjust to available time)

**v1.4:** the judging-table demo is the 3-minute loop in §19.1. The script below is the longer reference version for sponsor judges who ask for more.

The subscriber side of the demo is a real, team-owned test phone, shown on screen by camera or screen mirroring, receiving real texts. Replayed call audio plays aloud. The operator console is on the main screen.

1. **Context (15 s):** Show the console with the simulated reputation result “unknown,” not “safe.” The subscriber has no app; the fraud team runs everything from here; carrier routing is future work.
2. **Legitimate callback (30 s):** The clinic replay mentions a confirmation code while telling Ruth not to share it; the test phone stays silent.
3. **Benign then dangerous (75 s):** The bank-impersonation replay opens benignly, then asks for an OTP. The test phone buzzes with the alert SMS, and the console shows Rule ID -> Risk Event -> template -> SMS message ID -> delivery receipt. After the call ends, the follow-up arrives; reply SHARED on the phone and the recovery steps come back.
4. **Unseen variation (40 s):** A family-emergency paraphrase evades the rules; the T2 trigger invokes the intent model and the alert SMS arrives. Then an abstention case: nothing is sent. If Voice Evidence passed Gate 0, show “voice authenticity uncertain” in the console as supporting context only.
5. **Evidence and limits (50 s):** The gate board shows V1–V5 with evidence links. Show A/K/B/C numbers led by B vs K, C vs B and hard-benign false alerts. Then the promotion: WRONG replies cluster on one rule, policy v1.1 is scored on H1 reused, labelled as such (SM-10; H2 dropped, §19.6), the operator approves, and the audit record appears. Show degraded mode in one click.
6. **Close (20 s):** “We don't replace Scam Shield or on-device protection. Calls that pass number filters can still turn into a request for a code or a transfer; we catch the request, text one independent next step to any phone, and follow up afterward. Our numbers are against our own baselines only; lift over Scam Shield or Pixel would need carrier routing we don't have.”

**Replay framing:** label replayed calls on screen as “replayed call through the live ingestion path,” and never present replay as a live or carrier call. Use consented recordings of real voices at 8 kHz so the replay doesn't sound synthetic. If real SMS delivery fails at Gate 0, the console's phone-frame view labeled “simulated SMS” stands in, and the demo says so.

### 9.4 Hard questions and prepared answers

Fill bracketed values from the actual run and never round them up. If a number isn't available, say so rather than estimating. Rehearse until each answer takes under 20 seconds.

| Question | Prepared answer |
|---|---|
| How is this better than Pixel or Samsung on-device detection? | Pixel says "Likely scam" on some Android phones; we name the request, give a step that's safe even if we're wrong, teach the trick, and reach any phone, including iPhones. We haven't measured against those features; our numbers are against our own baselines only. |
| Doesn't T-Mobile Live Translation already do this? | It proves T-Mobile can run AI inside calls on any phone; we point that same path at scam requests. |
| Why should anyone trust AI with this? | Rules decide, the model never acts alone, every alert cites a rule ID, and the advice is safe even if we're wrong. |
| Isn't this just keyword matching? | That's why arm K exists. Keyword matching alone gave [K recall] recall and [K hard-benign false alerts] false alerts per 100 hard benign calls; our rules gave [B recall] and [B hard-benign false alerts]. |
| Does the model actually help? | On held-out paraphrases, the full pipeline added [C − B true warnings] warnings over the rules and [C − B false alerts] false alerts. [If not positive: it didn't help, so the rules are the product.] |
| How do you know a change is an improvement? | At our sample sizes we can only show it didn't regress: scored on held-out calls, recall didn't fall and false alerts didn't rise, and an operator approved it. [No regression observed on n=...]. |
| What's the false-alert rate on benign clinic, bank and pharmacy calls? | [SM-C01] per 100 on [N] held-out benign calls, [M] of which mention codes or payments. |
| Won't people miss a text while the phone is at their ear? | Some will. The text's vibration and tone are the in-call cue, the warning sits in the first line for the lock-screen preview, and a stored follow-up arrives after the call. An audible in-call cue is the P1 fix (§11.2). |
| Can't scammers fake a CallSafe text? | Yes, which is why our texts only ever say stop and check: a fake that copies us gives safe advice, and one that says "go ahead" breaks our one rule. In production, sender verification is a carrier gate (G-05). |
| Why not a flash (Class 0) message? | We may add one as an attention cue where phones support it, but never as the only copy: providers describe flash messages as not saved to the inbox, and one notes the sender isn't shown, which removes the fixed-sender trust signal. |
| What if T-Mobile never grants the API or routing? | Without audio routing the product doesn't run; it stays a prototype on replayed calls, and we've said so. Live Translation shows T-Mobile already routes call audio to network AI. The reputation feed is only supporting evidence. |
| Is listening to the caller legal? | Subscriber opt-in is necessary but not sufficient; caller notice in all-party-consent states is a gate before any real customer (G-03). |
| Why would anyone opt into carrier-side audio analysis? | Some people won't, and that's fine. It's opt-in by reply text, STOP ends it, and we store no audio, transcripts or raw numbers (only consent state and counts), but it is a real privacy cost compared with on-device processing (§12). Whether enough people opt in is unproven (G-07). |
| Is the call we just saw live? | No. It's a replayed recording sent through the same ingestion path a live call would use; the text on the phone is real. [If the P1 live call works: show it and say which parts are live.] |

## 10. Cross-cutting nonfunctional requirements

| ID | Domain | Requirement / test expectation |
|---|---|---|
| **NFR-01** | Latency | Measure ASR, rule, model queue, fusion and SMS dispatch latency separately; provisional p95 goal in SM-05. |
| **NFR-02** | Throughput | Isolate each Monitoring Session; bounded async WebSocket ingestion; load-shed model requests independently of call routing. |
| **NFR-03** | Reliability | If models fail or become overloaded, show “enhanced analysis unavailable” in the console; rule-based alerts still go out; never claim safe or terminate a call. |
| **NFR-04** | Accessibility | Plain-language SMS with no emoji and the warning in the first line; texts inherit the phone's own accessibility settings (text size, screen readers); the operator console follows WCAG 2.2 AA contrast and target-size guidance, with no conformance claim without an audit. |
| **NFR-05** | Security | TLS, provider signature validation (call media and SMS webhooks), authenticated console and API (single operator credential in the demo; least-privilege roles before any pilot), short-lived secrets, immutable policy version in logs. |
| **NFR-06** | Privacy | No default persistent audio or transcript storage; ephemeral processing; PII removal before metrics; subscriber phone numbers used only to route SMS and never shown in the console or logs; notice/consent and data-flow review for live calls. |
| **NFR-07** | Observability | Per-stage timing, queue length, dropped segments, inference failures, SMS message IDs and delivery receipts, and privacy-safe trace IDs. |
| **NFR-08** | Portability | Dockerized Python services; Provider Adapter boundary for reputation, call media and messaging; no single cloud dependency in policy/business logic. |
| **NFR-09** | Repeatability | Fixed model hashes/configs/seed where supported, dataset version, held-out batch hashes recorded before scoring, scenario labels, threshold and template versions, and reproducible eval command. |
| **NFR-10** | Messaging | One fixed sender ID; at most one alert per Risk Event category and one follow-up per call; idempotent dispatch, so retries never send duplicate alerts; SMS dispatch never blocks call routing. |

## 11. Architecture and recommended stack

### 11.1 Logical data flow

```text
Synthetic replay (P0) / controlled VoIP call (P1)
          |
   Provider Adapter ----- Mock/authorized Reputation Signal
          |
   Screening Proxy (P1, optional, controlled route)
          |
   Authorized Monitoring Session ---------------> consent state (YES / STOP by SMS)
          |
   Transient audio buffer ----------------------> Anti-spoof model (P1, Gate 0)
          |                                            |
   Streaming ASR -> Python rules -> Risk Events        | Voice Evidence
          |                  |                         |
          +------------------+--- triggers T1-T4       |
                             |                         |
                      Intent model -> Intent Evidence  |
                             |                         |
                             +------------+------------+
                                          |
                                Versioned Policy Engine
                                          |
                              Intervention / abstention
                                          |
          Messaging gateway (Provider Adapter) -> alert SMS to subscriber
                                          |
          Follow-up SMS after hang-up; reply keywords back to the gateway
                                          |
   Redacted events + metrics -> Operator console (gate board, monitoring, promotion)
```

### 11.2 Implementation choices

| Concern | Preferred | Backup / caveat |
|---|---|---|
| Call demo | Synthetic replay through the same ingestion interface a live call uses (P0) | Twilio Programmable Voice + Media Streams (P1), only after the topology below is verified |
| Subscriber channel | SMS through an SMS API (e.g., Twilio Programmable Messaging) to a team-owned test phone, behind the messaging gateway (P0) | Class 0 flash cue if the provider and demo handset support it (P1); carrier SMS center in production |
| Backend | Python 3.11+, FastAPI (WebSockets for ingestion, webhooks for SMS replies and receipts), Pydantic v2 | Standard Python async functions for ingestion |
| Event bus | In-process queue behind a publish interface | Kafka-compatible broker (Apache Kafka or Redpanda in Docker Compose) if setup takes under an hour; Kafka in production (§11.4) |
| Transcription | Existing streaming ASR service or local packaged ASR | Pretranscribed replay for deterministic troubleshooting (clearly labeled) |
| Rules/policy | Python state machine + YAML/JSON versioned policy tables and SMS templates in git | No LLM control of final safety action |
| Acoustic model | Existing licensed AASIST-family checkpoint (candidate only; P1, cut if the Gate 0 kill criterion fails) | Alternative pretrained speech anti-spoof checkpoint after benchmark |
| Intent model | Existing licensed NLI checkpoint; self-hosted Nemotron as a second candidate on the NVIDIA track | Bounded LLM fallback only if absolutely necessary and permitted; not required for demo |
| Model serving | Single Docker service / background workers; GPU if available (Brev credits on the NVIDIA track) | CPU-suitable checkpoints or prerecorded model-inference fixtures labeled as simulation |
| State and audit | In-memory session state; SQLite for consent (salted hash of the number), aggregates, reply counts and policy history in the hackathon build (§19.3) | PostgreSQL and an audit log before any pilot |
| Operator console | React + TypeScript; the product's only UI | Minimal responsive browser app |
| Ops | Docker, GitHub Actions/pytest, Prometheus-compatible counters; Grafana optional | Basic metrics JSON if schedule tight |
| Evaluation | pytest + scikit-learn + CSV/JSON artifact; MLflow optional | Versioned local reports sufficient |
| Cloud | AWS or team-provided cloud credits; smallest workable deployment | One VM/container is preferable to Kubernetes |

**Telephony constraints [GATE] (P1 live call only; checked against Twilio documentation, §17):**
- **Audio format.** Media Streams deliver 8 kHz μ-law mono audio. Replay audio must match (§9.1), and any model must be evaluated at that quality (§4.3).
- **Ingestion.** A bidirectional stream (`<Connect><Stream>`) receives only the inbound track and blocks subsequent TwiML, so it cannot sit in front of a `<Dial>` bridge. A unidirectional stream (`<Start><Stream>`) can carry the inbound, outbound or both tracks and lets the next TwiML instruction (such as `<Dial>`) run, so it is the candidate for monitoring a bridged call. Confirm on the actual bridge which track carries which party.
- **Audible in-call cue (P1).** The P0 warning is an SMS, which doesn't depend on the call topology. An audible cue can't come from a unidirectional stream, which cannot send audio back into the call; it likely needs a conference-based topology, where an announcement can be played to the subscriber's participant leg, or a coaching participant can speak to the subscriber without the caller hearing. Validate this at G-05 before promising it.
- **Fallback.** If the live path fails validation, the demo uses replay plus real SMS, and says so.

**Messaging constraints [GATE]:**
- **Class 0 flash SMS.** Providers describe flash SMS as shown immediately but not saved to the inbox, with only the latest message visible, and one notes the sender isn't shown; handset support varies. It is offered by SMS API providers, so it isn't a carrier-only signal, and trust has to come from the fixed sender and content rules (§4.4). It is never the only copy and is tested on the demo handsets before use.
- **Sender setup.** US SMS from an API provider may need number registration or verification, and trial accounts may prefix messages or limit recipients. Check at Gate 0. If delivery to the test phone isn't reliable, the demo falls back to a phone-frame view in the console labeled “simulated SMS.”
- **Production.** Alerts come from the carrier's own SMS center with a fixed, published sender (G-05).

### 11.3 Policy and API contracts

**Provider Adapter input (illustrative):**
```json
{"call_ref":"ephemeral-demo-id","reputation_state":"unknown","verification_status":"unavailable","source":"mock","timestamp_ms":0}
```

**Risk Event (illustrative; no PII):**
```json
{"session_ref":"ephemeral-demo-id","event_type":"otp_disclosure_request","source":"rule","rule_id":"POL-OTP-01","span_start_ms":12500,"span_end_ms":15600,"confidence_class":"high","evidence_summary":"caller requested verification code","policy_version":"1.0"}
```

**Intervention SMS (illustrative; template `ALERT-OTP-01`):**
```json
{"level":"action_warning","channel":"sms","template_id":"ALERT-OTP-01","message":"CallSafe: caller is asking for a code. Don't share it. Hang up, call your bank's number yourself.","segments":1,"basis":["POL-OTP-01"],"certainty":"risk_pattern_detected","policy_version":"1.0"}
```

**Follow-up SMS (illustrative; template `FU-OTP-01`):**
```json
{"template_id":"FU-OTP-01","trigger":"action_warning","basis":["POL-OTP-01"],"message":"CallSafe: your caller asked for a code. Codes unlock your account; banks never ask. Hang up, look up, call back. Reply SHARED or WRONG.","reply_keywords":["SHARED","WRONG"],"policy_version":"1.0"}
```

**Reply keyword event (illustrative; no number or free text stored):**
```json
{"event":"sms_reply","keyword":"WRONG","template_id":"ALERT-OTP-01","policy_version":"1.0","counted":true}
```

**Permissions:** `/console/*`, `/events/aggregate` and `/health` require authenticated operator access (a single operator credential in the demo); `/call/session` and `/sms/inbound` accept only signed/validated provider events; promotion endpoints require an operator approval recorded in the audit log. API routes are provisional architecture contracts, not endpoints already deployed.

### 11.4 Production alignment with T-Mobile's public engineering signals

Team-compiled summaries of public T-Mobile job postings and engineering talks repeatedly mention Java/Spring Boot, Python and Node.js services; React/TypeScript and Angular front ends; Apache Kafka; Docker and Kubernetes; AWS (with Azure and GCP); GitLab CI, Terraform and Helm; HashiCorp Vault; and Prometheus/Grafana. These are signals from public postings, not confirmed internal standards **[ASSUMPTION]**. The hackathon build is designed to map onto them without rework:

| Hackathon component | Production mapping |
|---|---|
| Python FastAPI ingestion, rules and policy services | Same services containerized on Kubernetes, or ported to Spring Boot where platform standards require it; policy tables, templates and contracts carry over unchanged |
| In-process queue or Kafka-compatible broker | Kafka topics such as `risk-events`, `interventions`, `sms-dispatch`, `sms-replies` and `audit` |
| SMS API behind the messaging gateway | Carrier SMS center behind the same gateway interface |
| Mock Reputation Signal | Network reputation signal through the Provider Adapter (G-01) |
| Docker model serving | Kubernetes or managed inference endpoints (e.g., SageMaker), with model hashes pinned |
| React operator console | Same app behind enterprise single sign-on with role-based access |
| PostgreSQL aggregates and audit log | Enterprise data platform with an immutable audit store |
| GitHub Actions and environment secrets | GitLab CI, Terraform/Helm, Vault |
| Prometheus-compatible counters | Prometheus/Grafana and existing alerting |

If the team has a Java developer, building the messaging gateway as a small Spring Boot service is a cheap way to show alignment; otherwise keep it in Python behind the same interface.

## 12. Privacy, security and legal constraints

**Data classes:** caller/customer numbers, email, SSN, voiceprints, call content, medical or financial context, and account identifiers are sensitive. Telephone audio and transcripts themselves can contain PII even when the displayed event is redacted.

**Required design:** consent and notice are stateful; only controlled/consented audio enters the pipeline; audio is kept in short-lived memory where feasible; transcript snippets are processed transiently; raw content is not retained by default; alert and follow-up texts carry only the risk category and next step; subscriber phone numbers are used only to route SMS and are never shown in the console or written to logs; reply text is discarded after keyword matching; metrics use non-reidentifying synthetic run IDs, not merely unsalted hashed phone numbers; console access is limited to the operator credential in the demo and to least-privilege roles before any pilot; logs never include credentials or transcript content. SMS bodies transit the SMS provider; in the hackathon they contain only template text sent to team-owned phones. A documented deletion/retention matrix must exist before any real pilot.

**[GATE] Legal review** is required for recording/monitoring consent, telecom interception/wiretap rules, jurisdictions of all parties, vendor subprocessors, data residency, healthcare-adjacent content, messaging rules for carrier-originated texts (opt-in, opt-out keywords, sender identity) and access procedures. Subscriber opt-in is necessary but not sufficient: the caller is analysed too, and all-party-consent states (for example Washington, RCW 9.73.030) require more. Real use is gated on counsel-approved caller notice and jurisdiction handling (G-03); such a notice may also warn scammers off. Call content should not simply be labelled CPNI; CPNI treatment of carrier metadata needs separate review. **[GATE] Production security review** is required for provider signature validation, threat modeling, audit evidence and incident response. Any sensitive data inadvertently received by a demo must be discarded, not treated as an evaluation sample.

**Privacy tradeoff vs smartphones:** existing on-device protections may keep audio on the handset. A carrier-side cloud model may increase exposure and infrastructure cost. CallSafe cannot claim superior privacy simply because it is carrier-operated. This is a potential competitive disadvantage to be measured and mitigated.

## 13. Risks, mitigations and failure modes

| Priority | Risk | Mitigation / evidence required |
|---|---|---|
| Critical | No legal access to call media or internal T-Mobile endpoint | Mock adapters + controlled VoIP/replay, clearly disclosed; do not claim production integration |
| Critical | PII/medical/financial audio processed without adequate consent | Explicit consent state, test-only synthetic inputs, legal gate, no default raw-data retention |
| High | Hackathon scope overrun | P0/P1 split, P1 built only after P0 runs end to end, explicit cut order, console views built over existing artifacts (§6) |
| High | Rules overfit to team-authored scripts, inflating results | Independent held-out authorship, development/held-out split, policy freeze and batch hashes before scoring (§9.1, SM-08) |
| High | A policy change makes things worse | V5: sealed-batch evaluation (SM-10), operator approval, tested rollback (FR-25) |
| High | Human scammer evades spoof detector | Detect harmful requests independently of Voice Evidence |
| High | Caller opens with a benign introduction, then scams later | Opt-in Monitoring Session; post-intro test scenario (UJ-02) |
| High | Benign OTP-related conversation triggers panic | Negation/context tests, high-specificity rules, hard benign negatives in the held-out batches, K-vs-B comparison, do-not-act fixtures (§8.2), false-positive counter-metrics |
| High | Legitimate code request on a call the subscriber placed | Outbound calls excluded in v1 (§8.2); callback-scam gap documented |
| High | Subscriber doesn't see the alert while the phone is at their ear | Vibration and tone as the in-call cue; warning in the first line for lock-screen previews; stored follow-up after the call; audible in-call cue (P1) |
| High | CallSafe texts look like phishing or get spoofed by scammers | One fixed sender; no links, numbers or requests for codes, money or info; texts only ever say stop and check, so a fake that copies us gives safe advice and one that says "go ahead" breaks the rule; enrollment texts teach this rule; carrier sender verification in production (G-05); output-contract tests (FR-16/23) |
| High | Older/low-tech subscriber cannot use the warning | Plain-language SMS that works on any phone, warning in the first line, comprehension check (SM-09), usability study (P1) |
| High | Important legitimate call delayed/blocked | No pre-answer screening in P0; if the Screening Proxy is built, soft screening, timeout/bypass, allowlist/contacts as permitted, measure abandonment |
| High | Voice model fails on 8 kHz telephone audio or unseen generators | Codec-matched Gate 0 test with kill criterion (§4.3), out-of-distribution test, insufficient-audio state; rules and intent pathway don't depend on it |
| High | Full pipeline underperforms the rules in ablation | Lead with rules (B) as the product; present the model as an experiment with its real numbers (§4.3) |
| High | Inference saturation at peak traffic | Bounded queue, independent CPU rules, shed model jobs, visible degraded mode |
| Medium | SMS sending blocked or delayed by provider registration or trial limits | Check at Gate 0; fallback to a labeled simulated-SMS view in the console (§11.2) |
| Medium | Class 0 flash SMS unsupported, not stored, or shown without a sender | Standard SMS is the P0 channel and always sent; Class 0 is an optional extra cue, tested on demo handsets first |
| Medium | Audible in-call cue not deliverable inside a bridged call | SMS is the P0 channel; conference topology validated at G-05 before any audio-cue claim |
| Medium | Improvement agent (P1) oversteps | Agent proposes only; no promotion rights, no sealed-batch or raw-content access; tool-use tests in V3 |
| Medium | Feature already exists in Google/Samsung/Apple | Focus on carrier coverage/verified signal + action outcome; measure against device feature when possible |
| Medium | “X% better” is artifact of easy, scripted data | Keyword-only arm K as a strong naive comparator, sealed held-out batches, ablation tests, denominators and confidence caveat; no fabricated gains |
| Medium | Healthcare scenario suggests medical-data processing | Use fabricated scripts only; no patient records or EHR integration |

## 14. Business rationale and pilot pathway

**Potential value [ASSUMPTION]:** incremental avoidance of harmful disclosures, fewer unsupported fraud incidents, more equitable access to call protections (including basic phones), and increased trust in network-level safety services. **No ROI, savings, conversion, retention, or fraud-loss improvement is currently established.** The business case requires call-volume distribution, eligibility/opt-in rates, processing and SMS cost, false-intervention support cost, measured customer behavior and ability to integrate with existing carrier products.

**How the gates support the business case:** V1–V5 are the pilot entry criteria, which shortens the path from pilot to production review. V2 guardrails and V3 safety tests reduce operational, regulatory and reputational risk. The V4 audit trail gives governance and stakeholders a record of every decision and change. V4 monitoring and V5 regression fixtures keep performance from silently degrading as scam scripts change. None of these is a measured outcome yet.

**Pilot prerequisites:** carrier-sponsored routing/sandbox access; signed privacy, legal and security approvals; independent model evaluation; accessibility testing with representative volunteers; documented on-call and rollback; cost per screened call and per alert; explicit definition of the incumbent comparator (actual T-Mobile, eligible Pixel/Samsung features, or combination). A small, opt-in, controlled pilot precedes any broader rollout.

**Pilot decision:** proceed only if the intervention improves safe behavior or missed-scam detection *without unacceptable false alarms, latency, privacy tradeoffs or lost legitimate calls.* If not, the recommended result is to stop or narrow to an accessibility/verification aid rather than claim a detection breakthrough.

## 15. Unresolved dependencies and approval gates

| Item | State | Required resolution / owner |
|---|---|---|
| G-01: T-Mobile internal risk/verified-number API availability | **Unavailable to the team** | T-Mobile has this internally, but the team can't get access for the hackathon. The Reputation Signal stays a mock adapter (§19.4) and is said so in the pitch. A pilot needs sandbox access, contract, fields, quotas and authorization from the carrier sponsor |
| G-02: Authorized controlled-call route for live monitoring (P1; P0 uses replay) | **Open** | Verify unidirectional-stream track mapping on the actual bridge, caller notice and bridge behavior (§11.2); telephony lead |
| G-03: Consent, privacy, sector/legal review | **Open** | Security/privacy/legal approval before non-synthetic calls, including caller notice in all-party-consent states and a data-retention matrix |
| G-04: Licensed pretrained checkpoints and hardware | **Open** | Test exact weights/license and benchmark speed; run the 8 kHz Voice Evidence kill criterion (§4.3); ML lead |
| G-05: Subscriber messaging and warning delivery | **Open** | P0 sends real SMS to team-owned test phones through an SMS API. For real subscribers: carrier-originated sender identity and verification, opt-in/STOP/HELP compliance, Class 0 behavior on supported handsets, and (P1) the audible in-call cue topology; UX/telephony lead |
| G-06: Model and user outcome benchmark | **Not yet executed** | Publish A/K/B/C results and the V5 promotion result (SM-10) from frozen policies on sealed held-out batches, with false positives and non-determinism; evaluation lead |
| G-07: Device coverage, opt-in and carrier cost assumptions | **Unverified** | Carrier product owner must scope eligible populations, likely opt-in, and cost per monitored minute and per alert |

**Build-ready determination:** the **mocked, controlled hackathon vertical slice is specified enough to implement**. **Carrier production implementation is not approved or represented as ready.**

## 16. Decision register and traceability

- **D-01 [DECIDED, revised v1.3]:** Subscribers interact only through calls and SMS; operators work entirely in the console; not a call-center agent tool.
- **D-02 [DECIDED]:** Primary protection is action-based Python rules plus deterministic policy; phone-number reputation is supporting evidence.
- **D-03 [DECIDED, revised v1.1]:** Two separate pretrained model pathways, evaluated independently: Intent Evidence (P0) and Voice Evidence (P1, kept only if it passes the Gate 0 kill criterion).
- **D-04 [DECIDED]:** No model training from scratch; one multimodal model may be benchmarked, not adopted without evidence.
- **D-05 [DECIDED, revised v1.1]:** The opt-in Monitoring Session after answer is the core capability; the pre-answer Screening Proxy is optional P1 and first in the cut order. Both apply only where media routing is authorized.
- **D-06 [DECIDED]:** Warn with an independent safe next step; never declare identity or authenticity conclusively.
- **D-07 [DECIDED, revised v1.1]:** Quantify incremental improvement and false-alarm harm; compare A/K/B/C with B vs K and C vs B as headline comparisons; credit third-party tools.
- **D-08 [DECIDED]:** Rural/older-customer accessibility and minimal friction are primary requirements.
- **D-09 [DECIDED]:** Image-malware scanning excluded from this MVP.
- **D-10 [ASSUMPTION]:** A carrier-operated version could protect more devices; needs integration rights and coverage evidence.
- **D-11 [DECIDED]:** P0 is the replay-driven vertical slice plus evaluation; P1 is built only after P0 runs end to end and is cut in the order in §6.
- **D-12 [DECIDED, revised v1.3]:** The P0 warning surface is an SMS to the subscriber's phone; audible in-call cues are P1 behind G-05.
- **D-13 [DECIDED]:** Held-out batches are authored independently of the rules, with policy frozen and batch hashes recorded before scoring.
- **D-14 [DECIDED]:** Models run only through versioned triggers T1–T4 (FR-12).
- **D-15 [DECIDED]:** The demo console uses a single operator credential; role-based access is deferred to pilot.
- **D-16 [DECIDED, revised v1.3]:** Close the loop with a template-only follow-up SMS after `action_warning` (FR-23); real SMS to a test phone is P0.
- **D-17 [DECIDED]:** Lead with rules. If the intent model doesn't beat B on held-out paraphrases, B is the product and the model is presented as an experiment.
- **D-18 [DECIDED]:** Accessibility claims in the pitch require the SM-09 comprehension check; otherwise they are dropped.
- **D-19 [DECIDED]:** Five verification gates V1–V5 (§8) govern every claim and every policy change; the gate board is the source of truth.
- **D-20 [DECIDED]:** FR-16 and FR-17 adopted as worded by the team: a standardized out-of-band SMS with a threat indicator, a do-not-disclose instruction and an independent next step; no PII or links; readable in under 5 seconds.
- **D-21 [DECIDED]:** Standard SMS from one fixed sender is the alert channel; Class 0 flash is an optional P1 cue and never the only copy.
- **D-22 [DECIDED]:** Outbound (subscriber-placed) calls are excluded from monitoring in v1.
- **D-23 [DECIDED]:** Policy changes are promoted only through V5 with operator approval; no automatic promotion, including by any agent.
- **D-24 [DECIDED, revised v1.4]:** Sponsor tracks: T-Mobile challenge only. NVIDIA, Photon, Nessie and Spacetime are skipped (§6.1).
- **D-25 [ASSUMPTION]:** The hackathon architecture maps onto T-Mobile's publicly signaled stack (§11.4).
- **D-26 [DECIDED]:** FR-18 (post-call summary) retired; there is no subscriber UI to host it, and FR-23 covers follow-up.

**Traceability:** UJ-01 -> FR-02/03/04/05/07/08/15/26; UJ-02 -> FR-01/03/06/07/08/09/14/16/17/23/26; UJ-03 -> FR-01/06/10/11/12/13/14/15/16/17; UJ-04 -> FR-09/19/20/21/22/24/27; UJ-05 -> FR-20/24/25/26/27. Every active FR maps to at least one journey (FR-18 is retired), and every success measure in §7 names the FRs it verifies. Open gates G-01 through G-07 are not silently treated as decisions.

## 17. External sources and attribution

Public sources reviewed November 7, 2026. These support descriptions of existing products and integration constraints, **not measured CallSafe results**.

1. BMAD Method, PRD template / essential spine: https://github.com/bmad-code-org/BMAD-METHOD/blob/main/skills/bmad-prd/assets/prd-template.md
2. BMAD Method, skills and agents / PM and validation workflow: https://docs.bmad-method.org/reference/skills-and-agents/
3. T-Mobile Scam Shield and call protection: https://www.t-mobile.com/benefits/scam-shield and https://www.t-mobile.com/business/solutions/call-protection
4. Google, on-device Scam Detection and expansion to Samsung: https://blog.google/security/staying-one-step-ahead-strengthening-androids-lead-in-scam-protection/
5. Apple, iPhone screening and call identification: https://support.apple.com/guide/iphone/screen-and-block-calls-iphe4b3f7823/26/ios/26
6. Twilio, Media Streams overview (track options, bidirectional limits): https://www.twilio.com/docs/voice/media-streams
7. Twilio, Media Streams WebSocket messages (8 kHz μ-law audio format): https://www.twilio.com/docs/voice/media-streams/websocket-messages
8. Twilio, Voice Conference (participant announcements, coaching): https://www.twilio.com/docs/voice/conference
9. Infobip, Flash SMS glossary (display and storage behavior): https://www.infobip.com/glossary/flash-sms
10. 46elks, Flash SMS tutorial (2018; storage and sender display): https://46elks.com/tutorials/flash-sms
11. Photon, weekly update (product description): https://photon.codes/weekly-update/may-14-2026
12. AASIST research / architecture: https://arxiv.org/abs/2110.01200
13. Speech SSL anti-spoofing research: https://arxiv.org/abs/2202.12233
14. Generalization caution in audio deepfake detection: https://arxiv.org/abs/2203.16263
15. ASVspoof 5 context: https://arxiv.org/abs/2408.08739
16. T-Mobile Live Translation beta (network-native in-call AI, \*87, any phone): https://androidcentral.com/phones/t-mobile/t-mobile-network-native-ai-live-translation-beta-just-the-start and https://www.droid-life.com/2026/05/21/t-mobile-live-translation-beta-is-now-live/
17. Hiya AI Phone (scam protection with call summaries): https://blog.hiya.com/introducing-hiya-ai-phone-revolutionizing-your-phone-conversations
18. Aura service terms and Trusted Family Access (2026-09-17): https://www.aura.com/legal/service-terms and https://www.aura.com/press/release/new-feature-to-help-protect-senior-adults-from-online-crime
19. Google Scam Detection help ("Likely scam" alert): https://support.google.com/phoneapp/answer/15654065?hl=en
20. Twilio trial account restrictions: https://help.twilio.com/articles/360036052753
21. Washington all-party consent statute, RCW 9.73.030: https://app.leg.wa.gov/rcw/default.aspx?cite=9.73.030

## 18. Change log

**v1.4 (2026-11-07)**, four model-council reviews (hardening; education, trust and differentiation; build readiness; three-developer split) plus two final readiness checks:
- **Build plan (new §19)** is authoritative for the hackathon: 3-minute judging loop, scope, frozen stack, contracts, SMS copy, evaluation, milestones, preflight, Q&A card, and the three-track split for three developers running many agents.
- **Positioning (§1.3):** added Live Translation, Hiya, Aura, ABA/AT&T and Scamio; wedge is "safe even if wrong" advice that names the request and teaches the tactic; coverage argument leads with iPhones.
- **Contradictions fixed:** "never ask you for anything" (vs reply keywords) and "a text that breaks the rules is fake" replaced with the stop-and-check rule (§1.2, §4.4, §9.4, §13).
- **Consent:** subscriber opt-in is necessary, not sufficient; caller-notice gate (§12, G-03). The routing answer in §9.4 no longer dodges audio routing.
- **Evaluation:** H2 dropped; promotion is a no-regression workflow demo (§8.5, SM-10, UJ-05); H1 at least 20 hard-benign, text-only, hash-sealed (§9.1, §19.6).
- **Scope:** "P0 never cut" replaced by §19.2 and the §19.10 slip plan; SQLite replaces PostgreSQL for the hackathon (§11.2); UJ-03 avoids FR-07 payment phrases.
- **Open questions answered:** Devpost deadline 2026-11-07 23:00 CST; no sleep rotation; H1 author Rithik; T-Mobile track only (NVIDIA and Photon skipped, D-24); G-01 unavailable, so the reputation signal stays mocked; subtitle, UJ-02, §9.3 and §11.3 aligned with §19.
- **Out list completed (§19.2):** arm A, load tests, health-metrics panel, drift/feedback panel and the gate board console view are named as Out; the gate board is a static Q&A slide.
- **Messaging:** follow-up teaches the tactic with "Hang up, look up, call back"; "verified offline" became "independent"; undefined "informational" level removed (FR-16, FR-23).

**v1.3 (2026-11-07)**, operating-model change and gated verification:
- **Operating model.** Subscribers use only their phone (calls and SMS, nothing to install, no browser); T-Mobile's fraud and scam protection team runs the service from the operator console, now the product's only UI. Updated the thesis, §1–§2, UJ-01–UJ-04, glossary and FR-03, FR-04 and FR-19.
- **FR-16 and FR-17 replaced** with the team's SMS wording, plus testable acceptance: a three-element template, at most 20 words in one segment, warning in the first line, read in under 5 seconds. Real SMS to a test phone moved to P0; FR-23 follow-up is now SMS with reply keywords (new FR-26); FR-18 retired.
- **Class 0 flash SMS** adopted only as an optional P1 cue, never the only copy, after checking provider descriptions: not saved to the inbox, sender may not be shown, and offered by SMS API providers rather than carrier-only.
- **Gated verification (new §8).** The five-step lifecycle became gates V1–V5 with exit evidence and pass criteria, an evaluation-dimensions map and a release ladder. Added FR-24 (gate board and audit export), FR-25 (gated policy promotion), FR-27 (drift and feedback monitoring), SM-10, SM-11, SM-C05, UJ-05, sealed held-out batches H1/H2, NFR-10 (messaging), and an explicit do-not-act list that excludes outbound calls.
- **Production alignment (§11.4)** with T-Mobile's publicly signaled stack, labeled as an assumption; optional Kafka-compatible event bus and a PostgreSQL audit store.
- **Sponsor tracks (§6.1).** NVIDIA Nemotron as a P1 operator-side improvement agent and intent-model candidate; Photon optional for the Screening Proxy; Nessie and Spacetime skipped.
- **Demo and Q&A** rewritten around a real test phone and a live policy promotion; new hard questions on SMS visibility, spoofing, flash SMS and how improvement is proven.
- **Renumbering.** Inserting §8 shifted old §8–§17 to §9–§18. Section numbers in the v1.1 and v1.2 entries below use the numbering of those versions.

**v1.2 (2026-11-07)**, revisions after the adversarial final review:
- **Follow-up loop closed (FR-23, D-16).** Template-only follow-up text after an `action_warning`, with anti-phishing guardrails; simulated in the P0 demo, real SMS is P1. Added to UJ-02, the demo script, data flow, contracts, privacy design, risks and G-05.
- **Hard questions (§8.4).** Prepared answers, filled from the actual run, for judge questions on Pixel/Samsung, keyword matching, model value, false alerts, carrier access, opt-in and replay.
- **Additive claim sharpened (§1.3, demo close).** Post-connect *request* detection on calls that pass number filters, positioned against Scam Shield's number-based protections and measured only against our own baselines.
- **Intent Evidence contract and "lead with rules" (§4.3, D-17).**
- **Demo-critical path, live-call go/no-go at Gate 0, and on-screen replay labeling (§6, §8.3).**
- **Lightweight comprehension check (SM-09, D-18)** as a P0 condition for any accessibility claim.
- **Not adopted** from that review because it assessed v1.0: restoring pre-answer screening to the demo script and freezing FR-01–22 as P0. The v1.1 P0/P1 split stands.

**v1.1 (2026-11-07)**, revisions after the v1.0 validation review:
- **Scope re-tiered (§6).** Screening Proxy (FR-04/05), Voice Evidence (FR-10), live telephony, audible in-call warning, 50/100-session load tests and the usability study moved to P1, with an explicit cut order. Dashboard auth simplified to a single operator credential (FR-19, NFR-05); the WCAG target reframed as design guidance (NFR-04).
- **Voice Evidence kill criterion (§4.3).** Codec-matched 8 kHz μ-law test at Gate 0, with a proposed EER threshold and an ablation check.
- **Stronger comparators (§7, §8.2).** Added keyword-only arm K. Headline comparisons are now B vs K, C vs B and hard-benign false alerts; arm A is kept for context only.
- **Held-out independence (§8.1, SM-08, NFR-09).** Separate authorship, development/held-out split, policy freeze and set hash before scoring.
- **Model triggers defined (FR-12).** T1–T4, with UJ-03 rewritten around the T2 weak-signal trigger.
- **Warning surface (FR-17, §10.2, G-05).** The demo call screen is the P0 surface; Twilio ingestion and warning-delivery constraints documented against current docs.
- **UJ-01 rewritten** as a hard benign negative that no longer depends on pre-answer screening.
- **Nits fixed.** §1.3 now points to §8; §0 names `review-prd.md`; traceability covers every FR and every FR appears in a success measure; removed MNPI language from §11; applied [DECIDED]/[ASSUMPTION]/[GATE] tags inline; moved the pitch ahead of the thesis and trimmed its disclaimers.

Both reviews assess v1.0 and have not been updated for the v1.1, v1.2 or v1.3 changes.

## 19. Hackathon build plan and three-developer split (authoritative)

This section is what the team and its agents build from. Where it conflicts with §1–§18, this section wins. It was produced by four model-council reviews and two final readiness checks on 2026-11-07.

### 19.0 Assumptions (confirmed)
- About 24 hours of build time remain; judging is Sunday 2026-11-08 at in-person tables (3 min pitch + 2 min Q&A, repeated for several judges over 3 hours). Devpost deadline: **2026-11-07 23:00 CST**, before the build finishes. Submit whatever is real by then; results not yet measured stay as placeholders and are never invented.
- Three developers, each running several AI coding agents on separate branches and worktrees (AGENTS.md): **Arnav (Track A), Ameya (Track B), Rithik (Track C)**.
- One laptop runs everything at the table. Two team-owned phones (primary + spare), both pre-enrolled.
- H1 author: **Rithik** (Track C). He never writes rules, lexicons, triggers, templates or thresholds.
- Sponsor tracks: T-Mobile challenge only (D-24).

### 19.1 What we pitch
**Line:** "We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

**Positioning facts:** T-Mobile Live Translation (*87, any phone) is precedent that carrier in-call AI works; we point that at scam requests. Pixel says "Likely scam" (a verdict about the caller); we name the request and give one safe step. Hiya, Aura, ABA, AT&T and Scamio each own one piece; we don't claim the combination is unique.

**Three-minute table loop**
| Time | Content |
|---|---|
| 0:00-0:20 | Problem slide: a call passes Scam Shield, then asks for your code. |
| 0:20-0:40 | Replay 1 (clinic, audio <= 15 s): mentions a code but says not to share it. Phone stays silent. Console: "no alert - not a safety verdict." |
| 0:40-1:50 | Replay 2 (bank, audio <= 25 s): turns into an OTP request. Phone buzzes with the alert. Replay ends, end-call fires automatically, follow-up arrives. Hand the judge the phone with the SMS thread already open: "type WRONG." Console counter ticks. |
| 1:50-2:25 | "Why this alert" panel, then one number: B vs K on hard-benign calls with counts. "Where we fail" card. |
| 2:25-3:00 | Stack slide and future steps (carrier routing on the Live Translation path, in-call audio prompt, consent gate, sender verification). |
- The console shows the live transcript in large type; the hall is too loud to rely on audio.
- If a text hasn't arrived 10 s after it was sent, flip the console's **SMS mode toggle** to simulated and say so.
- Q&A-only material: family-impersonation paraphrase (model path), gate board (a static deck slide, not a console view), full K/B/C table.

**Reset:** one console button. It cancels any running replay and pending sends, invalidates the session and re-arms both replays. It never changes consent. If a phone was STOPped, text START from it (Twilio blocks sends after STOP) or switch to the spare phone. Judges are only ever asked to type WRONG.

### 19.2 Scope
**In (must work):** replay ingestion, ASR on demo clips, rules + policy (arms K and B), alert SMS, follow-up SMS, reply keywords, consent, SMS mode toggle (real / simulated with on-screen reply buttons), console (live transcript, Why panel, WRONG counter, reset, results card, login), eval on H1 for K and B with one-command report, preflight script.
**Stretch, in this order:** intent model + arm C + family paraphrase scene; promotion screen listing changed cases (labelled "H1 reused, not a fresh held-out set"); hedged "not certain" alert for model-only detections.
**Out:** live telephony, screening proxy, voice anti-spoof model, Class 0 flash SMS, Kafka/Postgres/Prometheus, drift automation and the drift/feedback panel (FR-27), audit export, H2, SMS quiz, WHY keyword, family alerts, live-mic demo, arm A (reputation-only), load tests (FR-21, SM-07), health-metrics panel (FR-21), gate board console view (FR-24; Q&A uses a static slide).

### 19.3 Frozen stack
| Concern | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn, Pydantic v2, single process |
| Events | Pipeline work runs as asyncio tasks; a separate broadcast hub fans events out to SSE subscribers (`GET /events/stream`). SSE never consumes the work queue. |
| ASR | `faster-whisper` `small.en`, CPU int8, model preloaded at startup. Pass WAV **paths** (library decodes and resamples); raw arrays must be 16 kHz. Fallback: cached transcript JSON per demo clip, labelled "cached transcript" in the console. |
| Rules / policy | Pure Python; policy tables and SMS templates as YAML in `policy/v<version>/` |
| Intent model (stretch) | `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (MIT) via `transformers` zero-shot pipeline, CPU, warmed at startup |
| SMS | `SmsGateway` interface with two implementations: `TwilioGateway` (Programmable Messaging; inbound + status webhooks; signature validated against the exact public URL with Twilio's validator) and `SimulatedGateway` (console phone frame, labelled "simulated SMS", with YES/WRONG/SHARED/STOP buttons that go through the same inbound handler). Runtime toggle. |
| Tunnel | Named `cloudflared` tunnel (stable URL), or a startup script that rewrites the Twilio webhook URL |
| Storage | SQLite (`data/safesignal.db`): consent (salted SHA-256 of E.164 number + state), aggregates, reply counts, policy history. Send-to number comes from env `DEMO_PHONE` (and `SPARE_PHONE`). No transcripts, audio or raw numbers stored. |
| Console | React + TypeScript + Vite; single operator password -> session cookie |
| Eval | `python -m eval.run --arms K,B[,C] --batch H1|dev` -> `results/latest.json` + `.md`; paired B vs K counts when both arms are given |
| Tests | pytest |
| Demo voices | Qwen3-TTS, run offline by Track B from `voice/` with its own `voice/requirements.txt` (not an app dependency); output round-tripped through 8 kHz mu-law into `audio/demo/<id>/`. H+1 check: licence, weights download and generation on available hardware; fallback is team-recorded voices. Voices are synthetic: say so if a judge asks (this relaxes the §9.3 real-voice preference for the hackathon). |

### 19.4 Interfaces (the contracts tracks build against)
**Scenario file** `scenarios/<set>/<id>.json`:
`{"id","set":"dev|demo|H1","label":"scam|benign","hard_benign":bool,"category":"otp|payment|remote|none","turns":[{"speaker":"caller|subscriber","text":"<script line>","audio":"<id>/t01.wav|null"}]}`
Audio is required only for `demo` scenarios; audio paths resolve relative to `audio/demo/` (Track B writes the WAVs from Track C's scripts; C never writes under `audio/`). Speaker comes from the scenario (a real call would use the stream track).

**Cached transcript** `scenarios/demo/<id>/transcript.json`: a JSON array of `{seq,speaker,t_start_ms,t_end_ms,text}`. A adds `session_ref` and `source:"cached"` when replaying, and replay emits segments at those times.

**Results file** `results/latest.json` (C writes, B reads): `{batch, source:"script", arms:{K:{TP,FP,FN,TN,hard_benign_fp,hard_benign_n}, B:{...same}}, discordant:{K_only, B_only}}`. `GET /results/latest` returns it unchanged, or HTTP 200 `{status:"pending"}` before it exists.

**Transcript segment:** `{"session_ref","seq","speaker","t_start_ms","t_end_ms","text","source":"asr|cached|script"}`

**Risk Event:** `{"session_ref","event_type","source":"rule|intent","rule_id|null","category","span_seq":[int],"confidence_class":"high|medium|low","policy_version"}`. Category wording only, never quoted text.

**Decision:** `{"session_ref","level":"action_warning|none","template_id|null","followup_template_id|null","basis":[ids],"keyword_arm_would_fire":bool,"policy_version"}`

**Decision engine (pure, Track A):** `decide(segments: list[Segment], arm: "K"|"B"|"C", policy_version) -> list[Decision]`. No SMS, DB, network or asyncio. Called incrementally by the pipeline with all segments so far, and once per scenario by eval. At most one `action_warning` per category per session (dedupe lives here).
- **K** = the shared lexicon matched on any speaker's text, no speaker, negation or request-direction checks.
- **B** = the same lexicon plus context rules (caller is the speaker, request direction, negation such as "don't share", dialogue state).
- **C** = B plus intent model on trigger windows (stretch).

**Pipeline (Track A):** `backend/app/pipeline.py`
- `start(arm, policy_version, sms_mode) -> session_ref`. Only one demo session may be active; starting a new one finishes the old one.
- `process(segment) -> list[Decision]`: calls `decide`, publishes events, and asks the SMS gateway to send any new alert.
- `finish(session_ref)`: idempotent. Drains accepted segments, then sends at most one follow-up (the first action warning's `followup_template_id`) if the phone is still opted in. Called automatically when a replay's last turn finishes, and by `POST /demo/end-call`.
- `reset()`: cancels replay and pending sends, invalidates the session, emits `reset`. Preserves consent and aggregates.
- Demo arm is **B** (C if stretch passes). Eval does **not** use the pipeline; it calls `decide` directly.

**Event envelope (SSE):** `{"event_id","session_ref":null|string,"type","payload"}` with types and payloads:
`session` `{state:"running|finished|reset", arm, sms_mode}` · `segment` (Transcript segment) · `risk_event` (Risk Event) · `decision` (Decision) · `sms` `{message_id, template_id, status:"queued|sent|delivered|failed"}` · `reply` `{keyword, counted, wrong_count}` · `consent` `{state:"invited|active|stopped"}`

**SMS gateway (Track B):** `send(template_id, session_ref) -> message_id`; checks consent first and refuses if not active. Webhooks `POST /sms/inbound`, `POST /sms/status`. Deduplicate inbound by `MessageSid`. Normalise keywords: trim, strip punctuation, case-insensitive (`"Wrong."` counts). `STOP|STOPALL|UNSUBSCRIBE|CANCEL|END|QUIT|STOP PLEASE|PLEASE STOP` -> stopped (Twilio also blocks these at its layer and may send its own reply). `START|YES` -> active. `SHARED` -> category-specific R-SHARED. `WRONG` -> R-WRONG + counter. `HELP` or anything else -> R-HELP. Replies attach to the latest session with an action warning.

**Console API (Track B):** `POST /login`, `GET /events/stream`, `POST /demo/run/{scenario_id}`, `POST /demo/end-call`, `POST /demo/reset`, `POST /demo/sms-mode`, `GET /results/latest`, `GET /aggregates`.

### 19.5 SMS copy (frozen)
All templates: ASCII GSM-7 only (straight apostrophes), <= 160 characters, no digits, links or double quotes, nothing quoted from the call. `ALERT-*` <= 20 words. A lint test enforces this. Send from a non-trial Twilio account or confirm the trial prefix is off; otherwise measure the real segment count and don't claim one segment.

| Template | Text |
|---|---|
| ENROLL | CallSafe: reply YES to get a text if a caller asks for codes, money or access. No text doesn't mean safe. Reply STOP to end. |
| R-YES | CallSafe: you're in. Texts only when a caller asks for codes, money or access. Reply STOP to quit, HELP for help. Msg&data rates may apply. |
| R-HELP | CallSafe: we only ever say stop and check. We never ask for codes, money or info. Reply STOP to quit. |
| ALERT-OTP-01 | CallSafe: caller is asking for a code. Don't share it. Hang up, call your bank's number yourself. |
| ALERT-PAY-01 | CallSafe: caller is asking for money. Don't pay. Hang up, call them back on a number you know. |
| ALERT-REMOTE-01 | CallSafe: caller wants access to your device. Don't install anything. Hang up, call a number you know. |
| FU-OTP-01 | CallSafe: your caller asked for a code. Codes unlock your account; banks never ask. Hang up, look up, call back. Reply SHARED or WRONG. |
| FU-PAY-01 | CallSafe: your caller pushed for payment. Scammers rush you; real orgs let you call back. Hang up, look up, call back. Reply SHARED or WRONG. |
| FU-REMOTE-01 | CallSafe: your caller wanted access to your device. Real support doesn't cold-call. Hang up, look up, call back. Reply SHARED or WRONG. |
| R-SHARED-OTP | CallSafe: anyone can be fooled. Call your bank now using the number on your card and tell them a code was shared. |
| R-SHARED-PAY | CallSafe: anyone can be fooled. Call your bank or card issuer now using the number on your card and tell them. |
| R-SHARED-REMOTE | CallSafe: anyone can be fooled. Disconnect the device from the internet, then get help from a store or a number you know. |
| R-WRONG | CallSafe: thanks, counted. A person reviews any change, and it's tested before it goes live. |
| R-STOP | CallSafe: you're unsubscribed. No more texts. |

**Enrollment card (printed at the table, shown on the stack slide):** CallSafe analyses audio of your own calls only after you reply YES; texts are sent only when a call asks for codes, money or access; msg and data rates may apply; reply STOP to end, HELP for help. **CallSafe only ever says stop and check. Any text saying a caller is fine, or asking for codes, money or info, is not us.**

### 19.6 Evaluation (minimum honest version)
- **Dev set:** 20 scam + 20 benign (at least 10 hard-benign), written by Track C in `scenarios/dev/`. Track A tunes rules only on it, reads it, and never edits it.
- **H1:** 30 scam + 30 benign, at least 20 hard-benign. Written by Rithik, who is not on the rules or intent work, starting at H+0, outside the shared tree until sealed. Sealing = commit `scenarios/H1/` plus `scenarios/H1.sha256` = sha256 over the sorted file contents. Rules/intent agents never read `scenarios/H1`. `eval.run` refuses to score H1 if the hash doesn't match.
- **H1 runs on scenario text only** (`source:"script"`), no audio and no ASR. The report says "scripted transcripts, not ASR". ASR is checked only on demo clips.
- **Labels:** a scenario is predicted positive iff any Decision is `action_warning`. TP/FN on scam, FP/TN on benign. `hard_benign` = a benign call containing a code, money or access phrase in a non-request use; the H1 author sets it.
- **Report per arm:** TP/FP/FN/TN, recall with Wilson 95% CI, hard-benign false alerts "x of n (upper bound y%)", paired discordant counts B vs K. Call a win only at 5 or more one-directional discordant calls.
- Demo scenarios are never in H1 or dev.

### 19.7 Milestones (hours from dev start)
- **H+0:** H1 author (Track C) starts. Skeleton PR (§19.10) merged by H+0:45.
- **H+1 kill checks:**
  - SMS: the exact demo account and sender complete outbound **and** inbound to the real phone; log median and worst delivery time over 10 sends and the actual segment count. If it fails, the demo runs on `SimulatedGateway` and the pitch says so.
  - ASR: preloaded model transcribes a representative 8 kHz demo WAV end to end on the demo laptop within the clip's own duration. If download, accuracy or timing fails, demo uses cached transcripts (labelled).
  - Intent (only if attempting stretch): warmed inference <= 1.5 s on the laptop, otherwise drop C.
- **H+6:** full loop (clinic silent, bank alert, auto end-call, follow-up, WRONG, reset) in simulated mode, and on the real phone if the SMS check passed.
- **H+12:** Why panel complete; K vs B on sealed H1 with report on the results card.
- **H+16:** feature freeze. Stretch only if H+12 is green.
- **Devpost:** submitted by 2026-11-07 23:00 CST, whatever milestone the build has reached.
- **After freeze:** 10 timed table-loop rehearsals, hallway test (5 people, printed alert/follow-up/fake "go ahead" text), deck. Sleep rotation: none; the team works through the night.

**Preflight (`scripts/preflight`, run before every judging block):** models cached and the app starts offline; cached-transcript fallback works; tunnel URL matches the Twilio webhook; one real test SMS round trip; both phones opted in; laptop on power, sleep disabled, on a phone hotspot.

### 19.8 Q&A card (one sentence each)
- **Live Translation?** It proves T-Mobile can run AI inside calls on any phone; we point that same path at scam requests.
- **Pixel already does this?** Pixel says "Likely scam" on some Android phones; we name the request, give a safe step, teach the trick, and reach any phone, including iPhones.
- **Who reads a text mid-call?** The buzz is the interrupt and the text is one line; the follow-up exists because many won't read it until after; an in-call audio prompt on the Live Translation path is next.
- **So you transcribe all my calls?** Only for opted-in subscribers, processed in memory; we store no audio, transcripts or numbers, only counts.
- **Can scammers fake your text?** Yes, which is why our texts only ever say stop and check; a fake that copies us gives safe advice, and one that says "go ahead" breaks our one rule.
- **Is listening legal?** Subscriber opt-in is necessary but not sufficient; caller notice in all-party-consent states is a gate before any real customer.
- **How good is it?** On 60 held-out scripted calls written by a teammate who never saw the rules: [numbers with denominators]. Too small for a production claim, and we say so.
- **What if the AI is wrong?** A false alarm costs one callback; silence is never a safety verdict; WRONG replies go to a human-approved, tested policy change.
- **Why trust AI at all?** Rules decide, the model never acts alone, every alert cites a rule ID, and the advice is safe even if we're wrong.

### 19.9 PRD changes
Applied to §1–§18 in v1.4; see the §18 change log.

### 19.10 Tracks (three developers, conflict-free)
Every path has exactly one writing track. Inside a track, each agent owns one package directory plus its own `tests/<pkg>/`; no two agents share a file. Everyone else imports, never edits.

| Track | Owns (sole writer) | Delivers | Publishes | Consumes |
|---|---|---|---|---|
| **A - Pipeline + integration (Arnav)** | `backend/app/{ingest,asr,rules,policy,intent}/`, `backend/app/pipeline.py`, `backend/app/events.py`, `backend/app/models.py`, `backend/app/main.py`, `policy/` (rules, lexicon, SMS template YAML), `pyproject.toml` + Python lockfile, `Makefile`, `scripts/`, `tests/conftest.py` | Skeleton, contracts, replay + ASR + cached fallback, `decide` with K/B (C stretch), pipeline lifecycle (start/process/finish/reset), event hub, preflight | §19.4 models and signatures, example event fixtures (`tests/fixtures/events/*.json`), `decide`, template lookup `templates.get(id)` | Scenario files from C; `SmsGateway` from B |
| **B - Phone + operator + voice (Ameya)** | `backend/app/{sms,consent,api,storage}/`, `console/` (incl. `package.json` + lockfile), `voice/`, `audio/`, `.env.example`, tunnel config | Demo call audio via Qwen3-TTS (both demo scenarios by H+3), Twilio + Simulated gateways, webhooks, keyword parser, consent + SQLite, operator routes, SSE endpoint, console (transcript, Why panel, counter, reset, SMS-mode toggle, results card, login), real-phone tests | `SmsGateway`, routers (auto-discovered), aggregates and results API | A's models, events and templates; C's demo scripts and results JSON |
| **C - Evidence + pitch (Rithik)** | `scenarios/`, `eval/`, `deck/`, `results/`, Devpost text | Demo scenario scripts + cached transcripts (first), dev set, sealed H1, `eval.run` and report, deck, 30 s and 3 min scripts, Q&A card, rehearsals, hallway test | Scenario files, `results/latest.json` + `.md` | A's `decide` (imports only) |

**Independence:** Rithik (C) writes H1 and never writes rules. A's agents never read `scenarios/H1/`. C's agents never read `backend/app/rules/` or `policy/`.

**Integration rules**
- **Skeleton PR (A lead, merged by H+0:45), before any other PR:** all §19.4 models; `main.py` auto-discovers routers from `app.api` and `app.sms`, so nobody edits it to add routes; a stub in every backend package (cached transcript ASR, `decide` returns none, `SimulatedGateway`, fake events); all dependencies declared (fastapi, uvicorn, pydantic, faster-whisper, twilio, pyyaml, httpx, pytest; `[intent]` extra for transformers); `make smoke` = pytest + OTP replay through the stubs, using an A-owned fixture in `tests/fixtures/` until C's demo scenarios merge. With stubs, the full loop runs from H+1, and real pieces replace stubs one PR at a time. A writes stubs inside B's backend directories (`sms/`, `consent/`, `api/`, `storage/`) only in this PR, and ownership passes to B the moment it merges. The skeleton writes nothing under `scenarios/`, `eval/`, `results/` or `console/`; C owns demo scenarios and caches from H+0. `GET /results/latest` (B) reads `results/latest.json` (C).
- **Bootstrap in parallel (first 45 min):** B scaffolds `console/` against A's event fixtures and starts the Twilio H+1 check; C commits the two demo scenarios (text + cached transcripts) and starts H1; B starts Qwen3-TTS setup and voices them as soon as the scripts land.
- **Contract changes:** A only, PR titled `CONTRACT:`, additive fields with defaults, FYI on the board, thumbs-up from B and C before merge.
- **Dependencies:** Python deps only via A (others post ASK; A adds within 15 min). Console deps only via B.
- **Late events after reset:** every queued task and event carries a session generation number; anything from an old generation is dropped and never sends SMS.
- **Branches:** `<username>/<track>-<agent>` (e.g. `arnav/a-rules`, `ameya/b-sms`, `rithik/c-eval`), one worktree each, one PR per agent task, rebased on `origin/main` before merge.
- **Merging:** each developer reviews and merges their own track's PRs, in windows at :00 and :30, order CONTRACT -> A -> B -> C. A PR merges only if `make smoke` passes on the rebased branch, so main always runs.
- **Board:** one track-level CLAIM per developer listing paths; each agent posts its own CLAIM (branch + subdirectory) and DONE with the PR link; LEARN for Twilio, whisper and tunnel quirks.

**Integration points**
| When | Check |
|---|---|
| H+1 | Kill checks (§19.7); `make smoke` green on main |
| H+3 | A emits real events for the cached OTP replay; B's console renders them |
| H+6 | Full loop in simulated SMS mode: clinic silent, bank alert, auto end-call, follow-up, WRONG counter, reset. Same loop on the real phone if the H+1 SMS check passed |
| H+9 | `eval.run` scores dev set through A's `decide` |
| H+12 | K vs B on sealed H1; results card shows it |
| H+16 | Freeze |

**Human-only tasks:** Twilio account, numbers, webhook and both phones, Qwen3-TTS demo voices (Ameya, B); H1 authoring and hash commit, deck, Devpost (Rithik, C); 8 kHz ASR check on the demo laptop (Arnav, A); rehearsals and hallway test (Rithik leads, everyone attends).

**Slip plan:** A slips, demo on cached transcripts + K plus only B's negation rule (labelled); if that isn't ready either, skip the clinic replay and say so. Never run the clinic replay on plain K. B slips, simulated SMS phone frame. C slips, deck after H+12; H1 never shrinks below 30 + 30 without reporting the real denominators.

*End of PRD. Product scope and build plan (v1.4) are final for hackathon development. The document is not a security approval, customer validation report, or guarantee of future T-Mobile integration.*
