# Demo Script

**Round:** College internal hackathon · **Duration:** 5 minutes + Q&A · **Speakers:** whole team
**Version:** 1.0 · **Last updated:** 2026-08-17

---

## 0. How to use this document

Rehearse from this, not from memory. Fill in the names in section 2 and give every person their own printed copy with their lines highlighted.

The two things that lose marks in a 5-minute slot are **running over** and **fumbled handovers**. Both are solved by rehearsal, not by knowing the material better.

---

## 1. The one sentence

If the judges remember nothing else:

> **We tell a farmer which crop to plant on their specific land, why, and what they can expect to earn — using satellite soil data and public agricultural data, with every recommendation traceable to a published source.**

Every speaker should be able to say this if asked to summarise. Practise it until it sounds natural rather than recited.

---

## 2. Speaker assignments

Fill in before rehearsal. Adjust segment count to your actual team size — **do not add a speaker just to include someone.** A silent team member who answers one Q&A question brilliantly contributes more than a rushed 20-second segment.

| # | Segment | Time | Speaker | Owns in Q&A |
|---|---|---|---|---|
| 1 | Problem | 0:00–0:40 | _______ | Problem framing, user research |
| 2 | Solution + architecture | 0:40–1:10 | _______ | System design, tech stack |
| 3 | **Live demo** | 1:10–2:40 | _______ | Frontend, UX, offline |
| 4 | Data and geospatial | 2:40–3:20 | _______ | Earth Engine, data sources, licensing |
| 5 | AI and scoring | 3:20–4:00 | _______ | Ranker, LLM, safety |
| 6 | Impact and roadmap | 4:00–4:50 | _______ | Scale, feasibility, next steps |

**Driver:** one person operates the laptop for the entire demo — ideally speaker 3. Nobody else touches it. Passing a laptop mid-demo is how demos die.

---

## 3. The script

Timings are targets. The **bold** lines are the handovers — say them exactly. They are what stops the 4-second silence where the next person realises it's their turn.

### Segment 1 — Problem · 0:00–0:40

> "A farmer in Uttar Pradesh decides what to plant based on what he planted last year, and what his neighbour is planting. That decision commits his entire season — his land, his labour, and often borrowed money.
>
> He has no practical way to know whether his soil suits that crop this year, or whether the market will pay for it. Agricultural extension officers exist, but one officer covers thousands of farmers.
>
> The information to make a better decision already exists — in satellite data, in soil surveys, in government price feeds. It just never reaches him in a form he can use."

> **"That's the gap we built for. [Name] will show you what we made."**

**Do not** open with statistics about Indian agriculture's GDP share. Every team does. Open with the farmer.

### Segment 2 — Solution and architecture · 0:40–1:10

> "Our system takes one input — where your land is — and returns a ranked list of crops with a suitability score, a sowing window, and a profit estimate.
>
> Behind it: a Next.js progressive web app, a FastAPI backend, Google Earth Engine for soil and vegetation data, and Supabase for storage. The recommendation itself is computed by a deterministic scoring engine, not a language model — and I'll let [Name] explain why that matters later.
>
> One thing worth stating up front: every number we show has a documented source. Nothing is invented."

> **"[Name] will walk you through the live app."**

*Show the architecture diagram from `architecture.md` here — one slide, no animation.*

### Segment 3 — Live demo · 1:10–2:40 ⭐

**The most important 90 seconds.** Narrate what you are doing, not what the audience can already see.

Exact click path — rehearse until it is muscle memory:

| Time | Action | Say |
|---|---|---|
| 1:10 | App already open on the map screen | "This is the farmer's view. He opens it on his phone." |
| 1:15 | Drop pin on the pre-chosen location | "He marks his field. That's the only thing he has to do." |
| 1:20 | Field summary appears | "Immediately we show what we know about that land — soil pH, texture, rainfall. This came from satellite data in under two seconds." |
| 1:35 | Select season = Rabi, area = 1.5 ha | "He picks the season and his plot size." |
| 1:45 | Tap Get Recommendations | "And this is where the work happens." |
| 1:50 | Results load | "Five crops, ranked. Wheat first." |
| 2:00 | Point at score and reasons | "Not just *wheat* — *why* wheat. Soil pH 7.2 sits in wheat's optimal range. Rainfall is adequate with two irrigations. These reasons come out of the scoring itself, not from a text generator." |
| 2:15 | Point at economics | "Expected yield, input cost, and net margin for his 1.5 hectares — using current mandi prices from the government's own feed." |
| 2:25 | Scroll to a lower-ranked crop | "And he can see what didn't win, and why." |
| 2:35 | Stop | — |

> **"[Name] will explain where this data actually comes from."**

**Rules for the driver.** Have the app already open before you start speaking. Never say "let me just…" or "this is usually faster." Never apologise for load time — narrate through it instead. If something is slow, keep talking; silence is what the audience notices.

### Segment 4 — Data and geospatial · 2:40–3:20

> "Soil comes from ISRIC SoilGrids at 250-metre resolution, licensed CC BY 4.0. Vegetation state from Copernicus Sentinel-2, ten-metre resolution, five-day revisit. Rainfall from CHIRPS, which is public domain. All three via Google Earth Engine.
>
> Market prices come from Agmarknet through the government's open data platform, under the Government Open Data License.
>
> We documented every source with its licence and its limitations. SoilGrids is a model prediction, not a lab test of his field — so we say that in the app rather than hiding it. Where we don't have data, we show a dash, not a zero."

> **"[Name] will cover how the recommendation is actually computed."**

That last line about dashes rather than zeros is worth landing. It signals you thought about being wrong, which is rarer than it should be.

### Segment 5 — AI and scoring · 3:20–4:00

> "The ranking is deterministic. Each crop is scored against agronomic thresholds from ICAR guidance — pH, rainfall, temperature, texture — combined with documented weights. Same input, same output, every time. Auditable.
>
> The language model does two things, and neither is deciding what to grow. It rewrites the structured reasons into plain Hindi or English, and it answers follow-up questions. It only ever sees data we already computed.
>
> And we validate its output — if it produces a number that isn't in its input, we reject the response and fall back to a template. It cannot invent a yield figure, because we check.
>
> It also refuses pesticide dosage and disease diagnosis questions, and points the farmer to his local Krishi Vigyan Kendra. Those questions can cause real harm if answered badly, and we don't have the data to answer them safely."

> **"[Name] will close on where this goes."**

**This is your strongest technical segment.** Most teams say "we used AI." You are explaining what you deliberately did *not* let the AI do, and why. Deliver it slowly.

### Segment 6 — Impact and roadmap · 4:00–4:50

> "What works today: pin to recommendation, with real satellite data, real prices, and explanations in Hindi.
>
> What's next, in order: validating our scoring weights against historical district yield data, voice input for farmers who don't read comfortably, and crop rotation history so advice improves across seasons.
>
> What we're honest about: our soil data is modelled at 250 metres, not measured on his field. Our yield figures are historical averages, not predictions for his plot. We show confidence levels so the farmer knows how much to trust each recommendation.
>
> This is a decision-support tool for a farmer who currently has none. Not a replacement for an agronomist — a way to reach the farmers an agronomist will never get to."

> **"Thank you. Happy to take questions."**

---

## 4. Pre-demo checklist

### T–30 minutes

- [ ] Laptop charged, **charger plugged in**
- [ ] Backend warmed — hit `/health` twice (Render free tier sleeps; a cold start mid-demo is a guaranteed fumble)
- [ ] Full demo path run end to end once, successfully
- [ ] Browser: only the demo tab open. No bookmarks bar, no notifications, no WhatsApp
- [ ] Phone on silent, in a bag, not on the table
- [ ] Screen brightness maximum, night mode off
- [ ] Zoom set so the back row can read it — test from the back of the room
- [ ] Fallback video open in a **background tab**, paused at 0:00
- [ ] Screenshot deck open in another background tab

### T–5 minutes

- [ ] App open on the map screen, pin *not yet* dropped
- [ ] Backend pinged once more
- [ ] Everyone has their printed script
- [ ] Driver confirmed — one person, hands on the laptop

---

## 5. When it breaks

It will break at least once during the hackathon. Rehearsed recovery is the difference between a wobble and a collapse.

| Failure | Response | What to say |
|---|---|---|
| Backend slow / cold | Keep narrating, do not apologise | "While this loads — the soil layer we're querying covers all of India at 250-metre resolution…" |
| Earth Engine fails | Switch to `USE_MOCK_GEO=true` | "I'm switching to our cached dataset — this is the offline mode a farmer would get with poor connectivity." |
| Backend fully down | Go to the fallback video tab | "Our backend isn't responding, so here's the recorded run — I'll talk through it." |
| No internet at venue | Video, then screenshots | Same as above |
| App crashes | Screenshot deck, keep talking | "Let me walk you through what you'd see." |
| You blank on your line | Say the one-sentence summary (§1) and hand over | — |
| Judges cut you off early | Jump straight to segment 6's first paragraph | — |

**Non-negotiable preparation:** record the fallback video *this week*, while things work. A 90-second screen recording of the full happy path, no narration. Every team that skips this regrets it.

Never say "it worked five minutes ago." Judges have heard it from every team before you, and it reads as an excuse rather than an explanation.

---

## 6. Q&A preparation

Assign each question to whoever owns that area. Answers should be **20–30 seconds**. If you don't know, say so and say what you'd do to find out — that is a genuinely good answer, and judges can tell when you're inventing.

### Expected

**"How is this different from existing crop advisory apps?"**
> Most give generic district-level advice. We use satellite soil data for the specific plot, and we show our reasoning — the farmer sees which factors drove the recommendation, not just a crop name.

**"How accurate is it?"**
> We haven't validated against yield outcomes yet — that's our next step and we've named it as such. What we can defend today is that every threshold traces to published ICAR guidance, and the scoring is deterministic and auditable. We'd rather be honest about that than quote an accuracy number we can't support.

**"Why not use machine learning?"**
> We looked at it. The available labelled datasets have no documented provenance — the widely circulated one is reported to be synthetic. And what we'd actually have is what farmers *did* plant, not what they *should* have. Our interface is designed so a trained model can replace the rules engine once we have trustworthy data.

**"Will farmers actually use this?"**
> Honest answer: we haven't put it in front of enough farmers to claim that. It's a PWA so there's no app store and it works on a low-end phone, and Hindi output plus planned voice input address literacy. But adoption is a real open question, and we'd want extension officers as the channel.

**"What does it cost to run?"**
> Earth Engine is free for research and education, which covers this. At commercial scale it needs a paid plan or a self-hosted raster stack — we know that's a real cost and haven't hidden it.

**"How do you stop the AI hallucinating?"**
> Structurally — the model never produces a recommendation, only an explanation of one already computed. And we validate: any number in its output that isn't in its input causes rejection and a fallback to a template.

**"What if the soil data is wrong for a specific field?"**
> It will be, sometimes — it's a 250-metre model prediction, not a lab test. We show confidence levels, and we're planning to let farmers enter their own Soil Health Card values, which is a real measurement of their actual field.

### Harder — prepare these properly

**"Why is pH weighted 0.20 and not 0.15?"**
> Have the citation ready or concede. "Our current weights come from ICAR guidance on relative factor importance; we haven't empirically validated the exact values, and tuning them against yield data is our first post-hackathon step." **Do not invent a justification.**

**"Have you spoken to an actual farmer?"**
> If yes, say what you learned and what changed as a result. If no, say so and say when you will. Do not fabricate an interview — this is the question most likely to be followed up.

**"What happens if you recommend a crop and the farmer loses money?"**
> We present it as decision support with confidence levels and stated limitations, not a guarantee — the app never says "you will earn X", it says "expected yield is X". That's a deliberate wording choice. But we take the responsibility seriously, and it's why the system refuses to give advice it can't ground.

**"Isn't this just a wrapper around Earth Engine?"**
> Earth Engine gives raw pixel values. The work is turning those into a ranked, explained, economically-quantified recommendation — the scoring model, the crop thresholds, the cost data, and the explanation layer. Earth Engine is one input.

---

## 7. Things not to say

| Don't | Instead |
|---|---|
| "It worked five minutes ago" | Switch to fallback, keep moving |
| "This is just a prototype" | "This is what works today; here's what's next" |
| "We used AI/ML" (vague) | Name what it does and what it doesn't decide |
| "99% accurate" | Only claim what you measured |
| "Farmers will love this" | "We'd validate that with extension officers" |
| "Let me just quickly…" | Say nothing, do it |
| Filling silence with "um, so, basically" | Pause. Silence is fine. |

---

## 8. Rehearsal plan

Three full run-throughs minimum. Timed, standing, out loud, with the laptop.

| Run | Focus |
|---|---|
| 1 | Content — does everyone know their lines? Expect to overrun; cut words, not segments. |
| 2 | Handovers and timing — hit 5:00. Practise the failure switches deliberately. |
| 3 | Full dress — someone plays hostile judge and interrupts with the §6 hard questions. |

**Time every run.** If you're at 6:30 on run 3, you will be at 7:00 on the day, and you will be cut off during segment 6.

Record run 3 on a phone and watch it back. Painful, effective — it's the fastest way to catch the filler words and the fumbled handovers that nobody notices while speaking.

---

## 9. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Initial version for the internal round. Revise for the finale — longer slot, deeper technical questioning. |
