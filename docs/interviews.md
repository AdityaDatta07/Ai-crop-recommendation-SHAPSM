# Domain Interview Log

**Version:** 1.0 · **Last updated:** 2026-08-17
**Status:** ⚠️ **NO INTERVIEWS CONDUCTED YET.** Sections 1–5 are the instrument. Section 6 is the log and is empty by design.

---

## 0. Read this first

This document has one rule: **nothing goes in the log that did not happen.**

A fabricated interview is worse than no interview. It will not survive a follow-up question from a judge who works in agriculture, and if it fails it invalidates everything else you claim. An empty log with an honest plan is defensible. A fake one is not.

If you conduct zero interviews before the internal round, the correct answer to *"have you spoken to a farmer?"* is: **"Not yet. Here's who we've approached and when we're meeting them."** That is a survivable answer. Inventing a conversation is not.

---

## 1. Why this matters more than it looks

You are building a tool that tells someone how to spend a season of their income. Every assumption in `ai-design.md` and `data-sources.md` is currently an assumption made by students who have not farmed.

Concrete things only a domain conversation can tell you:

- Whether a farmer would trust a phone screen over his neighbour's advice, and what would change that.
- Whether "expected net margin" is even the number he cares about, or whether it's risk of total loss.
- Whether he can act on a recommendation at all — seed availability, credit, and landlord constraints may make the top-ranked crop impossible.
- Whether our scoring weights match how an agronomist actually reasons.
- Whether a Soil Health Card is something he has, can find, and trusts.

Each of those could invalidate a design decision. Better to find out now.

---

## 2. Ethics and consent

Non-negotiable, and partly a legal matter.

### 2.1 Consent

State before you start, in their language:

> "We're students building a tool to help farmers choose crops. We'd like to ask about your experience for about twenty minutes. Nothing you say will be published with your name. You can stop any time, or skip any question. Is that alright?"

Ask separately before recording audio. If they hesitate, take written notes instead.

### 2.2 Privacy — this repository is public

**Never commit any of the following:**

| Do not commit | Use instead |
|---|---|
| Full name | `Farmer A`, `Agronomist B` |
| Phone number, address | Omit entirely |
| Village name | District only |
| Photographs of people | Omit, or crop out faces |
| Aadhaar, land record numbers | Never collect these at all |
| Raw audio recordings | Keep offline, reference by ID |

Keep the identity mapping in a **local file that is never committed** — `interviews-private.md`, added to `.gitignore`. Verify with `git check-ignore -v interviews-private.md` before your next commit.

### 2.3 Conduct

- Do not promise the tool will help them, or that it will ever exist.
- Do not give agricultural advice. You are not qualified, and this is precisely the boundary `ai-design.md` §4.2 draws.
- Do not pay for participation. Offer tea if you're meeting somewhere it's appropriate.
- If they ask what they get out of it, be honest: nothing immediate.

---

## 3. Who to talk to

Ranked by value per unit of effort. **One good conversation with an agronomist beats five rushed ones with anyone.**

| Priority | Who | Why | How to reach |
|---|---|---|---|
| 1 | **KVK scientist** (Krishi Vigyan Kendra) | Can validate your scoring weights directly. Understands both agronomy and farmer behaviour. Used to explaining things. | Every district has a KVK. Phone or walk in. Say you're students on an SIH project — they are mandated to do outreach and usually receptive. |
| 2 | **Agriculture college faculty** | Likely on your own campus or nearby. Lowest friction of anyone on this list. | Ask your own faculty for an introduction. |
| 3 | **Farmer, 1–5 acres** | The actual user. Tells you what he'd trust and what he can act on. | Family connections, campus staff, nearest weekly mandi, a village within travel distance. |
| 4 | **Agriculture extension officer** | Knows how advice actually reaches farmers, and why it often doesn't. | District agriculture office. |
| 5 | **Agri-input shop owner** | Sees what farmers actually buy and what they ask. A candid, underrated source. | Any local seed/fertiliser shop. |
| 6 | **Mandi trader or commission agent** | Reality-check on your price data and how prices actually get set. | Local mandi. |

**Realistic minimum before the internal round:** one KVK scientist or faculty member, and one farmer. Two conversations. That is achievable in a week and transforms your answer to the hardest Q&A question.

---

## 4. How to run one

### Before

- Two people maximum. Six students surrounding one farmer is an interrogation.
- One asks, one takes notes. Agree who does which beforehand.
- Bring the app on a phone, working, with the demo path loaded. Showing beats describing.
- Have `USE_MOCK_GEO=true` ready in case there's no signal.
- 20–30 minutes. Respect it.

### During

**Ask about their experience, not about your idea.** The most common failure is describing your app for fifteen minutes and getting polite agreement, which teaches you nothing.

| Do | Don't |
|---|---|
| "How did you decide what to plant last season?" | "Would you use an app that recommends crops?" |
| "What happened the last time a crop didn't work out?" | "Don't you think this would be useful?" |
| "Who do you ask when you're unsure?" | "Our system uses satellite data to…" |
| Let silences run — they fill them | Fill every pause yourself |
| Follow the interesting tangent | Stick rigidly to your list |

Show the app in the **last five minutes**, not the first. Once they know what you want to hear, they'll tell you it.

### After

- Write it up **the same day.** Memory degrades faster than you expect.
- Log what surprised you, not just what confirmed you. The surprises are the entire value.
- Record what you will **change** as a result. An interview that changes nothing was probably conducted badly.

---

## 5. Question banks

Pick 8–10, not all of them. Follow tangents.

### 5.1 Farmer

**Current decision-making**

1. What did you plant last season, and how did you decide?
2. Who do you talk to before deciding? Whose opinion carries most weight?
3. Has anyone ever advised you to plant something and it went badly?
4. Do you know your soil's pH, or have a Soil Health Card? Have you used it?
5. How do you find out what prices are at the mandi?

**Constraints — often the most useful answers**

6. If you were told a crop would earn more, what would stop you planting it?
7. How do you pay for seed and fertiliser at the start of a season?
8. Do you own this land or farm it on lease? *(Ask carefully — it may be sensitive.)*
9. How much water can you access, and is that reliable?
10. Where do you buy seed, and is what you want usually available?

**Risk — probe this properly**

11. What matters more: a chance at a bigger profit, or being sure you don't lose?
12. What was your worst season, and what caused it?

**Technology**

13. What do you use your phone for? Do you use it for farming information?
14. Is there an app or WhatsApp group you get farming information from?
15. Would you trust advice from a phone more or less than from the KVK? Why?

**After showing the app**

16. What's the first thing you notice on this screen?
17. Does this number *(point at net margin)* mean anything useful to you?
18. What's missing? What would you want to see here?
19. Would you show this to another farmer?
20. What would make you not trust it?

### 5.2 KVK scientist or agriculture faculty

**Validating the model — the point of this conversation**

1. When you advise a farmer on crop choice, what do you consider, in what order?
2. We weight soil pH at 0.20, rainfall 0.20, temperature 0.15, texture 0.15. Does that ordering match how you'd reason?
3. What factor are we missing entirely?
4. Is a 250-metre modelled soil estimate useful, or too coarse to act on?
5. How much does variety choice matter relative to crop choice?
6. Are the ICAR thresholds in our table current, or has guidance moved on?

**Reality checks**

7. What do farmers in this district get wrong most often about crop selection?
8. Where does existing extension advice break down?
9. What would make you comfortable recommending a tool like this to a farmer?
10. What would make you actively warn a farmer away from it?

**After showing the app**

11. Is anything here agronomically wrong or misleading?
12. Is our confidence indicator honest enough, or does it still overstate certainty?
13. Would you use this yourself when advising a farmer?

Question 11 is the one to ask slowly and write down verbatim.

### 5.3 Extension officer

1. How many farmers are you responsible for, and how often do you reach each one?
2. How does advice actually get to a farmer in practice?
3. What would make a digital tool useful to *you* rather than a parallel channel?
4. What do farmers ask you that you can't answer well?
5. Has a digital agriculture initiative been tried here? What happened to it?

Question 5 is worth asking bluntly. There have been many. Knowing why they failed is more valuable than any feature idea.

### 5.4 Agri-input shop owner

1. What do farmers ask you when they come in?
2. Do they arrive knowing what they want, or asking what to buy?
3. What gets planted here most, and has that changed in the last five years?
4. Do farmers show you information from their phones?

---

## 6. Interview log

**Empty. Add one entry per conversation, most recent first.**

Copy the template. Do not modify it — consistent structure is what makes these comparable later.

### Template

```markdown
### INT-00X · [Role, e.g. KVK scientist] · YYYY-MM-DD

| | |
|---|---|
| **Participant** | Anonymised label, e.g. `Agronomist B` |
| **Role / context** | e.g. Horticulture scientist, district KVK |
| **District** | District only, never village |
| **Interviewers** | Team member names |
| **Duration** | e.g. 25 min |
| **Consent** | Verbal, recorded: yes / no |
| **Format** | In person / phone / video |

**Context**
Two or three lines. Land size, crops grown, or professional background.

**Key points**
- Direct, specific statements. Quote where the wording matters.
- "…" for verbatim quotes.

**Surprises — things that contradicted our assumptions**
- The most valuable section. If empty, the interview was probably badly run.

**Direct feedback on the app** *(if shown)*
- What they noticed first
- What confused them
- What they said was missing

**Changes we are making as a result**
| Change | Where | Status |
|---|---|---|
| e.g. Add water-availability input | `api-contract.md` request | Proposed |

**Open questions to follow up**
- 
```

### Entries

*None yet.*

---

## 7. Synthesis

**To be completed after three or more interviews.** Fill only from real entries.

### 7.1 Recurring themes

| Theme | Heard from | Implication |
|---|---|---|
| | | |

### 7.2 Assumptions validated

| Our assumption | Evidence | Source |
|---|---|---|
| | | |

### 7.3 Assumptions invalidated ⭐

| Our assumption | What we heard instead | What we changed |
|---|---|---|
| | | |

**This is the table judges care about most.** It demonstrates that talking to users changed the product. A team that interviewed people and changed nothing either asked the wrong questions or wasn't listening.

### 7.4 Deliberately not acted on

| Suggestion | Why not | Revisit when |
|---|---|---|
| | | |

Being able to say "we heard this and chose not to do it, because…" is a stronger signal than acting on every suggestion.

---

## 8. Plan and progress

Update as you go. This table is what you show a judge if the log is still thin.

| Target | Type | Approached | Scheduled | Completed | Owner |
|---|---|---|---|---|---|
| District KVK | Priority 1 | ☐ | ☐ | ☐ | |
| Agriculture faculty | Priority 2 | ☐ | ☐ | ☐ | |
| Farmer 1 | Priority 3 | ☐ | ☐ | ☐ | |
| Farmer 2 | Priority 3 | ☐ | ☐ | ☐ | |
| Extension officer | Priority 4 | ☐ | ☐ | ☐ | |

**Assign owners now.** An unowned row does not get done.

Even *"approached, awaiting reply"* is a real answer under questioning. It shows you knew it mattered.

---

## 9. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Instrument created — protocol, ethics, question banks, templates. Log empty; no interviews conducted. |
