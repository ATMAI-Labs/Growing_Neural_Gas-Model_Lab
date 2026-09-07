# Exact replay and the numerical runtime

The evidence launcher compares deterministic JSON values exactly. It has no
numerical tolerance. Reproduction on one runtime does not certify every Python
build, operating system, or architecture.

## Observed results

The capacity-controlled successor's full 20-seed artifact was produced with
CPython 3.14.7 on macOS 27 arm64. An independent full rerun on that local runtime
matched every deterministic field, excluding only `/environment`. Its source,
protocol, metrics and recorded hashes remain frozen.

The complete [Linux CI run at revision d805392](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/actions/runs/34084904065)
used Ubuntu 24.04 x64 and CPython 3.12.3 (runner image `20260831.293.1`). It
passed repository validation, all 57 tests and both historical experiment
replays. The new full panel failed exact comparison in precisely two fields:

| JSON pointer | Retained value | Linux replay |
| --- | ---: | ---: |
| `/seed_outcomes/6/arms/abrupt/phases/0/windows/11/cumulative_qe` | 247.088959816619 | 247.088959816618 |
| `/seed_outcomes/12/arms/abrupt/phases/0/windows/3/squared_loss` | 15.86791507134 | 15.867915071341 |

Every other compared field matched, including primary outcomes, bootstrap
intervals, recovery decisions, capacity checks and reported fingerprints.
These differences are about 10^-12 in two rounded window-loss fields. Their
specific numerical cause has not been isolated. This is an exact-replay
portability failure, even though it did not change the reported interpretation.
The failed run is retained as evidence; no fields are dropped and no tolerance
is introduced to turn it into a pass.

## CI reference and acceptance scope

The required `Repository integrity` job uses the explicit GitHub-hosted
`macos-26` arm64 runner with CPython 3.14.7. `actions/setup-python` is pinned to
its v7.0.0 commit. GitHub documents the [runner labels and architectures](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
and supplies the [CPython 3.14.7 arm64 runtime](https://github.com/actions/python-versions/releases/tag/3.14.7-31064857500).
This CI host is a second macOS runtime, not the original local machine. Its
current run must pass before claiming a CI reproduction. A hosted runner label
and Python version are not an immutable operating-system image.

The required job runs validation, all unit tests and all three registered full
experiments. A Linux validation-and-test job is a prerequisite, so failed Linux
contract or smoke checks cannot be bypassed by a macOS replay pass. Full Linux
replay is not a passing gate for the successor at this revision.

The frozen successor README's cross-platform CI language predates this full
Linux result. Read that expectation together with this observed failure record;
it is not evidence that the full panel reproduces exactly on Linux.

## Remaining work

Isolate the two numerical divergences across Python builds and system math
libraries before claiming broader portability. Any new arithmetic or rounding
policy requires its own versioned successor, declared protocol and regenerated
evidence. Preserve this runner, the recorded result and this failed replay
instead of refreshing hashes or precision after observing the result.
