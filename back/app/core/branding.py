"""Identidade oficial do ecossistema **Bem-Te-Vi**.

O produto tem duas faces, com nomes próprios:

* **Bem-Te-Vi Monitor** — a aplicação (interface web/desktop) que o observador
  usa: painel, galeria, diário, configurações;
* **Bem-Te-Vi Core** — o motor de inteligência (backend FastAPI, YOLOv8,
  embeddings, aprendizado ativo) que faz tudo acontecer.

Toda a telemetria, os metadados de visita, a interface, os logs e os selos
visuais exibem o sistema sob esses nomes oficiais — por exemplo
``"engine": "Bem-Te-Vi Core v1.0"`` — para que o produto tenha uma identidade
clara e unificada perante o usuário/biólogo.

Centralizar a assinatura aqui garante consistência em todos os pontos de
contato (status da API, JSON de visita, painel, logs e selo visual).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Nomes oficiais
# --------------------------------------------------------------------------- #

#: Nome comercial da aplicação (interface do Bem-Te-Vi Monitor).
MONITOR_NOME = "Bem-Te-Vi Monitor"

#: Nome comercial do motor de IA (backend + visão computacional).
CORE_NOME = "Bem-Te-Vi Core"

#: Assinatura completa (usada em metadados e status da API).
CORE_SIGNATURE = "Bem-Te-Vi Core v1.0"

#: Texto do selo visual ("powered by …") exibido na interface.
CORE_SELO = "Powered by Bem-Te-Vi Core"

#: Texto de arranque do backend (log de inicialização).
CORE_BOOT = "Bem-Te-Vi Core Backend iniciado com sucesso"

# --------------------------------------------------------------------------- #
# Aliases legados
#
# Mantidos para não quebrar importações existentes no código e em integrações
# externas. New code deve preferir os nomes oficiais acima.
# --------------------------------------------------------------------------- #

ALARIS_NOME = CORE_NOME
ALARIS_CORE = CORE_NOME
ALARIS_SIGNATURE = CORE_SIGNATURE
ALARIS_SELO = CORE_SELO

__all__ = [
    "MONITOR_NOME",
    "CORE_NOME",
    "CORE_SIGNATURE",
    "CORE_SELO",
    "CORE_BOOT",
    "ALARIS_NOME",
    "ALARIS_CORE",
    "ALARIS_SIGNATURE",
    "ALARIS_SELO",
]
