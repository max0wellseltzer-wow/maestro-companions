# Vouching: how a derived copy earns the right to answer

A derived copy (a cache, an index, a column-major mirror, a precomputed table) is a promise: "reading me gives what reading the
source would give". The promise holds only while the source has not changed since the copy was cut. Everything below is about
making that condition checkable in microseconds, failing safe when it is not, and auditing what the cheap check cannot see.

## The signature
Take it from the SOURCE, not the copy, and take it BEFORE reading the source to build the copy. For a plain file: size and
modification time (ns). For SQLite: the database file's size and mtime AND its write-ahead log's (an uncheckpointed write
changes the log, not the database; an empty log is no write - normalise it to "none", because a reader may create an empty one).
For a folder of files: the sorted list of (name, size, mtime). Store the signature in a small sidecar beside the copy, together
with the copy's own size and mtime (so a replaced copy is caught too). Why before: if you read the source, build the copy, and
only then take the signature, a write that landed during your read is signed as if it were included.

Size and mtime miss one case: an edit of the same length within the same mtime granularity (or a tool that preserves mtime). If
the source is edited by people with editors, add a content hash of each file; it costs one read per file at refresh time, not at
query time. Hash with line endings normalised when git may touch the file.

## The gate (every query, cheap)
    stored = read sidecar
    if stored is None or stored.source != signature(source) or stored.copy != stat(copy):
        answer from the exact slow path; print one line saying why; count it
    else:
        answer from the copy
A gate that fails closed costs time; a gate that fails open costs truth. Every doubt goes to the slow path. Count how many
queries fell back and print the count: a copy that is always stale is a bug you would otherwise never see.

## The audit (scheduled, thorough)
The gate compares signatures, not values; it cannot see a copy that was cut from the right source wrongly (a bug in the cutter),
nor a copy tampered with between sidecar checks. Give every copy a `verify` command that recomputes it from the source and diffs
byte for byte (or row by row with names), exits non-zero on any difference, and a `build`/`rebuild` command that cuts it again
atomically (write a temp file, then replace) and re-signs. Run `verify` in the nightly chain or after any job that writes the
source without going through the rebuild.

## The three states (from fast-path-proof)
current (serve), incomplete (holes: a missing row must be distinguishable from "the true value is undefined" - add a marker per
row or per file), behind (older than the source: the signature catches it). Write a test for each state with a planted
condition: a copy a day behind, a copy with one row removed, a copy with one byte flipped and the right date; each test names
which path answered.

## What to plant (tests that must go red)
- skip the signature comparison (serve always);
- compare only size, then edit a file keeping its size;
- take the signature after the read, then simulate a write during the read;
- make the gate too strict (always fall back): answers stay right - the test must assert the copy WAS used (a counter, a log line);
- corrupt one value in the copy and run `verify`: it must fail;
- replace the copy with identical bytes (new mtime): the sidecar must notice or the rebuild must re-sign.

## Words to use in the report
"served from the copy: N; fell back: M (reasons: ...)" - and the command that audits it. Never "the cache is fine".
