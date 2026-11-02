"""Independent run checkpoints with bounded concurrent clients."""
import asyncio
from pathlib import Path

from .analysis import compare, report
from .engine import Engine
from .scenario import ID, require, validate_bindings
from .storage import Run, read, write


async def batch(manifest_path, output, loader):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    manifest = read(manifest_path)
    require(manifest.get("schema") == "agent-experiment-lab.batch/1", "Unsupported batch schema")
    cases = manifest.get("cases", [])
    require(isinstance(cases, list) and 1 <= len(cases) <= 20, "Use 1–20 batch cases")
    parallel = manifest.get("max_parallel", 1)
    require(isinstance(parallel, int) and 1 <= parallel <= 8, "Use 1–8 parallel runs")
    require(len({case["id"] for case in cases}) == len(cases), "Batch case IDs must be unique")
    runs = []
    for case in cases:
        require(ID.fullmatch(case.get("id", "")), "Invalid batch case ID")
        repetitions = case.get("repetitions", 1)
        require(isinstance(repetitions, int) and 1 <= repetitions <= 20, "Use 1–20 repetitions")
        scenario = loader((manifest_path.parent / case["scenario"]).resolve())
        bindings = validate_bindings(read((manifest_path.parent / case["bindings"]).resolve()), scenario)
        for repetition in range(1, repetitions + 1):
            path = output / f'{case["id"]}-{repetition:02d}'
            run = Run.create(path, scenario, bindings)
            run.data["batch"] = {"case_id": case["id"], "repetition": repetition, "max_parallel": parallel,
                                  "agent_memory_isolation": "not_guaranteed_by_client"}
            run.save()
            runs.append(run)
    write(output / "batch.json", {"manifest": manifest, "runs": [str(run.path) for run in runs]})
    slots = asyncio.Semaphore(parallel)

    async def one(run):
        async with slots:
            with run.lock():
                try:
                    await Engine(run).execute()
                except Exception as exc:
                    run.data.update(status="error", error_type=type(exc).__name__)
                    run.save()
                report(run)

    await asyncio.gather(*(one(run) for run in runs))
    return compare(runs, output / "comparison")
