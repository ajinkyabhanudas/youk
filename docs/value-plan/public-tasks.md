# Public task sets for the pilot (E1e)

Looked up on 2026-10-07. Anything marked unverified could not be confirmed in that lookup.

## Pick

SWE-bench Multilingual is the primary set. It is MIT licensed, small (300 instances), and each row
already carries the base commit, the issue text, the test patch, the failing and passing test
lists, the Docker image the tests run in, and the eval script. That is enough to grade without
building an environment per repo.

| language | instances |
|---|---|
| Ruby | 44 |
| Rust | 43 |
| PHP | 43 |
| Java | 43 |
| Go | 42 |
| C | 30 |
| JavaScript | 26 |
| TypeScript | 17 |
| C++ | 12 |

## Other sets considered

| set | licence | languages | why not first |
|---|---|---|---|
| Multi-SWE-bench (full and the 400-instance mini) | CC0 data, repo licences apply | Java, TS, JS, Go, Rust, C, C++ (mini adds Python) | no confirmed base-commit field, its own harness, images on a different registry |
| SWE-bench Pro v2 | harness MIT, repos deliberately copyleft, data licence unverified | Go, Python, JS, TS | only four languages, and the repos are copyleft |
| SWE-bench Verified | MIT | Python only | the domain is software in general |

SWE-Gym is a training set and was dropped.

## Sample review

The first sample is 27 tasks, three per language. Each statement was read to its first lines and two
were marked unfair. That check is shallow on purpose. A task whose statement hides the needed
behavior shows up in the pilot as one that bare never solves, and the design check drops those.

## Risks

- **Ceiling.** A leaderboard page listed top scores of 95 to 98 percent for Multilingual. That
  figure is unverified. If a bare run already solves most of these, they cannot separate arms. The
  design check already treats a task that bare always solves as a ceiling task, so the pilot
  decides it with data.
- **Emulation.** The images are x86_64 and this machine is arm64, so every grading run is
  emulated and slower. Some C and C++ builds may fail under emulation.
- **Underspecified issues.** Public issue text was not written to be a spec. Each sampled task is
  read before it is used, as for the mined ones.
- **Licences.** The dataset is MIT. Each repo keeps its own licence, so task files hold the issue
  text and ids but no repo code.

## How a public task runs

1. `public_tasks.py fetch` downloads all rows once.
2. `public_tasks.py sample` writes task files to `bench/tasks-public/`, spread across languages and
   repos, largest diffs first (within the limits), after dropping short statements, oversize diffs and rows with no
   failing test.
3. The runner makes a shallow checkout of the base commit on this machine and the agent edits it.
   The tests are not in the checkout.
4. Grading takes the agent's diff and hands it to the swebench harness, which applies the test
   patch and runs the eval script inside the instance image. No harness verdict is an
   infrastructure error, not a failed task.

## What was verified on this machine

One instance (gin-gonic gin 1805) was graded for real through the harness. The gold patch came back
resolved, a patch that changes nothing relevant came back unresolved, and a missing image came back
as an error with no verdict, which the grader returns as None. The harness pulls images through the
docker SDK, which ignores the platform setting, so the grader pulls the amd64 image first. Only this
one instance was run. The other eight languages use the same path but were not run, and a C or C++
image may still fail to build or time out under emulation.

Run the pilot on this set with `--tasks-dir bench/tasks-public`, so the mined and public sets stay
separate choices.
