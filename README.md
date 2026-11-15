# Agent Experiment Lab

Compare how agents collaborate and carry work through. Define a scenario, connect
participants, observe their contributions, and evaluate what they actually deliver
across repeated trials. Reports keep task results, interaction observations and
protocol behavior separate.

Part of [Amplifier Constellation](https://github.com/microsoft/amplifier-constellation).

## Get started

Download the matching [native release](https://github.com/microsoft/amplifier-acp-lab/releases)
for Windows, macOS or Linux. Extract the whole package and run
`agent-experiment-lab --help` (`agent-experiment-lab.exe` on Windows).
The package includes Python and the ACP SDK; no developer tools are required.
Preview packages are unsigned and not notarized.

To run an experiment:

1. Choose a question and a check that could show the result is wrong.
2. Define participants and rooms using the [scenario examples](examples/README.md).
3. Connect your installed agents with [private agent bindings](docs/execution-reference.md#connect-actual-agents).
4. Validate the scenario, run it, then open its generated `report.html`.

`validate` makes no agent connections. `run` submits actual prompts to the selected
agents and may use their models and tools. The Lab does not provide model accounts
or provision agents. Run folders contain private conversation content.

## Try the local demonstration

From a source checkout, use Python 3.11+ and a virtual environment:

```sh
git clone https://github.com/microsoft/amplifier-acp-lab.git
cd amplifier-acp-lab
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python examples/fixture_demo.py --output ./demo-run
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. Open
`demo-run/report.html`. This demonstration uses deterministic protocol fixtures,
not model accounts; it illustrates the experiment workflow.

## Guides

- [Run, evaluate, compare and recover experiments](docs/execution-reference.md)
- [Attention and participation experiments](docs/attention-experiments.md)
- [Context, latency and delivery experiments](docs/harness-experiments.md)
- [Contributor entry](AGENTS.md)

Keep uncertain outcomes when a connection or process stops. Recovery does not
automatically replay unfinished prompts or prove that a remote agent stopped.

## Contributing

Invited collaborators: follow [Join the work](https://github.com/microsoft/amplifier-constellation#join-the-work)
within your agreed access and scope. The notice below covers general public intake.

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
