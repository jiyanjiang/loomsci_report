# LoomSci Report

Chinese-first research report app for LoomSci Core.

## Pipeline

The app runs a staged LLM pipeline, not a retrieval template:

```text
query planning
-> arXiv + OpenAlex retrieval
-> per-source claim extraction
-> relevance ranking
-> thesis + section plan
-> parallel Chinese section writing
-> critic rewrite
-> evidence gate
-> Core item
```

Target runtime is 5-10 minutes. A few seconds means only retrieval ran.

## DeepSeek key

Resolution order:

```text
DEEPSEEK_API_KEY / DS_KEY
~/.loomsci/config.yaml  (llm.providers.deepseek.api_key)
~/.taa/config.toml      (llm.deepseek_api_key)
DEEPSEEK_KEY_FILE
```

Keys are never logged.

Primary model is `deepseek-v4-flash`; if it fails or returns empty, the client
falls back to Alibaba DashScope `qwen-plus`.

```text
DEEPSEEK_MODEL=deepseek-v4-flash
ALI_MODEL=qwen-plus
DASHSCOPE_API_KEY / ALIBABA_API_KEY / QWEN_API_KEY
```

Ali keys are also read from `~/.loomsci/config.yaml` and
`~/.taa/config.toml` (`llm.alibaba_api_key`).

## Retrieval

OpenAlex is the primary metadata layer. The arXiv API is optional because it is
rate-limited aggressively:

```bash
LOOMSCI_USE_ARXIV=1   # opt-in enrichment; default is OpenAlex only
```

OpenAlex abstracts are reconstructed from `abstract_inverted_index`.

## Figure/table facts

Only OA PDFs with an allowlisted reuse license are opened. The fact library
stores the caption, label, page, license and source URL; the image itself is
linked, not redistributed.

```text
cc-by / cc-by-3.0 / cc-by-4.0 / cc-by-sa / cc0 / public-domain
```

## Evidence

Sources are online APIs only. The app does not read a local arXiv database.

Before prose is written, each source produces one traceable claim. The draft
must cite source IDs such as `[S001]`. The deterministic gate checks independent
domains, strong sources and citations. Gate pass means the evidence contract is
met; it is not a truth proof.

## Development

```bash
python3 -m unittest discover -s tests -q
```

See [docs/perspective-style.md](docs/perspective-style.md) and
[prompts/perspective.md](prompts/perspective.md).
