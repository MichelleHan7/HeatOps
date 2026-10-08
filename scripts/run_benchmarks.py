import argparse

from heatops.benchmark.runner import run_benchmarks

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="benchmarks/final.json")
    p.add_argument("--output-dir", default="reports")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    run_benchmarks(a.manifest, a.output_dir, resume=a.resume)
