"""Central de Regras de Alerta Personalizadas (Smart Alerts).

Avalia regras condicionais configuradas pelo observador antes de disparar
notificações (Telegram/Discord). Cada regra combina condições sobre a visita
(espécie nova, espécie rara, nitidez do frame, confiança, jardim específico)
e decide se a notificação deve ser enviada ou suprimida.

As regras são armazenadas como JSON no `SettingsRepository` sob a chave
``smart_alert_rules`` e podem ser editadas pela aba de Configurações.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.core.config import get_settings
from app.infra.database.repository import SettingsRepository

logger = logging.getLogger(__name__)

# Chave no SettingsRepository onde as regras são persistidas.
_RULES_KEY = "smart_alert_rules"

# Campos que uma condição pode avaliar.
_ALLOWED_FIELDS = {
    "species_is_new",       # bool: espécie não está no catálogo
    "species_is_rare",      # bool: status ecológico contém "rara"
    "sharpness_min",        # float: nitidez mínima do frame
    "confidence_min",       # float: confiança mínima da detecção
    "garden_id",            # str: câmera/jardim específico
    "visitor_kind",         # str: "bird", "mammal", etc.
    "has_individual",       # bool: indivíduo recorrente reconhecido
}

# Operadores suportados.
_ALLOWED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"}


def _default_rules() -> list[dict[str, Any]]:
    """Regras padrão (permissivas): notifica tudo, a menos que configurado."""
    return [
        {
            "id": "default-notify-all",
            "name": "Notificar todas as visitas de aves",
            "enabled": True,
            "conditions": [],
            "description": "Regra padrão: envia notificação para toda visita de ave.",
        }
    ]


def load_rules() -> list[dict[str, Any]]:
    """Carrega as regras do banco (ou retorna as padrão se vazio)."""
    try:
        raw = SettingsRepository(get_settings().db_path).get(_RULES_KEY)
        if not raw:
            return _default_rules()
        rules = json.loads(raw)
        if isinstance(rules, list) and rules:
            return rules
        return _default_rules()
    except (json.JSONDecodeError, Exception):
        logger.debug("Falha ao carregar regras de alerta; usando padrão", exc_info=True)
        return _default_rules()


def save_rules(rules: list[dict[str, Any]]) -> None:
    """Persiste as regras no banco."""
    SettingsRepository(get_settings().db_path).set(_RULES_KEY, json.dumps(rules, ensure_ascii=False))


def _get_field_value(visit: Any, event: dict[str, Any] | None, field: str) -> Any:
    """Extrai o valor de um campo da visita/evento para avaliação."""
    visit_dict = visit if isinstance(visit, dict) else (visit.__dict__ if hasattr(visit, "__dict__") else {})
    event = event or {}

    if field == "species_is_new":
        return bool(event.get("is_new_species", False))
    if field == "species_is_rare":
        status = str(visit_dict.get("ecological_status") or event.get("ecological_status") or "")
        return "rara" in status.casefold()
    if field == "sharpness_min":
        return float(visit_dict.get("sharpness") or visit_dict.get("best_frame_sharpness") or 0.0)
    if field == "confidence_min":
        return float(visit_dict.get("confidence") or 0.0)
    if field == "garden_id":
        return str(visit_dict.get("camera_id") or "")
    if field == "visitor_kind":
        return str(visit_dict.get("visitor_kind") or "bird")
    if field == "has_individual":
        return bool(event.get("individual_id") or visit_dict.get("individual_id"))
    return None


def _evaluate_condition(cond: dict[str, Any], visit: Any, event: dict[str, Any] | None) -> bool:
    """Avalia uma única condição contra a visita/evento."""
    field = cond.get("field")
    operator = cond.get("operator", "eq")
    expected = cond.get("value")

    if field not in _ALLOWED_FIELDS:
        logger.warning("Campo de regra desconhecido: %s", field)
        return True  # Condição desconhecida não bloqueia

    actual = _get_field_value(visit, event, field)

    try:
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "gt":
            return float(actual) > float(expected)
        if operator == "gte":
            return float(actual) >= float(expected)
        if operator == "lt":
            return float(actual) < float(expected)
        if operator == "lte":
            return float(actual) <= float(expected)
        if operator == "contains":
            return str(expected).casefold() in str(actual).casefold()
        if operator == "in":
            if isinstance(expected, list):
                return actual in expected
            return actual in str(expected).split(",")
    except (TypeError, ValueError):
        logger.debug("Falha ao avaliar condição %s %s %s", field, operator, expected, exc_info=True)
        return True

    return True


def evaluate_rules(visit: Any, event: dict[str, Any] | None = None) -> bool:
    """Avalia todas as regras habilitadas. Retorna True se a notificação deve ser enviada.

    Lógica: se NÃO houver regras habilitadas, envia (permissivo). Se houver,
    envia se PELO MENOS UMA regra habilitada for satisfeita (OR). Uma regra é
    satisfeita quando TODAS as suas condições são verdadeiras (AND).
    """
    rules = [r for r in load_rules() if r.get("enabled", True)]
    if not rules:
        return True

    for rule in rules:
        conditions = rule.get("conditions", [])
        if not conditions:
            # Regra sem condições = sempre satisfeita.
            return True
        if all(_evaluate_condition(c, visit, event) for c in conditions):
            return True

    return False


def create_rule(
    name: str,
    conditions: list[dict[str, Any]],
    *,
    enabled: bool = True,
    description: str = "",
) -> dict[str, Any]:
    """Cria uma nova regra e a persiste."""
    rule = {
        "id": str(uuid.uuid4())[:8],
        "name": name.strip() or "Regra sem nome",
        "enabled": enabled,
        "conditions": conditions,
        "description": description.strip(),
    }
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    return rule


def update_rule(rule_id: str, **updates: Any) -> dict[str, Any] | None:
    """Atualiza uma regra existente (name, enabled, conditions, description)."""
    rules = load_rules()
    for rule in rules:
        if rule.get("id") == rule_id:
            for key in ("name", "enabled", "conditions", "description"):
                if key in updates and updates[key] is not None:
                    rule[key] = updates[key]
            save_rules(rules)
            return rule
    return None


def delete_rule(rule_id: str) -> bool:
    """Remove uma regra pelo ID."""
    rules = load_rules()
    filtered = [r for r in rules if r.get("id") != rule_id]
    if len(filtered) == len(rules):
        return False
    save_rules(filtered)
    return True


def toggle_rule(rule_id: str) -> dict[str, Any] | None:
    """Inverte o estado enabled de uma regra."""
    rules = load_rules()
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["enabled"] = not rule.get("enabled", True)
            save_rules(rules)
            return rule
    return None


def get_smart_alerts_service() -> "SmartAlertsService":
    """Compatibilidade com o padrão de singleton do projeto."""
    return SmartAlertsService()


class SmartAlertsService:
    """Wrapper de compatibilidade com o padrão get_*_service()."""

    def evaluate(self, visit: Any, event: dict[str, Any] | None = None) -> bool:
        return evaluate_rules(visit, event)

    def load(self) -> list[dict[str, Any]]:
        return load_rules()

    def save(self, rules: list[dict[str, Any]]) -> None:
        save_rules(rules)

    def create(self, name: str, conditions: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
        return create_rule(name, conditions, **kw)

    def update(self, rule_id: str, **updates: Any) -> dict[str, Any] | None:
        return update_rule(rule_id, **updates)

    def delete(self, rule_id: str) -> bool:
        return delete_rule(rule_id)

    def toggle(self, rule_id: str) -> dict[str, Any] | None:
        return toggle_rule(rule_id)
