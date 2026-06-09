from __future__ import annotations


def run(question: str, **kwargs) -> dict:
    answer = f"Sample adapter answer for: {question}"
    contexts = [
        "This is a local Python adapter example.",
        "Replace this with your real retrieval and generation logic.",
    ]
    return {
        "answer": answer,
        "contexts": contexts,
        "raw_response": {"question": question, "kwargs": kwargs},
    }
