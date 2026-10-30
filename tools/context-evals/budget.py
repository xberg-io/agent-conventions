"""Persistent reservations bound paid calls across baseline runs, probes and judges."""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import runner

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class BoundedExecute:
    def __init__(self, path: Path, total: float, per_call: float, execute: runner.Execute) -> None:
        if not all(math.isfinite(n) and n > 0 for n in (total, per_call)) or per_call > total:
            raise runner.RunnerError("budget and per-call cap must be positive; per-call cannot exceed total")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.total, self.per_call, self.execute = path, total, per_call, execute
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (charged REAL NOT NULL, settled INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS limits (total REAL NOT NULL)")
            saved = db.execute("SELECT total FROM limits").fetchone()
            if saved and saved[0] != total:
                raise runner.RunnerError("cannot change the total budget of an existing round")
            if not saved:
                db.execute("INSERT INTO limits VALUES (?)", (total,))

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def spent(self) -> float:
        with self.connection() as db:
            return db.execute("SELECT COALESCE(SUM(charged), 0) FROM calls").fetchone()[0]

    def reserve(self) -> int:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(charged), 0) FROM calls").fetchone()[0]
            if spent + self.per_call > self.total:
                raise runner.RunnerError(f"round budget exhausted: ${spent:.4f} reserved/spent of ${self.total:.2f}")
            return db.execute("INSERT INTO calls VALUES (?, 0)", (self.per_call,)).lastrowid

    def __call__(self, argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        if Path(argv[0]).name != "claude":
            return self.execute(argv, cwd, env, timeout)
        reservation = self.reserve()
        done = self.execute([*argv, "--max-budget-usd", str(self.per_call)], cwd, env, timeout)
        result = self.result(done.stdout)
        cost = result.get("total_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, int | float) or not math.isfinite(cost) or cost < 0:
            raise runner.RunnerError("paid call returned no valid cost; reservation retained, stopping round")
        with self.connection() as db:
            db.execute("UPDATE calls SET charged = ?, settled = 1 WHERE rowid = ?", (cost, reservation))
        case_limit = result.get("subtype") == "error_max_turns"
        if cost > self.per_call or done.timed_out or ((done.returncode or result.get("is_error")) and not case_limit):
            evidence = self.path.parent / "failed-calls"
            evidence.mkdir(exist_ok=True)
            (evidence / f"{reservation}.jsonl").write_text(done.stdout)
            raise runner.RunnerError(
                f"paid call failed ({result.get('subtype')}, ${cost:.4f}, cap ${self.per_call:.2f}); stopping round"
            )
        return done

    @staticmethod
    def result(stdout: str) -> dict:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        for line in reversed(stdout.splitlines()):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "total_cost_usd" in data:
                return data
        return {}
