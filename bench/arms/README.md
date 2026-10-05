# Arms

The SessionStart hook picks an arm per session (`servers/shared/arms.py`) and injects:

| Arm | Injected | Gates | Events |
|---|---|---|---|
| `full` | the server's session brief (current youk) | on | yes |
| `lean` | `lean/context.md` only | on | yes |
| `bare` | nothing | off (Edit/Write and close gates skipped) | yes |

`YOUK_ARM=<arm>` pins the arm. `YOUK_ARM_MODE=randomize` assigns by session hash instead.
Without either, sessions run `full`, so ordinary work is never silently ungated.
`superpowers` is not a youk arm: S10 runs it in a separate config directory without youk's hooks.
