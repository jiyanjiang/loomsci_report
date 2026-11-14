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

Model default is `deepseek-chat`; override with `DEEPSEEK_MODEL`.

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
