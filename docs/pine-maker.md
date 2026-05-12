# Pine Maker

Pine Maker is the local error-memory path for turning AF model candidates into
TradingView-safe Pine code.

Runtime error memory is stored under the active target state root:

`state/targets/<target-id>/pi-autoresearch/runtime/pine-maker/compile-errors.jsonl`

Use it whenever TradingView returns a compiler error for generated Pine:

```powershell
npm run pine-maker -- record-error --target btc-15m-af --candidate cand-87051e0e --error "<TradingView compiler error>"
npm run pine-maker -- check --target btc-15m-af --candidate cand-87051e0e
```

The `check` command combines collected compiler errors with static preflight
rules, so repeated conversion mistakes are caught before the Pine source is sent
back to TradingView.

Current guarded pattern:

- `input.time(timestamp(...), ...)` is blocked because Pine requires a `const int`
  default value. Use a Unix millisecond integer literal instead, for example
  `input.time(1685539800000, "backtestStartTime")`.
- Empty Pine structures are blocked. Functions, `if`/`else`, loops, and `switch`
  statements must have at least one indented local expression, or the structure
  should be removed.
- Strategies with no executable side effect are blocked. A generated strategy
  must include at least one order-creating `strategy.*()` call or one visible
  output such as `plot*()`, `barcolor()`, `bgcolor()`, `hline()`, or a drawing.
