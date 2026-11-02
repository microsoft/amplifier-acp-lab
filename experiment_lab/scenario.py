"""Versioned experiment manifests contain tasks, never endpoint credentials."""
import copy
import re

from .attention import validate_attention

ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(value):
    value = copy.deepcopy(value)
    require(value.get("schema") == "agent-experiment-lab.scenario/1", "Unsupported scenario schema")
    require(isinstance(value.get("label"), str) and 0 < len(value["label"]) <= 200, "Scenario needs a label")
    participants, rooms = value.get("participants", {}), value.get("rooms", {})
    require(1 <= len(participants) <= 16 and 1 <= len(rooms) <= 16, "Use 1–16 participants and rooms")
    for key, participant in participants.items():
        require(ID.fullmatch(key), "Invalid participant ID")
        require(participant.get("kind") in ("simulated_human", "support_agent", "protocol_fixture"), "Participant kind must distinguish simulations from people")
        require(isinstance(participant.get("label"), str), "Participant needs a label")
        require(isinstance(participant.get("role_instructions", ""), str) and len(participant.get("role_instructions", "")) <= 5000, "Role instructions must be bounded text")
    if "attention" in value:
        value["attention"] = validate_attention(value["attention"])
    memberships = {}
    for key, room in rooms.items():
        require(ID.fullmatch(key), "Invalid room ID")
        members = room.get("members", [])
        require(isinstance(members, list) and len(set(members)) == len(members), "Room members must be unique")
        require(all(member in participants for member in members), "Unknown room member")
        memberships[key] = set(members)
        require(room.get("type", "group") in ("direct", "group"), "Room type must be direct or group")
        require(room.get("type") != "direct" or len(members) == 2, "A direct room needs exactly two members")
    steps = value.get("steps", [])
    require(isinstance(steps, list) and 1 <= len(steps) <= 200, "Use 1–200 steps")
    for index, step in enumerate(steps):
        action, room = step.get("action"), step.get("room")
        require(room in rooms, f"Step {index}: unknown room")
        require(action in ("cue", "message", "round", "join", "leave"), f"Step {index}: unsupported action")
        if action in ("cue", "message"):
            require(isinstance(step.get("text"), str) and 0 < len(step["text"]) <= 20_000, "Cue text is required")
        if action == "message":
            require(step.get("speaker") in memberships[room], "Scripted message speaker must be a room member")
            require(step.get("provenance") == "operator_authored_fixture", "Scripted messages must explicitly declare fixture provenance")
        if action in ("join", "leave"):
            who = step.get("participant")
            require(who in participants, "Unknown membership participant")
            require((who in memberships[room]) == (action == "leave"), "Invalid membership transition")
            if action == "join":
                require(rooms[room].get("type") != "direct", "Create a group room before inviting another participant")
                memberships[room].add(who)
            else:
                memberships[room].remove(who)
        if action == "round":
            active = step.get("participants", sorted(memberships[room]))
            require(active and len(set(active)) == len(active) and set(active) <= memberships[room], "Round participants must be current room members")
            require(1 <= step.get("max_words", 300) <= 3000, "Invalid round word budget")
            private = step.get("private_context", {})
            require(isinstance(private, dict) and set(private) <= set(active) and all(isinstance(text, str) and len(text) <= 5000 for text in private.values()), "Private role context must be bounded and target an active participant")
            intervention = step.get("interrupt")
            if intervention:
                require(intervention.get("participant") in active, "Interruption target must be in this round")
                require(intervention.get("when") == "first_chunk", "Interruption trigger must be first_chunk")
                require(isinstance(intervention.get("text"), str) and 0 < len(intervention["text"]) <= 20_000, "Interruption needs an operator cue")
    limits = value.setdefault("limits", {})
    limits.setdefault("turn_seconds", 180)
    limits.setdefault("max_turns", 80)
    limits.setdefault("max_seconds", 1800)
    limits.setdefault("history_characters", 60_000)
    require(1 <= limits["turn_seconds"] <= 1800 and 1 <= limits["max_turns"] <= 1000, "Invalid turn limits")
    require(1 <= limits["max_seconds"] <= 86400 and 100 <= limits["history_characters"] <= 250_000, "Invalid observation limits")
    value.setdefault("seed", 1)
    require(isinstance(value["seed"], int), "seed must be an integer")
    for evaluation in value.get("evaluators", []):
        require(ID.fullmatch(evaluation.get("id", "")), "Evaluator needs an ID")
        require(evaluation.get("room") in rooms, "Evaluator room missing")
        require(not evaluation.get("participant") or evaluation["participant"] in participants, "Evaluator participant missing")
        command = evaluation.get("command")
        require(isinstance(command, list) and command and all(isinstance(arg, str) for arg in command), "Evaluator command must be an argv array")
        require(1 <= evaluation.get("timeout_seconds", 20) <= 120, "Invalid evaluator timeout")
    return value


def validate_bindings(value, scenario):
    require(value.get("schema") == "agent-experiment-lab.bindings/1", "Unsupported endpoint bindings schema")
    endpoints = value.get("participants", {})
    require(set(scenario["participants"]) <= set(endpoints), "Each participant needs an ACP endpoint")
    for key in scenario["participants"]:
        endpoint = endpoints[key]
        command = endpoint.get("command")
        require(isinstance(command, list) and command and all(isinstance(arg, str) for arg in command), "Endpoint command must be an argv array")
        require(isinstance(endpoint.get("cwd"), str) and endpoint["cwd"], "Endpoint needs an ACP cwd")
        require(isinstance(endpoint.get("env", {}), dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in endpoint.get("env", {}).items()), "Environment must contain strings")
        require(isinstance(endpoint.get("secret_env", {}), dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in endpoint.get("secret_env", {}).items()), "Secret environment must reference files")
    return copy.deepcopy(value)
