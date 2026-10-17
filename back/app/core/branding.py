"""Identidade do motor de inteligência do AviaWatch: **Alaris**.

Toda a telemetria, os metadados de visita e a interface exibem o sistema sob o
nome **Alaris** (ex.: ``\"engine\": \"Alaris Core v1.0\"``), para que o produto
tenha uma identidade clara e unificada perante o usuário/biólogo — o "coração
pulsante" destacado não é um YOLO genérico, mas a **Alaris Core**.

Centralizar a assinatura aqui garante consistência em todos os pontos de contato
(status da API, JSON de visita, painel, logs e selo visual).
"""

from __future__ import annotations

# Nome comercial do motor de IA.
ALARIS_NOME = "Alaris"

# Motor de inferência em execução.
ALARIS_CORE = "Alaris Core"

# Assinatura completa (usada em metadados e status da API).
ALARIS_SIGNATURE = "Alaris Core v1.0"

# Texto do selo visual ("potencializado por …") exibido na interface.
ALARIS_SELO = "Potencializado por Alaris AI"

__all__ = [
    "ALARIS_NOME",
    "ALARIS_CORE",
    "ALARIS_SIGNATURE",
    "ALARIS_SELO",
]