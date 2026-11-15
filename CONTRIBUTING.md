# Contributing

Each plugin has its own tests (`python3 -m unittest discover -s tests` in the plugin's folder) and the repo has its own (the same command here). Run both before a pull request.

## Code quality checklist

The same five problems came up in review after review of the generators in this repo. Check a change against them before asking for review, and add tests for the error paths, not only the happy path.

1. **Clear errors, not raw exceptions.** Bad input data or a layout the code cannot handle stops with the plugin's own error and a message that names the thing at fault (for example `SchematicError` in `schematic-maps`). A `KeyError`, `ValueError`, `TypeError` or `StopIteration` from the data must never reach the user.
2. **No silent fallbacks.** Never guess, use a default, or skip something without saying so. Either stop with a clear error, or log what was done and why.
3. **Check after changing things.** After code moves, slides, merges or splits something (a block boundary, a mast, a cut), check that what the rest of the code relies on still holds: order along the track, minimum lengths, nothing overlapping, the same blocks either side. Fail loudly if it does not.
4. **Validate input up front.** Check every settings or data file for shape, types, ranges and unknown keys at the boundary, before any heavy work starts.
5. **Reuse, don't rebuild.** Use the shared helpers instead of copying them, and build indexes or lookups once rather than on every call.

## Reviews

A review may report more findings than are worth fixing at once. Sort them: fix correctness bugs now, check each unverified finding against the code before acting on it, and leave speed and style points for a later cleanup unless they are trivial.
