"""
token_tracker.py — Thread-safe token usage accumulator.
Shared across all parallel Claude API calls in a run.
"""
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenTracker:
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    input_tokens: int  = 0
    output_tokens: int = 0
    api_calls: int     = 0

    # Rate limit info from last response (per-minute window)
    _rl_remaining: Optional[int] = field(default=None, repr=False)
    _rl_limit: Optional[int]     = field(default=None, repr=False)

    def add(self, input_tokens: int, output_tokens: int,
            rl_remaining: Optional[int] = None,
            rl_limit: Optional[int] = None) -> None:
        with self._lock:
            self.input_tokens  += input_tokens
            self.output_tokens += output_tokens
            self.api_calls     += 1
            if rl_remaining is not None:
                self._rl_remaining = rl_remaining
            if rl_limit is not None:
                self._rl_limit = rl_limit

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def summary(self) -> str:
        if self.api_calls == 0:
            return "📊 Token tracking disabled (ANTHROPIC_API_KEY not set)"
        lines = [
            "━" * 50,
            "📊 Token Usage",
            f"   API calls:     {self.api_calls}",
            f"   Input tokens:  {self.input_tokens:,}",
            f"   Output tokens: {self.output_tokens:,}",
            f"   Total tokens:  {self.total_tokens:,}",
        ]
        if self._rl_limit and self._rl_remaining is not None:
            used_pct = round(
                (self._rl_limit - self._rl_remaining) / self._rl_limit * 100, 1
            )
            lines += [
                "",
                "   Rate limit window (per minute):",
                f"   Limit:     {self._rl_limit:,} tokens",
                f"   Remaining: {self._rl_remaining:,} tokens  ({100 - used_pct:.1f}% available)",
            ]
        lines.append("━" * 50)
        return "\n".join(lines)


# Global singleton — imported and shared by discover.py and analyze.py
tracker = TokenTracker()