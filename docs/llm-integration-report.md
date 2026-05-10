# LLM Integration Report — The Wandering Goblet

## Technical decisions and integration strategy

The Wandering Goblet integrates a local large language model through
[Ollama](https://ollama.com/) over its `localhost:11434` HTTP API. The
default model is `llama3.2:3b`, swappable at runtime via `--model` or
the in-game settings menu. The game is written in Python with Pygame,
chosen because Ollama's official Python client and the wider Python
ecosystem give the cleanest path to two specific features the design
needs: token-by-token streaming for chat, and `format: "json"`
constrained output for decisions.

The integration is split across three small modules. `ollama_client.py`
owns the HTTP transport and exposes two surfaces — `chat_stream` for
free-form, streamed dialogue and `json_call` for one-shot structured
replies — and logs every prompt/response pair so a `--demo` session can
dump a reproducible JSONL transcript. `prompts.py` builds three prompt
families (chat, haggle, quest) from shared persona-card and
world-state blocks, so a refinement to either propagates everywhere.
`parsers.py` validates JSON-mode replies through Pydantic models,
clamps out-of-range numbers, and provides a `call_with_retry` harness
that retries once and then degrades gracefully so gameplay never hangs
on a misbehaving model. The split — *transport, prompt, parse* — was
the single biggest reliability win of the project.

The most important design choice is what the LLM is *not* allowed to
do. It generates dialogue, soft beats (accept, refuse, counter, walk
away, "rumour"-flagged sentences), and quest text, but it never
mutates gold or inventory. Those are owned by `WorldState` in plain
code, with hard clamps on every value the model emits. The model can
colour the negotiation; it cannot break the economy. This is a
deliberate echo of the "trust but verify" pattern the Ollama docs
recommend.

## Performance considerations

The game targets a no-GPU 16 GB Windows laptop. On that hardware
`llama3.2:3b` produces a first token in roughly 1.5 s once the daemon
is warm and streams at around 30 tokens/s, well inside the 2-second
budget set in `ollama-plan.md`. Three techniques keep latency low.
First, **streaming**: tokens flow into the dialogue box as they arrive,
so perceived latency is time-to-first-token rather than time-to-finish.
Second, **a 6-turn sliding memory window**: older chat turns are
dropped while the persona card is re-injected every turn, keeping
prompts short without losing voice consistency. Third, **`keep_alive:
10m`**: Ollama keeps the model resident between calls so subsequent
prompts skip the cold-start cost.

JSON-mode calls are not streamed (the schema requires a complete
object), so the input bar is locked while a customer "thinks" and a
toast explains why. End-to-end haggle and quest calls finish inside
four seconds in normal play. The retry/degrade harness ensures even
failures surface within roughly twice that time and never block the
frame loop, since all LLM work runs on a daemon thread that posts back
through a queue.

## Gameplay impact and workflow evaluation

Putting the LLM behind real gameplay decisions — not just flavour —
changed the project meaningfully. Haggling carries weight because the
customer's voice and their accept/refuse are produced by the same
call: an irritable dwarf actually refuses an obvious lowball offer in a
voice you can read. Gossip persistence, where a line from one customer
re-enters later customers' prompts, makes the bar feel like a single
shared world rather than a stage that resets. The five hand-authored
personas plus the JSON world-state are still the load-bearing wall;
the LLM colours their interaction surface.

The development workflow benefited from the local model in two
non-obvious ways. Iterating on prompts at 30 tokens/s and zero cost
let `prompts-used.md` accumulate a long list of tried-and-rejected
variants. And the fixed-seed `--demo` flag, paired with the prompt
log, made it possible to reproduce specific scenes for video evidence
without scripting them by hand.

## Ethical considerations

A small banner across the top of the screen tells the player on every
launch that NPC dialogue is generated locally by an LLM, naming the
model. It can be hidden with `T`, but it is **on by default** so first
contact is always informed. The README and the high-concept document
both repeat the disclosure, and the model name appears in the in-game
status bar. No player chat ever leaves the machine; Ollama runs on
`localhost` and there is no telemetry or third-party API.

Crediting follows the model's licence: `llama3.2:3b` is shipped under
Meta's Llama 3.2 Community License, linked in the README alongside
the Pygame and Pydantic licences. AI tools used during development
(Cursor with Claude as a coding assistant, plus the same local Llama
model for prompt iteration) are disclosed in `refinements-changes.md`
with specific entries marking which decisions were AI-assisted. The
goal across all of these surfaces is the same: a player or marker
should never have to wonder where text in this game comes from.
