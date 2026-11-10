"""从回放库训练 BC 并导出 ONNX。

用法：
  python scripts/train_bc.py --db data/replays/produce.sqlite3 --out data/models/bc_produce.npz --onnx data/models/bc_produce.onnx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.runtime.replay import ReplayDB
from gkagent.training.bc import train_bc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/replays/produce.sqlite3")
    parser.add_argument("--label", default="index", choices=["index", "action", "reward"])
    parser.add_argument("--mode", default="auto", choices=["auto", "linear", "logistic", "softmax"])
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--out", default="data/models/bc_produce.npz")
    parser.add_argument("--onnx", default="data/models/bc_produce.onnx")
    parser.add_argument("--no-onnx", action="store_true")
    args = parser.parse_args()

    db = ReplayDB(args.db)
    X, y, meta = db.export_dataset(label=args.label)
    print(f"dataset: X={X.shape} y={y.shape} features={len(meta.get('feature_names', []))} skipped={meta.get('n_skipped')}")
    if X.shape[0] == 0:
        print("no replay rows; abort")
        return 1

    model = train_bc(X, y, mode=args.mode, epochs=args.epochs)
    print(f"loss: {model.loss_history[0]:.4f} -> {model.loss_history[-1]:.4f}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(out)
    print("saved", out)

    if not args.no_onnx:
        try:
            onnx_path = model.export_onnx(args.onnx)
            print("onnx", onnx_path)
        except Exception as exc:  # noqa: BLE001
            print("onnx skipped:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
