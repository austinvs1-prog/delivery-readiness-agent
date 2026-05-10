from app.schemas import SharedContext
from app.observability import log_event


class ContextBudgetManager:
    def __init__(self, default_budget: int = 1800, safety_margin: int = 120):
        self.default_budget = default_budget
        self.safety_margin = safety_margin

    @staticmethod
    def estimate_tokens(value: object) -> int:
        return max(1, int(len(str(value).split()) * 1.3))

    def used_tokens(self, context: SharedContext) -> int:
        return self.estimate_tokens(context.model_dump())

    def remaining_tokens(self, context: SharedContext, max_budget: int) -> int:
        return max_budget - self.used_tokens(context)

    def ensure_budget(self, context: SharedContext, agent_id: str, max_budget: int) -> SharedContext:
        used = self.used_tokens(context)
        if used <= max_budget - self.safety_margin:
            return context

        original_history = list(context.conversational_history)
        context.conversational_history = [
            "Older conversational filler compressed; structured memory, tool outputs, citations, and scores preserved losslessly."
        ]
        log_event(
            context.job_id,
            "compression_agent",
            "compression_triggered",
            payload={
                "triggered_for": agent_id,
                "used_before": used,
                "history_items_before": len(original_history),
                "structured_data_preserved": True,
            },
            token_count=self.used_tokens(context),
        )

        after = self.used_tokens(context)
        if after > max_budget:
            violation = f"context_overflow:{agent_id}:{after}>{max_budget}"
            context.policy_violations.append(violation)
            log_event(
                context.job_id,
                agent_id,
                "policy_violation",
                payload={"used_tokens": after, "max_budget": max_budget},
                token_count=after,
                policy_violation=violation,
            )
        return context
