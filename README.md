# Agent Experiment Lab

Part of [Amplifier Constellation](https://github.com/microsoft/amplifier-constellation).

A standalone lab for investigating how independent agents collaborate and carry
work through. Define a scenario, connect the participants, observe their actual
contributions and delivery, and compare checked outcomes across repeated trials.

Read the [vision](docs/VISION.md) for intended value and the
[local contracts](docs/contracts.md) for scenario execution, evidence and recovery.
Shared meanings stay in the
[Constellation family agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/composition.md);
the [working guide](https://github.com/microsoft/amplifier-constellation/blob/main/docs/working-together.md)
applies Converge to contributions.

The runner and comparison commands are reusable
[Tools](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/tool.md);
reports provide an experiment [Experience](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/experience.md).
The Lab is optional, and a directly tested engine need not be wrapped as an Agent
Instance. Direct ACP attachment does not
reproduce another platform's timing, context or authority. Treat imported Slack
recordings as a separate condition. Report pages provide reference access to the
evidence; future ways of inspecting and judging it remain open to design.

## Native downloads

The native package includes its own Python and the pinned official ACP SDK.
Extract the matching package and run `agent-experiment-lab` (`.exe` on Windows);
no Python, Git, WSL or build tools are needed. Windows 11 x64 and ARM64, macOS
Intel and Apple silicon, and Linux x64 and ARM64 have separate packages. The
Lab remains a command-line experiment tool; it does not provision model accounts.

Keep the package files together. Replace the entire extracted package to update;
run folders remain separate, and unfinished or uncertain prompts are never
automatically replayed. These preview packages are unsigned and not notarized.
The [shared installation agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/installations.md#native-single-computer-setup)
owns the family platform promise. Source installation below is for contributors.

## Start locally

Python 3.11 or newer and Git are required. Install the pinned official ACP SDK in
a virtual environment before running the lab:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python3 -m experiment_lab --help
python3 -m unittest discover -s tests -v
python3 examples/fixture_demo.py --output /tmp/agent-lab-demo
```

Open `/tmp/agent-lab-demo/report.html`. This demonstration uses deterministic ACP subprocess fixtures, not language models or human proxies. It tests room separation, a late participant, an interrupted private draft, a revised requirement, and a separately evaluated artifact. The nine checks apply only to that exact Python artifact.

On Windows, activate with `.venv\Scripts\Activate.ps1`. Installation also adds the
`agent-experiment-lab` command. Every command works as `python -m experiment_lab`
in the environment where its dependencies are installed.

## Choose the question and boundary

| Work to do | Read |
| --- | --- |
| Connect actual engines and choose an independent evaluator | [Agent bindings and evaluation](docs/execution-reference.md#connect-actual-agents) |
| Define participants, rooms, steps and limits | [Scenario contract](docs/execution-reference.md#scenario-contract) |
| Resume interrupted runs without replaying uncertainty | [Recovery](docs/execution-reference.md#resume-and-ambiguous-outcomes) |
| Compare repeated conditions and interpret evidence | [Comparison](docs/execution-reference.md#repeat-and-compare) and [evidence](docs/execution-reference.md#understand-the-evidence) |
| Study replies, useful silence, handoffs or attention | [Attention experiments](docs/attention-experiments.md) |
| Study context, latency, compaction or delivery | [Harness experiments](docs/harness-experiments.md) |
| Import Slack evidence or submit a report to an optional management client | [External evidence and reporting](docs/execution-reference.md#existing-slack-recordings-and-optional-fleet-integration) |
| Change protocol integration | [SDK boundary](docs/execution-reference.md#acp-sdk-integration) |

Select a meaningful outcome and a check that could expose failure. Keep human
observations, model behavior, protocol checks and operator-authored expectations
distinct. Use current source and the actual configured engines to establish the
conditions for a new experiment; this entry point is not a running result ledger.

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
