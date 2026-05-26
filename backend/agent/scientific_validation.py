"""
Backward-compatible entry point — delegates to inference state machine.

User-facing text is produced only by output_renderer (no LLM).
"""

from agent.inference_state import (
    InferenceState,
    InterpretationLevel,
    STATE_CONTRACT,
    apply_inference_state,
    assign_inference_state,
    build_state_record,
)

# Legacy name used by reports
def apply_scientific_validation(tool_name, result, args=None, user_message=None):
    return apply_inference_state(tool_name, result, args)


def format_validation_banner(inference_state_record: dict) -> str:
    """Deprecated: renderer owns banners. Kept for report sanitization."""
    if not inference_state_record:
        return ""
    state = inference_state_record.get("state", "UNKNOWN")
    level = inference_state_record.get("allowed_interpretation_level", "")
    return f"[inference_state={state} | level={level}]"


def wrap_result_for_llm(tool_name: str, result, args=None):
    from agent.output_schema import build_output_schema
    from agent.output_renderer import schema_json_for_llm

    schema = build_output_schema(tool_name, result, args or {})
    return schema_json_for_llm(schema)
