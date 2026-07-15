from __future__ import annotations

from task5.src.stock_classification import run_pipeline


def main() -> None:
    result = run_pipeline()
    print(result["metrics"].to_string(index=False))


if __name__ == "__main__":
    main()
