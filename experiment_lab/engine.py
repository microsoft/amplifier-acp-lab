"""A bounded conversation experience, with private drafts and explicit delivery."""
import asyncio
import json
import random
import time
import uuid

from .acp import Client
from .attention import instructions
from .scenario import validate, validate_bindings
from .storage import digest, driver_identity, now, read


def room_messages(data, room):
    return [message for message in data["messages"] if message["room"] == room]


def publish(run, room, speaker, kind, text, **metadata):
    message = {"id": str(uuid.uuid4()), "seq": len(run.data["messages"]) + 1,
               "at": now(), "room": room, "speaker": speaker, "kind": kind,
               "text": text, **metadata}
    run.data["messages"].append(message)
    run.save()
    return message


def projection(run, scenario, room, participant):
    messages = room_messages(run.data, room)
    bounded, size = [], 0
    for message in reversed(messages):
        length = len(message["text"])
        if size + length > scenario["limits"]["history_characters"]:
            break
        bounded.append(message)
        size += length
    receipts = []
    for turn in run.data["turns"]:
        if turn["participant"] == participant and turn["room"] == room and turn.get("delivery"):
            receipts.append({key: turn.get(key) for key in ("id", "delivery", "message_id", "reason", "stop_reason")})
    return {"room": room, "experience": "lab_acp", "your_participant_id": participant,
            "conversation_type": scenario["rooms"][room].get("type", "group"),
            "your_role_instructions": scenario["participants"][participant].get("role_instructions", ""),
            "attention_condition": scenario.get("attention", {"policy": "baseline", "scheduling": "simultaneous"}),
            "participants": {key: {name: value for name, value in scenario["participants"][key].items() if name != "role_instructions"} for key in run.data["members"][room]},
            "history": list(reversed(bounded)), "history_truncated": len(bounded) < len(messages),
            "public_seq": len(run.data["messages"]),
            "response_delivery": {"items": receipts[-20:], "truncated": len(receipts) > 20}}


def prompt(step, data):
    return (
        "You are participating through the Experiment Lab conversation experience. "
        "This is an isolated simulation, not Slack, and simulated people are not actual human feedback. "
        "Use your installed identity and guidance; the lab does not change your permissions. "
        "Respond naturally to the visible conversation if you have something useful to add; otherwise pass. "
        "Do not speak on behalf of other participants or invent their agreement. "
        "Only visible messages or delivered receipts establish that anyone saw an earlier reply. "
        "Prior ACP responses may be private drafts. not_delivered means nobody saw that draft; "
        "uncertain or pending means delivery is not established. An omitted receipt establishes nothing. "
        "Reconsider useful points against the current conversation; don't blindly repost or repeat tool work. "
        "Separate proposed work, performed work, and independently checked results. "
        f"Keep a spoken contribution under {step.get('max_words', 300)} words when practical. "
        "Your final response must be JSON with action 'speak' and text, or action 'pass' and optional reason. "
        "Code can be included in text using fenced blocks. Intermediate ACP output remains private. "
        + instructions(data.get("attention_condition", {})) + "\n\n"
        + json.dumps(data, ensure_ascii=False)
    )


def decision(text):
    cleaned = text.strip()
    preamble_characters = 0
    if cleaned.startswith("```json") and cleaned.endswith("```"):
        cleaned = cleaned[7:-3].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        # ACP text may contain progress updates followed by the requested final
        # JSON envelope. Only a complete terminal envelope establishes what the
        # agent wants published; retain progress in private raw output evidence.
        value = None
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character != "{" or (index and cleaned[index - 1] not in "\r\n \t"):
                continue
            try:
                candidate, end = decoder.raw_decode(cleaned, index)
            except json.JSONDecodeError:
                continue
            suffix = cleaned[end:].strip()
            if isinstance(candidate, dict) and candidate.get("action") in ("speak", "pass") and suffix in ("", "```"):
                value = candidate
                preamble_characters = index
                break
        # Plain natural-language ACP agents can still use this experience.
        # Malformed attempted JSON is kept private for an operator to inspect.
        if value is None:
            if cleaned.startswith(("{", "[")) or ('"action"' in cleaned and "{" in cleaned):
                return {"action": "invalid", "reason": "Malformed response envelope"}
            return {"action": "speak" if cleaned else "pass", "text": cleaned, "format": "plain_text"}
    if not isinstance(value, dict) or value.get("action") not in ("speak", "pass"):
        return {"action": "invalid", "reason": "Unknown response action"}
    if value["action"] == "speak" and (not isinstance(value.get("text"), str) or not value["text"].strip()):
        return {"action": "invalid", "reason": "Missing speech text"}
    return {"action": value["action"], "text": value.get("text", ""), "reason": str(value.get("reason", ""))[:2000],
            "format": "json_with_progress" if preamble_characters else "json", "private_progress_characters": preamble_characters}


class Engine:
    def __init__(self, run):
        self.run = run
        self.scenario = validate(read(run.path / "scenario.json"))
        self.bindings = validate_bindings(read(run.path / "bindings.json"), self.scenario)
        if digest(self.scenario) != run.data["scenario_sha256"] or digest(self.bindings) != run.data["bindings_sha256"]:
            raise ValueError("Scenario or endpoint bindings changed; create a new run for a new condition")
        self.clients = {}
        self.started = time.monotonic()

    async def client(self, participant, room):
        key = participant + ":" + room
        if key in self.clients:
            return self.clients[key]
        endpoint = self.bindings["participants"][participant]
        observe = lambda kind, **values: self.run.event(kind, participant=participant, room=room, **values)
        client = Client(endpoint, observe)
        self.clients[key] = client
        await client.start()
        session = await client.open_session(self.run.data["sessions"].get(key))
        self.run.data["sessions"][key] = session
        self.run.save()
        return client

    async def turn(self, step, participant, index, interruption, context):
        existing = next((turn for turn in self.run.data["turns"] if turn["step"] == index and turn["participant"] == participant), None)
        if existing:
            return existing
        turn = {"id": str(uuid.uuid4()), "step": index, "room": step["room"],
                "participant": participant, "started_at": now(), "state": "connecting",
                "delivery": "pending", "baseline_seq": context["public_seq"]}
        self.run.data["turns"].append(turn)
        self.run.save()
        began, first_chunk = time.monotonic(), False
        try:
            client = await self.client(participant, step["room"])
            if participant in step.get("private_context", {}):
                context = {**context, "your_private_role_context": step["private_context"][participant]}
            text = prompt(step, context)
            # Save the exact supplied prompt before any write to the endpoint.
            turn["input"] = self.run.evidence(turn["id"] + "-input.json", {"prompt": text})
            turn.update(state="in_flight", session_id=client.session)
            self.run.event("prompt_started", turn_id=turn["id"], participant=participant, room=step["room"])

            async def chunk(_):
                nonlocal first_chunk
                if first_chunk:
                    return
                first_chunk = True
                turn["first_chunk_ms"] = round((time.monotonic() - began) * 1000)
                self.run.event("first_chunk", turn_id=turn["id"])
                if interruption and participant == interruption["participant"]:
                    marker = f"intervention:{index}"
                    if not any(message.get("intervention_id") == marker for message in self.run.data["messages"]):
                        publish(self.run, step["room"], "operator", "operator_cue", interruption["text"], intervention_id=marker, step=index)
                        self.run.event("intervention_triggered", step=index, turn_id=turn["id"], trigger="first_chunk")
                        await client.cancel()
                        turn["cancel_requested"] = True
                        self.run.event("cancel_requested", turn_id=turn["id"])

            result = await client.prompt(text, self.scenario["limits"]["turn_seconds"], chunk)
            turn.update(state="finished", stop_reason=result["stop_reason"], decision=decision(result["text"]),
                        output=self.run.evidence(turn["id"] + "-output.json", result),
                        elapsed_ms=round((time.monotonic() - began) * 1000), finished_at=now())
            self.run.event("prompt_finished", turn_id=turn["id"], stop_reason=result["stop_reason"])
        except Exception as exc:
            # A timeout, dropped process, or malformed result may follow tool
            # execution. It is not safe to quietly replay this prompt.
            was_sent = turn["state"] == "in_flight"
            turn.update(state="unknown" if was_sent else "connection_error", delivery="uncertain" if was_sent else "not_delivered",
                        error_type=type(exc).__name__, reason="Execution outcome needs inspection" if was_sent else "Connection failed before prompt", elapsed_ms=round((time.monotonic() - began) * 1000))
            self.run.event("prompt_uncertain" if was_sent else "connection_error", turn_id=turn["id"], error_type=type(exc).__name__)
        return turn

    async def round(self, step, index):
        room = step["room"]
        active = step.get("participants", self.run.data["members"][room])
        remaining = [participant for participant in active if not any(turn["step"] == index and turn["participant"] == participant for turn in self.run.data["turns"])]
        calls = len(self.run.data["turns"]) + sum(bool(t.get("publication_check")) for t in self.run.data["turns"])
        if calls + len(remaining) > self.scenario["limits"]["max_turns"]:
            self.run.data.update(status="limited", stop_reason="turn_limit")
            self.run.save()
            return False
        scheduling = self.scenario.get("attention", {}).get("scheduling", "simultaneous")
        if scheduling == "staggered":
            # The declared participant order is visible experiment configuration.
            # Each decision is delivered before the next opportunity; private
            # drafts, pass reasons, and evaluator labels never go to peers.
            for participant in active:
                context = projection(self.run, self.scenario, room, participant)
                turn = await self.turn(step, participant, index, step.get("interrupt"), context)
                if not self.deliver([turn], room):
                    return False
            return True
        # Simultaneous agents see the same published baseline, never peer drafts.
        contexts = {participant: projection(self.run, self.scenario, room, participant) for participant in active}
        turns = await asyncio.gather(*(self.turn(step, participant, index, step.get("interrupt"), contexts[participant]) for participant in active))
        shuffled = turns[:]
        random.Random(self.scenario["seed"] + index).shuffle(shuffled)
        if scheduling == "recheck":
            for turn in shuffled:
                newer = [m for m in room_messages(self.run.data, room) if m["seq"] > turn["baseline_seq"]]
                eligible = (turn["delivery"] == "pending" and turn["state"] == "finished"
                            and turn.get("stop_reason") == "end_turn"
                            and turn.get("decision", {}).get("action") == "speak"
                            and not turn.get("cancel_requested")
                            and not any(m["kind"] == "operator_cue" for m in newer))
                if eligible and newer and not turn.get("publication_check"):
                    if not await self.recheck(step, turn):
                        return False
                if not self.deliver([turn], room):
                    return False
            return True
        return self.deliver(shuffled, room)

    async def recheck(self, step, turn):
        """The same individual reconsiders its own private draft, with public updates.

        Record the extra model call separately from the participation opportunity.
        Never suppress speech to manufacture a pass or replay an uncertain call.
        """
        calls = len(self.run.data["turns"]) + sum(bool(t.get("publication_check")) for t in self.run.data["turns"])
        if calls >= self.scenario["limits"]["max_turns"]:
            self.run.data.update(status="limited", stop_reason="publication_check_turn_limit")
            self.run.save()
            return False
        context = projection(self.run, self.scenario, turn["room"], turn["participant"])
        context["publication_review"] = {
            "instruction": "Your earlier draft has NOT been delivered. The public conversation advanced. Decide again whether to speak, revise, or pass. Do not repeat tool work. A direct request or a new material blocker may still require a response.",
            "your_private_draft": turn["decision"],
        }
        if turn["participant"] in step.get("private_context", {}):
            context["your_private_role_context"] = step["private_context"][turn["participant"]]
        check = {"state": "connecting", "started_at": now(), "public_seq": len(self.run.data["messages"]),
                 "original_decision": turn["decision"]}
        turn["publication_check"] = check
        # Parent state participates in existing crash recovery and resolve flow.
        turn["state"] = "connecting"
        self.run.save()
        began = time.monotonic()
        try:
            client = await self.client(turn["participant"], turn["room"])
            text = prompt(step, context)
            check["input"] = self.run.evidence(turn["id"] + "-publication-input.json", {"prompt": text})
            check["state"] = turn["state"] = "in_flight"
            self.run.event("publication_check_started", turn_id=turn["id"], public_seq=check["public_seq"])
            result = await client.prompt(text, self.scenario["limits"]["turn_seconds"], lambda _: asyncio.sleep(0))
            check.update(state="finished", decision=decision(result["text"]), stop_reason=result["stop_reason"],
                         output=self.run.evidence(turn["id"] + "-publication-output.json", result),
                         elapsed_ms=round((time.monotonic() - began) * 1000), finished_at=now())
            turn.update(state="finished", decision=check["decision"], stop_reason=check["stop_reason"])
            self.run.event("publication_check_finished", turn_id=turn["id"], decision=check["decision"]["action"])
            return True
        except Exception as exc:
            sent = check["state"] == "in_flight"
            check.update(state="unknown" if sent else "connection_error", error_type=type(exc).__name__)
            turn.update(state=check["state"], delivery="uncertain" if sent else "not_delivered",
                        reason="Publication decision requires inspection")
            self.run.data.update(status="needs_resolution", stop_reason="publication_check_failed")
            self.run.save()
            return False

    def deliver(self, turns, room):
        if any(turn["state"] in ("unknown", "in_flight", "connecting", "connection_error") for turn in turns):
            self.run.data.update(status="needs_resolution", stop_reason="ambiguous_or_failed_turn")
            self.run.save()
            return False
        for turn in turns:
            if turn["delivery"] != "pending":
                continue
            changed = any(message["room"] == room and message["seq"] > turn["baseline_seq"] and message["kind"] == "operator_cue" for message in self.run.data["messages"])
            response = turn["decision"]
            if changed or turn.get("cancel_requested") or turn["stop_reason"] == "cancelled":
                turn.update(delivery="not_delivered", reason="Superseded by an intervention" if changed else "Cancelled draft")
            elif turn["stop_reason"] != "end_turn":
                turn.update(delivery="not_delivered", reason="ACP turn did not end normally")
            elif response["action"] == "speak":
                # Message and receipt are one atomic checkpoint; a crash cannot
                # create a published message with a retryable missing receipt.
                message = {"id": str(uuid.uuid4()), "seq": len(self.run.data["messages"]) + 1,
                           "at": now(), "room": room, "speaker": turn["participant"],
                           "kind": self.scenario["participants"][turn["participant"]]["kind"],
                           "text": response["text"], "turn_id": turn["id"]}
                self.run.data["messages"].append(message)
                turn.update(delivery="delivered", message_id=message["id"])
            elif response["action"] == "pass":
                turn.update(delivery="no_response", reason=response.get("reason"))
            else:
                turn.update(delivery="not_delivered", reason=response["reason"])
            self.run.event("delivery_recorded", turn_id=turn["id"], delivery=turn["delivery"], message_id=turn.get("message_id"))
        return True

    async def execute(self, max_steps=None):
        for turn in self.run.data["turns"]:
            if turn["state"] in ("in_flight", "connecting"):
                turn.update(state="unknown", delivery="uncertain", reason="Runner stopped before the outcome was recorded")
        if any(turn["state"] in ("unknown", "connection_error") for turn in self.run.data["turns"]):
            self.run.data["status"] = "needs_resolution"
            self.run.save()
            return
        if self.run.data["status"] == "completed":
            return
        self.run.event("driver_started", driver=driver_identity())
        self.run.data.update(status="running", last_started_at=now())
        self.run.save()
        completed = 0
        try:
            while self.run.data["cursor"] < len(self.scenario["steps"]):
                if max_steps is not None and completed >= max_steps:
                    self.run.data.update(status="paused", stop_reason="step_limit")
                    break
                if time.monotonic() - self.started + self.run.data.get("elapsed_seconds", 0) >= self.scenario["limits"]["max_seconds"]:
                    self.run.data.update(status="limited", stop_reason="time_limit")
                    break
                index = self.run.data["cursor"]
                step = self.scenario["steps"][index]
                action, room = step["action"], step["room"]
                if action == "cue":
                    if not any(message.get("step") == index for message in self.run.data["messages"]):
                        publish(self.run, room, "operator", "operator_cue", step["text"], step=index)
                elif action == "message":
                    if not any(message.get("step") == index for message in self.run.data["messages"]):
                        publish(self.run, room, step["speaker"], "scripted_context", step["text"], step=index,
                                provenance=step["provenance"], simulated_speaker_kind=self.scenario["participants"][step["speaker"]]["kind"])
                elif action in ("join", "leave"):
                    who = step["participant"]
                    members = self.run.data["members"][room]
                    if action == "join" and who not in members:
                        members.append(who)
                    elif action == "leave" and who in members:
                        members.remove(who)
                    if not any(message.get("step") == index for message in self.run.data["messages"]):
                        publish(self.run, room, "operator", "membership", f"{who} {'joined' if action == 'join' else 'left'} this room.", step=index)
                    self.run.event("membership_changed", room=room, participant=who, action=action)
                else:
                    remaining = self.scenario["limits"]["max_seconds"] - self.run.data.get("elapsed_seconds", 0) - (time.monotonic() - self.started)
                    try:
                        if not await asyncio.wait_for(self.round(step, index), max(remaining, 0.001)):
                            break
                    except asyncio.TimeoutError:
                        for turn in self.run.data["turns"]:
                            if turn["state"] in ("connecting", "in_flight"):
                                turn.update(state="unknown", delivery="uncertain", reason="Overall observation limit reached during the turn")
                        self.run.data.update(status="needs_resolution", stop_reason="time_limit_during_turn")
                        self.run.event("observation_limit_reached", runtime_stop_confirmed=False)
                        break
                self.run.data["cursor"] += 1
                self.run.save()
                completed += 1
            else:
                self.run.data.update(status="completed", finished_at=now(), stop_reason="scenario_steps_finished")
        finally:
            self.run.data["elapsed_seconds"] = round(self.run.data.get("elapsed_seconds", 0) + time.monotonic() - self.started, 3)
            self.run.save()
            await asyncio.gather(*(client.close() for client in self.clients.values()))


def resolve(run, turn_id, reason):
    turn = next((turn for turn in run.data["turns"] if turn["id"] == turn_id), None)
    if not turn or turn["state"] not in ("unknown", "in_flight", "connecting", "connection_error"):
        raise ValueError("Only uncertain or failed turns need resolution")
    if not reason.strip():
        raise ValueError("Record what was inspected and why it is safe to continue")
    turn.update(state="abandoned", delivery="uncertain" if turn["delivery"] != "not_delivered" else "not_delivered", reason=reason)
    run.event("operator_resolution", turn_id=turn_id, resolution="skip_without_replay", reason=reason)
