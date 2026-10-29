# deploytool: install and deploy zoid6

> Status: written, not yet run end to end on minotaur. The dry-run plans for steps 1 and 3 were
> checked. Run the steps, then remove this note once they have worked.

Run these as `jam`, from the meta-repo at `/home/opencode/data/work`. Each block is one command.

## 1. Install deploytool (once per change to deploytool)

```
cd /home/opencode/data/work/deploytool && make deploy-tui PYTHON=python3.12 PIP="python3.12 -m pip"
```

This builds the wheel from the repo and installs it into your venv. Check it:

```
deploy --help >/dev/null && python -m pip show deploytool | head -2
```

## 2. One-time setup for the zoid6 group (once per host)

The zoid6 account's directories must be writable by the `zoid6` group, which jam is in. Run this
once, as root or as `zoid6`:

```
sudo -u zoid6 mkdir -p /home/zoid6/dist-wheels && sudo chmod -R g+rwX /home/zoid6/dist-wheels /home/zoid6/venv
```

## 3. Deploy the zoid6 venv

```
deploy zoid6.venv --with-deps
```

This runs, in order:

- `bbsengine6.venv`: installs the engine into your venv.
- `zoid6.wheels`: builds the five wheels from git HEAD, then stages them and the installer into
  `/home/zoid6/dist-wheels`. Its build step is `zoid6/scripts/build_zoid6_wheels.sh`, which deploy
  runs (it is labelled `helper:` in the output).
- `zoid6.venv`: installs the staged wheels into `/home/zoid6/venv` through the installer.

It ends with `deploy complete`. If a step stops with a message, the message names the one command
to run. Fix it, then run step 3 again.

## 4. Restart the daemon

```
sudo systemctl restart zoid6
```

Check it:

```
systemctl is-active zoid6
journalctl -u zoid6 --since "5 minutes ago" | grep -E "startup completed|PingService"
```

Expect `active`, and a `startup completed, <n> modules enabled` line with the new bed version in
`PingService`.

## If something fails

| Message | Do this |
|---|---|
| `is not writable by group zoid6` | Run the `chmod` in step 2. |
| `manifest names ..., which is not in` | The wheel build did not finish. Run step 3 again. |
| `zoid6.venv exited with rc=` | Read the installer output above it; fix that, then run step 3 again. |
