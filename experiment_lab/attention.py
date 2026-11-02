"""Explicit client-side participation conditions; never a peer coordinator.

These instructions influence agent decisions. They do not filter completed
speech, choose a winner, confer permissions, or replace runtime scheduling.
"""
import copy


def validate_attention(value):
    if not isinstance(value, dict):
        raise ValueError("Attention condition must be an object")
    result = copy.deepcopy(value)
    allowed = {"policy", "scheduling", "ambient_threshold", "duplicate_window", "direct_reply"}
    if set(result) - allowed:
        raise ValueError("Unknown attention option")
    result.setdefault("policy", "baseline")
    result.setdefault("scheduling", "simultaneous")
    result.setdefault("ambient_threshold", "material")
    result.setdefault("duplicate_window", 8)
    result.setdefault("direct_reply", True)
    if result["policy"] not in ("baseline", "selective"):
        raise ValueError("Attention policy must be baseline or selective")
    if result["scheduling"] not in ("simultaneous", "staggered", "recheck"):
        raise ValueError("Scheduling must be simultaneous, staggered, or recheck")
    if result["ambient_threshold"] not in ("relevant", "material"):
        raise ValueError("Ambient threshold must be relevant or material")
    if type(result["duplicate_window"]) is not int or not 1 <= result["duplicate_window"] <= 100:
        raise ValueError("Duplicate window must be 1–100 visible messages")
    if type(result["direct_reply"]) is not bool:
        raise ValueError("Direct reply must be boolean")
    return result


def instructions(condition):
    if condition.get("policy", "baseline") == "baseline":
        return ""
    direct = (
        "In a direct conversation reply to the person's new message, including a brief acknowledgement when appropriate, unless they explicitly requested silence. "
        if condition["direct_reply"] else ""
    )
    threshold = (
        "An ambient contribution should change a decision, unblock accepted work, correct a consequential error, or raise a concrete material risk. "
        if condition["ambient_threshold"] == "material" else
        "An ambient contribution should add relevant information not already covered. "
    )
    return (
        "This experience explicitly enables selective participation; every invited participant still gets an opportunity. "
        + direct +
        "In a group, answer a new direct question or mention addressed to you; acknowledge an ownership offer to you and either accept its stated scope or explain a blocker. "
        "An open question invites a useful answer, but does not require everybody to answer. "
        + threshold +
        f"Check the last {condition['duplicate_window']} visible messages for coverage before speaking. "
        "If a peer has already answered adequately, pass instead of repeating, endorsing, summarizing, or announcing that you are waiting. "
        "Do not take over a task accepted by someone else, invent a new assignment, or turn tentative brainstorming into a commitment. "
        "When humans are talking to each other and no useful intervention is needed, pass. "
        "After a pause or interruption, respect the revised request; do not publish superseded work. "
        "Passing is a private decision, not a message saying you will be quiet. "
        "Silence must not hide a request you owe or a concrete blocker only you know. "
        "Include a short reason in the final decision envelope for either speak or pass. "
    )
