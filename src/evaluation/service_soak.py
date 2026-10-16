import argparse
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "benchmark_runs" / "20261015_105008_full_final_baseline"


def mem_available_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1048576
    return None


def process_rss_gb(name):
    usage = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip() != name:
                continue
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            rss = int((entry / "statm").read_text().split()[1]) * 4096 / 1073741824
        except (OSError, ValueError, IndexError):
            continue
        usage[cmdline] = rss
    return usage


def service_rss_gb(service_pid):
    try:
        return int(Path(f"/proc/{service_pid}/statm").read_text().split()[1]) * 4096 / 1073741824
    except (OSError, ValueError, IndexError):
        return None


class Sampler(threading.Thread):

    def __init__(self, service_pid, out_path, interval=5.0):
        super().__init__(daemon=True)
        self.service_pid = service_pid
        self.out_path = out_path
        self.interval = interval
        self.stop_event = threading.Event()
        self.answer_index = 0

    def run(self):
        with self.out_path.open("w") as out:
            out.write("time,answer_index,mem_available_gb,runner_max_gb,runners_total_gb,service_gb\n")
            while not self.stop_event.is_set():
                runners = process_rss_gb("llama-server")
                out.write(
                    f"{datetime.now().isoformat(timespec='seconds')},{self.answer_index},{mem_available_gb():.3f},"
                    f"{max(runners.values(), default=0):.3f},{sum(runners.values()):.3f},{service_rss_gb(self.service_pid) or 0:.3f}\n"
                )
                out.flush()
                self.stop_event.wait(self.interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ask the running service many questions and record memory over time.")
    parser.add_argument("--answers", type=int, default=50)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--service-pid", type=int, required=True)
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--label", default="soak")
    args = parser.parse_args(argv)

    definitions = {item["id"]: item for item in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    snapshot = {}
    for path in sorted((Path(args.snapshot) / "records").glob("*__r1.json")):
        record = json.loads(path.read_text())
        if (record.get("context") or {}).get("text") and not record.get("warmup"):
            snapshot[record["id"]] = record
    order = list(snapshot)
    plan = [order[index % len(order)] for index in range(args.answers)]

    run_dir = PROJECT_ROOT / "benchmark_runs" / f"{datetime.now():%Y%m%d_%H%M%S}_service_{args.label}"
    run_dir.mkdir(parents=True)
    sampler = Sampler(args.service_pid, run_dir / "memory.csv")
    sampler.start()
    rows = []
    try:
        for index, question_id in enumerate(plan, 1):
            sampler.answer_index = index
            definition = definitions[question_id]
            started = time.perf_counter()
            response = requests.post(f"{args.url}/ask", json={"question": definition["question"]}, timeout=900)
            elapsed = time.perf_counter() - started
            result = response.json()
            answer = result.get("answer") or ""
            baseline = snapshot[question_id]
            baseline_answer = baseline.get("answer") or ""
            baseline_chunks = {value.get("chunk_id") for value in (baseline["context"].get("evidence_map") or {}).values()}
            served_chunks = {reference.get("chunk_id") for reference in result.get("references") or []}
            facts = definition.get("facts", [])
            row = {
                "index": index,
                "id": question_id,
                "status": response.status_code,
                "error": result.get("error"),
                "seconds": elapsed,
                "generation_seconds": (result.get("metrics_seconds") or {}).get("generation"),
                "facts_total": len(facts),
                "facts_stated": sum(1 for fact in facts if re.search(fact["pattern"], answer, re.IGNORECASE)),
                "baseline_facts_stated": sum(1 for fact in facts if re.search(fact["pattern"], baseline_answer, re.IGNORECASE)),
                "same_evidence": served_chunks == baseline_chunks,
                "abstained": result.get("abstained"),
                "memory_reset": (result.get("telemetry") or {}).get("memory_reset"),
                "mem_available_gb_after": mem_available_gb(),
                "runner_max_gb_after": max(process_rss_gb("llama-server").values(), default=0),
            }
            rows.append(row)
            print(f"[soak] {index}/{len(plan)} {question_id}: {elapsed:.0f}s facts {row['facts_stated']}/{row['baseline_facts_stated']} "
                  f"same_evidence={row['same_evidence']} runner {row['runner_max_gb_after']:.2f} GB "
                  f"available {row['mem_available_gb_after']:.2f} GB", flush=True)
            (run_dir / "answers.json").write_text(json.dumps(rows, indent=2))
        time.sleep(15)
    finally:
        sampler.stop_event.set()
        sampler.join()
    health = requests.get(f"{args.url}/health", timeout=30).json()
    (run_dir / "health_after.json").write_text(json.dumps(health, indent=2))
    print(json.dumps({"run_dir": str(run_dir.relative_to(PROJECT_ROOT)), "health": health}, indent=2))


if __name__ == "__main__":
    main()
