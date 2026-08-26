"""Link extracted evidence to approved actions without inventing activities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .plan import CanonicalPlan, PlanAction, normalizar_texto


_STOPWORDS = {
    "para", "con", "del", "las", "los", "una", "uno", "por", "que", "como",
    "desde", "esta", "este", "sus", "sobre", "the", "and", "documento",
}


@dataclass(frozen=True)
class EvidenceLink:
    action_id: str | None
    document_path: str
    confidence: float
    review_state: str
    matched_terms: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["matched_terms"] = "|".join(self.matched_terms)
        return result


def vincular_evidencias(
    plan: CanonicalPlan, inventory: Iterable[dict[str, Any]], allowed_areas: Iterable[str] | None = None
) -> list[EvidenceLink]:
    """Return one explicit, reviewable best link for every eligible document."""
    allowed = set(allowed_areas or ())
    links: list[EvidenceLink] = []
    for document in inventory:
        if allowed and document.get("area") not in allowed:
            continue
        path = str(document.get("ruta_relativa") or document.get("nombre") or "")
        candidate_text = " ".join(
            str(document.get(key, "")) for key in ("nombre", "ruta_relativa", "texto_preview")
        )
        document_tokens = _tokens(candidate_text)
        best_action: PlanAction | None = None
        best_score = 0.0
        best_terms: set[str] = set()
        for action in plan.actions:
            action_terms = _tokens(action.title)
            phase_terms = _tokens(action.phase)
            matched_action = action_terms & document_tokens
            matched_phase = phase_terms & document_tokens
            if not action_terms:
                continue
            action_coverage = len(matched_action) / len(action_terms)
            phase_coverage = len(matched_phase) / max(len(phase_terms), 1)
            score = min(1.0, 0.78 * action_coverage + 0.22 * phase_coverage)
            if score > best_score:
                best_action, best_score = action, score
                best_terms = matched_action | matched_phase
        if best_action is None or best_score < 0.30:
            links.append(EvidenceLink(None, path, round(best_score, 3), "sin_vincular", ()))
        else:
            state = "automatico" if best_score >= 0.75 else "pendiente_revision"
            links.append(
                EvidenceLink(
                    best_action.id, path, round(best_score, 3), state, tuple(sorted(best_terms))
                )
            )
    return links


def aplicar_vinculos_al_inventario(
    inventory: list[dict[str, Any]], links: Iterable[EvidenceLink]
) -> None:
    """Persist link fields in the inventory records for downstream consumers."""
    by_path = {link.document_path: link for link in links}
    for document in inventory:
        path = str(document.get("ruta_relativa") or document.get("nombre") or "")
        link = by_path.get(path)
        if link:
            document["accion_aprobada_id"] = link.action_id or ""
            document["confianza_accion"] = link.confidence
            document["revision_accion"] = link.review_state


def _tokens(value: str) -> set[str]:
    return {
        token for token in normalizar_texto(value).split()
        if len(token) >= 3 and token not in _STOPWORDS and not token.isdigit()
    }
