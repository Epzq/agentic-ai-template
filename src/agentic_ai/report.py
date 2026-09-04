from __future__ import annotations

from pydantic import BaseModel, Field

# The structured output of the grant-fit analyst. `create_react_agent(..., response_format=
# GrantFitReport)` fills this in with a final model call, so every run returns the same shape.


class CompetitorTake(BaseModel):
    group: str = Field(description="Lab or research group name")
    institution: str
    their_strengths: str
    vs_pi: str = Field(description="Where the PI is stronger, and where weaker, than this group")
    attack: str = Field(description="Angle the PI should lean into against this competitor")
    avoid: str = Field(description="Where the PI should not compete head-on")


class GrantFitReport(BaseModel):
    pi: str = Field(description="Principal investigator name")
    grant_call: str = Field(
        description="Target grant call - the one given, or the best-fit one found"
    )
    pi_strengths_and_track_record: str
    grant_to_pi_match_pct: int = Field(ge=0, le=100, description="Estimated alignment, 0-100")
    match_rationale: str = Field(description="Why that percentage - concrete evidence")
    proposed_direction: str = Field(description="One specific, fundable research direction")
    competitors: list[CompetitorTake]
    relevant_past_grants: list[str] = Field(
        description="Awarded grants relevant to the proposed direction, with links where available"
    )
