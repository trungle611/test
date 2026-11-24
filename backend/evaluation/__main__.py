import argparse
import json
import sys
from pathlib import Path

from .dataset import freeze, read_json
from .runner import run, write_json


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Khóa nhãn và đánh giá nhận diện Gemini")
    commands = parser.add_subparsers(dest="command", required=True)
    lock = commands.add_parser("freeze")
    lock.add_argument("manifest")
    lock.add_argument("--root", required=True)
    lock.add_argument("--output", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("lock")
    execute.add_argument("--root", required=True)
    execute.add_argument("--output", required=True)
    execute.add_argument("--split", choices=["dev", "test", "smoke"], required=True)
    execute.add_argument("--env-file")
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            value = freeze(read_json(args.manifest), args.root)
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, value)
            print(f"Đã khóa {len(value['cases'])} ảnh: {args.output}")
        else:
            value = run(args.lock, args.root, args.output, args.split, args.env_file)
            print(json.dumps(value, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Không thực hiện được: {exc}\n")


if __name__ == "__main__":
    main()
