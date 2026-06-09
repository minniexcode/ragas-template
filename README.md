## Offline Ragas Evaluation

This repository now includes a minimal offline RAG evaluation pipeline built on top of `ragas`.

### What it expects

Export samples from your RAG application into a CSV or Excel file with these required columns:

- `question`
- `contexts`
- `answer`
- `ground_truth`

Optional metadata columns are preserved in the output:

- `sample_id`
- `scenario`
- `language`
- `retrieval_config`

`contexts` should be stored as a JSON array string so rank order is preserved.

### Run the evaluator

Set your OpenAI API key and then run:

```powershell
$env:OPENAI_API_KEY="your-api-key"
.\.venv\Scripts\python.exe ragas_examples\rag_eval\offline_eval.py `
  --input ragas_examples\rag_eval\sample_rag_eval_dataset.csv `
  --output outputs\ragas_scores.csv
```

Useful flags:

- `--judge-model` to override the OpenAI judge model. Default: `gpt-4o-mini`
- `--embedding-model` to override the embedding model. Default: `text-embedding-3-large`
- `--batch-size` to control Ragas evaluation batching
- `--max-samples` to run only the first N rows while iterating

### Output

The evaluator writes:

- a per-sample score CSV
- an additional `_invalid` CSV when rows are discarded during normalization
- a console summary with overall means and grouped means by `scenario` and `language`

### Notes

- The evaluator uses English metric prompts even when sample content is mixed Chinese and English.
- This repo includes a local compatibility shim because the current environment ships a `langchain-community` build that breaks `ragas` import on the VertexAI chat module path.
