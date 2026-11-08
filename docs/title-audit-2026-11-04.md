# Title audit after the nano model change — 2026-11-04

Scope: local Markdown documents ingested since commit `1461aa4` (2026-11-03
11:34:45 Europe/Madrid, 10:34:45 UTC), compared with local body/summary content
and the scheduled pipeline log. No original documents or titles were modified.

- 37 current documents: 34 posts and 3 tweets. Daily tweet compilations and
  podcasts with deterministic titles are excluded.
- The scheduled pipeline log contains 17 title generations after the change.
  These overlap the current inventory except for the earlier “Simon Willison -
  Qwen Can Interpret Model Weights- Running 3-8 27B on a Laptop Without Tools”
  title, whose exact file is no longer present. Its topic is coherent; the log
  alone cannot establish whether its API response completed. A later Qwen
  Substack article is present under a different source URL and title.
- Two current titles are clearly incomplete: `Federico` and `Noah Smith -`.
  Noah Smith's article discusses Anthropic's IPO valuation and upside/risks.
- Lesser quality issues: Simon Willison's “GitHub Sponsors Update” drops the
  October LLM digest topic; “John” omits Cook's surname; several titles include
  “Clipper”, likely influenced by capture filenames or metadata.
- Historical API status and token usage were not recorded. Truncation by the
  token limit is plausible, but cannot be proven retrospectively per document.
- The title input extractor also includes front matter in its 1,600-byte sample,
  which can crowd out the article body. This is a separate input-quality issue;
  this patch only changes response validation and the title output budget.

## Fix and validation

The shared AI helper checks incomplete status before extracting any text,
retries token-limit responses with twice the budget, and raises on exhausted
or otherwise incomplete responses. Failed title requests leave filenames intact.
Titles now start at 1,024 output tokens instead of the effective 128; language
detection and summary budgets are unchanged. The 1,024 setting is a conservative
starting budget, not a measured optimum. Retry warnings include model and budget.

Validation: 30 tests passed across title, summary and podcast processing, including
partial direct/nested output, retry exhaustion, and no rename after failure.

## Live 512-token trial

After the initial patch, the starting title budget was reduced from 1,024 to
512 and tested against all 37 current documents using the actual API. All 37
responses completed on the first attempt; none required a larger budget.
Output usage, including reasoning, ranged from 165 to
447 tokens (mean 238.8). Both `Federico` and `Noah Smith -`
generated complete topic-bearing titles (204 and 189 output tokens).

The trial consumed 20,926 input tokens and 8,834 output tokens, including
6,336 reasoning tokens. At the official standard GPT-5 nano rates ($0.05/M
input, $0.005/M cached input, $0.40/M output), its estimated cost was
$0.004580, or $0.1238 per 1,000 titles at this sample's consumption.
These estimates exclude taxes and language detection, which was not called in
the trial and whose production budget is unchanged. The token limit is a ceiling;
it is not the number of tokens automatically charged. Historical cost differences
cannot be measured because previous per-request usage was not saved.

This is one live run on current stored content, not a replay of the original
requests. Existing front matter (including previously generated titles) remains
in the snippets; logged original filename hints were used where available.
Language was determined locally for the experiment. This evaluates completion
and consumption; it does not resolve the separate front-matter input-quality issue.
The generic Simon Willison title and the abbreviated “John” attribution persisted.
No article files were changed. Detailed requests, generated titles and usage:
[title-budget-trial-2026-11-04.json](title-budget-trial-2026-11-04.json).
Pricing: https://developers.openai.com/api/docs/pricing

Validation after reducing the budget: 40 targeted tests passed.

## Current inventory

Times below are UTC, from `docflow_ingested_at`.

| Ingested at | Type | Title | Review |
| --- | --- | --- | --- |
| 2026-11-03T11:00:26Z | Tweets | Tweet - Andrej Karpathy - Weekend Hack- HackerTube—Claude-Powered Video Curation from 43M Comments | No obvious title truncation; topic consistent with local content |
| 2026-11-03T11:00:32Z | Tweets | Tweet - Mike Knoop - ARC Prize 2026- $1M Open-Source ARC-AGI Challenge & Final Winners Dec 4 | No obvious title truncation; topic consistent with local content |
| 2026-11-03T11:01:00Z | Tweets | Tweet - Rikiya Takehi - Thread- Weight-Space Programming—Frontier LLMs Read-Write Neural Weights | No obvious title truncation; topic consistent with local content |
| 2026-11-03T11:09:07Z | Posts | rikiyat-github-io - Sparks of Weight-Space Programming- LLMs can natively read & write neural network weights | No obvious title truncation; topic consistent with local content |
| 2026-11-03T13:07:53Z | Posts | AINews - Weight Space Programming- LLMs Edit Small Network Weights to Bypass PyTorch-JAX Experiments | No obvious title truncation; topic consistent with local content |
| 2026-11-03T13:08:02Z | Posts | Simon Willison @simonw - GitHub Sponsors Update | Too generic: omits October LLM digest |
| 2026-11-03T15:07:47Z | Posts | Asymco - The Ternus Doctrine- How John Ternus Reframes Apple's Strategy Around People, Products, and Execution | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:00:58Z | Posts | Daniel Arjona - Todo lo que pueda hackearse va a ser hackeado- lecciones históricas sobre señales falsas y vulnerabilidades digitales | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:01:06Z | Posts | Zvi Mowshowitz - If Youre Helping Build Something That Might Kill Everyone, Stop (And Tell Others to Stop Too) | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:01:11Z | Posts | Paul Henderson, Federica Nicolardi - Writing Seen in PHerc- 306B- Reading the Vesuvius Scroll After Its Eruption | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:01:18Z | Posts | Alexander Kruel - Clipper Links for 2026-11-02- Linux IPv4 TCP UAF Exploit, Quantum Calibration Law, and Ukraine Tech Developments | Topic present, but capture-related wording needs review |
| 2026-11-03T16:01:24Z | Posts | Import AI - Spacewar Low-Latency- Realtime-Bench Evaluates AI Agents on 50 Dynamic Tasks Across Wall-Clock and Token Clocks | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:01:30Z | Posts | Kent Beck - Not a Copier- Rethinking Genie-like Task Delegation in Software | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:01:35Z | Posts | Noah Smith - | Incomplete title: author only |
| 2026-11-03T16:01:41Z | Posts | Pau Brunet Fuertes - Taquillas del fin de semana Halloween- afluencia baja y la estrategia de Netflix con La bola negra expandiéndose a más salas | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:02:16Z | Posts | Miguel A- Román - GDPx- el benchmark de SemiAnalysis sitúa a los mejores modelos en solo un 12% de media | No obvious title truncation; topic consistent with local content |
| 2026-11-03T16:02:26Z | Posts | José Ramón Pérez Agüera - Clipper- qué instalar y qué no para que tu flujo funcione | Topic present, but capture-related wording needs review |
| 2026-11-03T22:30:36Z | Posts | Simon Willison - October 2026 Newsletter- Vibe Game Dev, Vulnerability Apocalypse, LLM Releases, and $100+-month API Credits | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:30:49Z | Posts | Six Colors - He admit it!- Notes from another record Apple quarter | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:30:55Z | Posts | Apple - Apple Reports Fourth Quarter 2026 Results- Revenue $114-5B, EPS $2-10, Record iPhone and Services | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:31:04Z | Posts | Six Colors - Hello, everyone, its John- Apples Q4 2026 earnings call transcript | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:31:12Z | Posts | Six Colors - OLED iPad mini review- A modern multitasker | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:31:19Z | Posts | John - Spherical and Projective Geometry- From Great Circles to the Projective Plane and Polars | Topic retained; author surname omitted |
| 2026-11-03T22:31:26Z | Posts | John Cook - Hack to Rigor- From a Graphic Programmers Hack to a Rigorous Projective Plane Definition | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:31:32Z | Posts | Xataka - El auge de la IA en Macs- OpenClaw impulsa el Mac mini y Siri queda como asistente | No obvious title truncation; topic consistent with local content |
| 2026-11-03T22:31:47Z | Posts | Federico | Incomplete title: author only |
| 2026-11-04T06:44:53Z | Posts | Reyk Knuhtsen, Jeremie Eliahou Ontiveros, Dylan Patel - Making 13GW in 1-5 Years- Repurposing Rocket Ship Campuses and a TeraFab Datacenter | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:04Z | Posts | Alberto Romero - The Dawn of a New AI Paradigm- Weight Clipper and the Possibility of Recursive Self-Improvement | Topic present, but capture-related wording needs review |
| 2026-11-04T06:45:10Z | Posts | Pragmatic Engineer – How Software Engineering Is Changing- A Tale of Two Eras | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:17Z | Posts | euge - Navegar lo incierto- la orientación de la naturaleza frente a la luz de las pantallas | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:24Z | Posts | Cremieux - Is this really where longevity science needs to go | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:30Z | Posts | Zvi Mowshowitz - OpenAI Updates Its Model Spec- A Diff-Focused Look at Five Core Values | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:35Z | Posts | Simon Willison - Qwen 3-8 27B on my laptop can interpret model weights | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:40Z | Posts | Sergio Parra - A favor del desacuerdo y la polarización | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:46Z | Posts | eferro - Building for Cheap Complexity- Designing Lean Solutions Without the Cumulative Cost | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:51Z | Posts | Antonio Ortiz - El algoritmo de la plataforma- equilibrio entre usuarios, creadores y anunciantes (y la visión del agente de IA que prioriza al usuario) | No obvious title truncation; topic consistent with local content |
| 2026-11-04T06:45:57Z | Posts | Sergio San Juan - De coleccionar frases virales a cambiar- cómo convertir atención en acción con Simone Weil y un club de lectura | No obvious title truncation; topic consistent with local content |

## Applied title repairs

On 2026-11-04, seven titles identified in this audit were corrected manually,
including both incomplete titles, the generic Simon Willison digest title, the
abbreviated John D. Cook attribution, and the three capture-related “Clipper”
artifacts. Markdown and HTML names and title/path metadata were synchronized;
HTML title elements were updated. Article bodies, document IDs and file mtimes
were verified unchanged. Canonical state references were checked and capture
queue references updated; none of the seven had a hashed reading-position or
highlight file to migrate. A backup and mapping manifest were saved locally at
`/tmp/docflow-title-repair-20261104/`. The operational shared lock covered changes
and browse/reading/done index regeneration. The 512-token budget is retained.

- `Federico` → `Federico Viticci - How to Easily Create Multiple Windows for the Same App on iPhone Duo`
- `Noah Smith -` → `Noah Smith - Anthropics Moat Is Claude - The Bull Case for Anthropics IPO`
- `Simon Willison @simonw - GitHub Sponsors Update` → `Simon Willison - LLM Digest October 2026 - Vibe Game Development and the Vulnerability Apocalypse`
- `John - Spherical and Projective Geometry- From Great Circles to the Projective Plane and Polars` → `John D Cook - Spherical and Projective Geometry - From Great Circles to the Projective Plane and Polars`
- `Alberto Romero - The Dawn of a New AI Paradigm- Weight Clipper and the Possibility of Recursive Self-Improvement` → `Alberto Romero - The Dawn of a New AI Paradigm - Direct Neural Network Weight Editing and Recursive Self-Improvement`
- `Alexander Kruel - Clipper Links for 2026-11-02- Linux IPv4 TCP UAF Exploit, Quantum Calibration Law, and Ukraine Tech Developments` → `Alexander Kruel - Links for 2026-11-02 - Linux IPv4 TCP Exploit, Quantum Calibration, and Ukraine Tech`
- `José Ramón Pérez Agüera - Clipper- qué instalar y qué no para que tu flujo funcione` → `José Ramón Pérez Agüera - Qué instalar y qué no para programar con agentes - Evidencia y frenos que el agente no pueda editar`
