"""Módulos de inteligência adaptativa do Bem-Te-Vi Core.

- :mod:`app.ai.active_learning` — fila de amostras e fine-tuning incremental.
- :mod:`app.ai.behavioral_memory` — memória comportamental e previsão de picos.
- :mod:`app.ai.visual_embeddings` — assinaturas visuais e reidentificação
  individual ("Conhecido do Jardim").
"""

from __future__ import annotations

__all__ = ["active_learning", "behavioral_memory", "visual_embeddings"]
