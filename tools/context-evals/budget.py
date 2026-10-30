"""Prospective accounting for a CLI whose dollar limit cannot enforce a hard ceiling."""

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


class BudgetedExecute:
    def __init__(
        self,
        path: Path,
        total: float,
        per_call: float,
        execute: runner.Execute,
        *,
        allow_soft_limits: bool = False,
    ) -> None:
        if not all(math.isfinite(n) and n > 0 for n in (total, per_call)) or per_call > total:
            raise runner.RunnerError("budget and per-call cap must be positive; per-call cannot exceed total")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.total, self.per_call, self.execute = path, total, per_call, execute
        self.allow_soft_limits = allow_soft_limits
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS calls (charged REAL NOT NULL, settled INTEGER NOT NULL)")
            self.initialize_limit(db)
            db.execute("CREATE TABLE IF NOT EXISTS round_stop (id INTEGER PRIMARY KEY CHECK(id = 1), reason TEXT)")
            db.execute("INSERT OR IGNORE INTO round_stop VALUES (1, '')")

    def initialize_limit(self, db: sqlite3.Connection) -> None:
        if db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'limits'").fetchone():
            legacy = db.execute("SELECT total FROM limits").fetchall()
            if len(legacy) > 1:
                raise runner.RunnerError("ambiguous legacy budget limits; refusing execution")
            if legacy and legacy[0][0] != self.total:
                raise runner.RunnerError("cannot change the total budget of an existing round")
        db.execute(
            "CREATE TABLE IF NOT EXISTS round_limits (id INTEGER PRIMARY KEY CHECK(id = 1), total REAL NOT NULL)"
        )
        db.execute("INSERT OR IGNORE INTO round_limits VALUES (1, ?)", (self.total,))
        if db.execute("SELECT total FROM round_limits WHERE id = 1").fetchone()[0] != self.total:
            raise runner.RunnerError("cannot change the total budget of an existing round")

    def stop(self, reason: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE round_stop SET reason = ? WHERE id = 1", (reason,))

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
            reason = db.execute("SELECT reason FROM round_stop WHERE id = 1").fetchone()[0]
            if reason:
                raise runner.RunnerError(f"round stopped: {reason}")
            spent = db.execute("SELECT COALESCE(SUM(charged), 0) FROM calls").fetchone()[0]
            if spent + self.per_call > self.total:
                raise runner.RunnerError(f"round budget exhausted: ${spent:.4f} reserved/spent of ${self.total:.2f}")
            return db.execute("INSERT INTO calls VALUES (?, 0)", (self.per_call,)).lastrowid

    def __call__(self, argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        if Path(argv[0]).name != "claude":
            return self.execute(argv, cwd, env, timeout)
        if not self.allow_soft_limits:
            raise runner.RunnerError("Claude CLI dollar limits are soft; hard-ceiling execution is unsupported")
        reservation = self.reserve()
        try:
            done = self.execute([*argv, "--max-budget-usd", str(self.per_call)], cwd, env, timeout)
        except BaseException:
            self.stop("execution interrupted; billing is uncertain")
            raise
        result = self.result(done.stdout)
        cost = result.get("total_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, int | float) or not math.isfinite(cost) or cost < 0:
            self.stop("paid call returned no valid cost; reservation retained")
            raise runner.RunnerError("paid call returned no valid cost; reservation retained, stopping round")
        case_limit = result.get("subtype") == "error_max_turns"
        failed = (
            cost > self.per_call or done.timed_out or ((done.returncode or result.get("is_error")) and not case_limit)
        )
        with self.connection() as db:
            db.execute("UPDATE calls SET charged = ?, settled = 1 WHERE rowid = ?", (cost, reservation))
            if failed:
                db.execute("UPDATE round_stop SET reason = 'paid call failed or exceeded its soft limit' WHERE id = 1")
        if failed:
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
