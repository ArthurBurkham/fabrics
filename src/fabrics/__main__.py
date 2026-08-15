import argparse
import sys

from . import run, FabricsInputError


def main():
    ap = argparse.ArgumentParser(prog="fabrics",
                                 description="Value your network, then value changing it.")
    ap.add_argument("folder", help="folder containing demand.csv, existing_facilities.csv, "
                                   "and optionally candidate_sites.csv + params.yaml")
    ap.add_argument("--out", default=None, help="output folder (default: <folder>/out)")
    args = ap.parse_args()
    try:
        run(args.folder, args.out)
    except FabricsInputError as e:
        print(f"\nFabrics can't run yet:\n\n{e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
