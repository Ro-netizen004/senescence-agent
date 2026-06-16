"""Named deterministic workflow graphs (ordered tool steps)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass(frozen=True)
class WorkflowStep:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    stop_on_error: bool = True


@dataclass(frozen=True)
class Workflow:
    id: str
    description: str
    steps: list[WorkflowStep]
    header: str | None = None
    add_panel_summary: bool = False


WORKFLOWS: dict[str, Workflow] = {
    "panel": Workflow(
        id="panel",
        description="Full senescence panel",
        header="Standard senescence analysis panel completed.",
        add_panel_summary=True,
        steps=[
            WorkflowStep("find_senescence_markers"),
            WorkflowStep("senescence_score"),
            WorkflowStep("generate_umap"),
            WorkflowStep("get_cluster_annotations"),
            WorkflowStep("compare_across_age"),
        ],
    ),
    "coverage": Workflow(
        id="coverage",
        description="SenMayo coverage only",
        steps=[WorkflowStep("find_senescence_markers")],
    ),
    "score_and_annotate": Workflow(
        id="score_and_annotate",
        description="Score cells + cluster annotations",
        steps=[
            WorkflowStep("senescence_score"),
            WorkflowStep("get_cluster_annotations"),
        ],
    ),
    "deseq2": Workflow(
        id="deseq2",
        description="DESeq2 pseudobulk DE",
        steps=[WorkflowStep("run_deseq2")],
    ),
    "senescence_test": Workflow(
        id="senescence_test",
        description="Mann-Whitney senescence score test",
        steps=[WorkflowStep("test_senescence_difference")],
    ),
    "umap": Workflow(
        id="umap",
        description="UMAP only",
        steps=[WorkflowStep("generate_umap")],
    ),
    "cluster_annotations": Workflow(
        id="cluster_annotations",
        description="Cluster cell type annotations",
        steps=[WorkflowStep("get_cluster_annotations")],
    ),
}


def run_workflow(
    workflow: Workflow,
    tool_map: dict,
    message: str,
    *,
    execute_tool: Callable,
    collect_plots: Callable,
    deterministic_reply: Callable,
    panel_highlights: Callable | None = None,
    needs_pvalue_clarification: Callable[[str], bool] | None = None,
    arg_overrides: dict[str, dict[str, Any]] | None = None,
    reply_suffix: str | None = None,
) -> dict:
    """Execute a workflow graph sequentially; render via deterministic reply."""
    plots: list = []
    tool_calls_log: list = []

    for step in workflow.steps:
        if step.tool not in tool_map:
            continue

        args = dict(step.args)
        if arg_overrides and step.tool in arg_overrides:
            args.update(arg_overrides[step.tool])

        result = execute_tool(tool_map, step.tool, args, message)

        if step.stop_on_error and isinstance(result, dict) and result.get("error"):
            serializable_result = json.loads(json.dumps(result, default=str))
            tool_calls_log.append({
                "name": step.tool,
                "args": args,
                "result": serializable_result,
            })
            break

        for plot_entry in collect_plots(result, step.tool):
            if not any(p["url"] == plot_entry["url"] for p in plots):
                plots.append(plot_entry)

        serializable_result = json.loads(json.dumps(result, default=str))
        tool_calls_log.append({
            "name": step.tool,
            "args": args,
            "result": serializable_result,
        })

    reply = deterministic_reply(tool_calls_log)

    if workflow.header:
        reply = f"{workflow.header}\n\n{reply}"

    if workflow.add_panel_summary and panel_highlights is not None:
        highlights = panel_highlights(tool_calls_log)
        reply = f"{reply}\n\n---\n\nPanel summary:\n{highlights}"

    if needs_pvalue_clarification and needs_pvalue_clarification(message):
        reply += (
            "\n\n[System] Score p-values require test_senescence_difference; "
            "gene padj requires run_deseq2."
        )

    if reply_suffix:
        reply += f"\n\n{reply_suffix}"

    return {"reply": reply, "plots": plots, "tool_calls": tool_calls_log}
