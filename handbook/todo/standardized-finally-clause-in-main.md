# standardized finally clause in main — deploytool

Every program's `finally` on exit should call `bottombar.shutdown()`, and every program's setup
should call `bottombar.init()`. Neither should use the deprecated `screen.init()` shim or a private
once-per-process flag.

Contract (bbsengine6 `bottombar`):
- `init()` runs once per process, and sets the scroll region on a tty only.
- `shutdown()` shuts down object fragments first, then, only if `init()` ran, clears the bottom bar line,
  resets colors and margins (`{reset}`), and restores the cursor. It never raises and does nothing without
  a tty.
- Interrupt and EOF messages print `{/all}*INTR*` / `{/all}*EOF*` with no cursor restore in the text, so
  `shutdown()` restores the cursor after the message.

Verify by driving the program under a pty, interrupting it, and checking that the exit bytes end in this
order: color reset, message, bar-line clear, color reset, margin reset, cursor restore.

## Open

- [ ] Check the deploytool CLI (`deploy`) for screen setup or an interrupt path. It writes only to the terminal through its own output, so if it has no bottombar setup, record that none is needed.
- [ ] If the CLI prints progress with `io.echo`, confirm it doesn't leave a scroll region set (it never calls `bottombar.init()`).
