import asyncio
import time


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


async def evaluate():
    # Placeholder metrics scaffold. Replace with annotated datasets.
    parsing_tp, parsing_fp, parsing_fn = 80, 20, 15
    normalization_tp, normalization_fp = 120, 25
    ndcg_at_5 = 0.71

    start = time.perf_counter()
    await asyncio.sleep(0.01)
    latency_ms = int((time.perf_counter() - start) * 1000)

    parsing_precision = safe_div(parsing_tp, parsing_tp + parsing_fp)
    parsing_recall = safe_div(parsing_tp, parsing_tp + parsing_fn)
    parsing_f1 = safe_div(2 * parsing_precision * parsing_recall, parsing_precision + parsing_recall)

    normalization_precision = safe_div(normalization_tp, normalization_tp + normalization_fp)

    print({
        "parsing_f1": round(parsing_f1, 4),
        "normalization_precision": round(normalization_precision, 4),
        "matching_ndcg": ndcg_at_5,
        "end_to_end_latency_ms": latency_ms,
    })


if __name__ == "__main__":
    asyncio.run(evaluate())
