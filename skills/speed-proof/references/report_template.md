# Speed report template (fill every line; a line you cannot fill is a finding)

**Claim:** <what> is <ratio>x faster; answers identical.
**Machine:** <cpu / RAM / "shared with N other jobs" or "idle">, Python <version>, <date>.
**Metric:** CPU seconds of the child process (user+system), min of <N> runs after one warm-up; median shown when spread > 20%.
**Benchmark declared:** <path to baseline.json>, committed <hash> BEFORE the first code change (sources' sha256 inside it).

| command | before (s) | after (s) | ratio | answers |
|---|---|---|---|---|
| <name> | <cpu_min> | <cpu_min> | <x.x>x | IDENTICAL / DIFFERENT (why) |

**Equality proof:** `bench.py compare` fingerprints (stripped: <which lines and why>); plus <slow path vs fast path diff on the
real data: N rows, 0 differences> / plus <damaged-input runs>.
**Where the time was:** top 3 lines of the profile before the change, with seconds. Imports: <x> s before, <y> s after.
**What changed (one line each):** <the structural change>; <the import change>; <the derived copy and its signature>.
**Derived copies:** <file>, signed by <signature fields>, audited by `<verify command>`, rebuilt by `<build command>`, served
<N> / fell back <M> on the real data.
**Planted bugs:** <K> planted, <K> killed (<list the mechanism-level ones>); survivors: <none / name + what was done>.
**Not sped up (and why):** <command or path> - <by design / out of budget / another session's file / needs a dependency the user
has not approved>.
**Dependencies:** none added / <name, declared where>.
**Rent verdict:** the code is <clearer / as clear / less clear> than before for the next reader because <one line>; <ship /
ship the plain version instead>.
