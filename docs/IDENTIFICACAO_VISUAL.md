# Pacote de Identificação Visual do Bem-Te-Vi Core

**Escopo:** Backend (FastAPI + YOLOv8 + OpenCV + SQLite) e Frontend
(React + Vite + Tailwind).
**Data:** 2026-10-21.

Este documento descreve o pacote de refatoração visual e funcional do
**Bem-Te-Vi Monitor** (aplicação) e do **Bem-Te-Vi Core** (motor de IA), que
automatiza a identificação de visitantes e eleva o design system do
Bem-Te-Vi. Todo o código foi escrito e documentado em **português do Brasil**.

---

## 1. Visão geral

| Módulo | Entrega | Onde vive |
| --- | --- | --- |
| 1. Auto-associação de espécie | Re-ID visual contra o Catálogo Local (limiar 65%) | `back/app/ai/species_association.py` |
| 1. Curadoria / retreinamento | Botão "Associação Incorreta / Reclassificar" + pasta `data/fine_tuning/` | `back/app/ai/fine_tuning.py`, `front/src/components/gallery/ReclassifySpeciesModal.tsx` |
| 2. Download do recorte HD | "Baixar Recorte HD (Crop)" na Galeria e no deep-dive | `back/app/services/hd_crop.py`, `back/app/controllers/visits.py` |
| 3. Bounding box & rótulos | Cantos arredondados, borda 2 px translúcida, selo dark mode dinâmico | `back/app/infra/ai/annotate.py` |
| 4. Limpeza do status | Selos "Identificado pelo Bem-Te-Vi Core" / "Espécie Confirmada" | `front/src/utils/visits.ts`, `front/src/components/**` |

> **Nota de arquitetura:** o pedido original citava
> `app/services/detection_service.py` e `app/utils/drawing.py`. Esses
> arquivos **não existem** nesta base: o fluxo de detecção mora em
> `back/app/infra/ai/pipeline.py` e a renderização em
> `back/app/infra/ai/annotate.py`. A implementação foi feita nos módulos reais
> (sem criar atalhos paralelos), preservando a separação de camadas do projeto.

---

## 2. Auto-associação de espécie (Re-ID visual)

### 2.1 Como funciona

1. O YOLOv8 detecta a ave e o classificador devolve apenas o rótulo genérico
   (`bird`). A visita nasce com esse rótulo.
2. `SpeciesAssociationService.associate_visit()` lê o **recorte tratado** da
   captura e extrai o embedding (MobileNetV3-Small, 576 dims; fallback OpenCV,
   180 dims).
3. O vetor normalizado (L2) é comparado por **similaridade de cosseno**
   (produto escalar) com o embedding de cada `bird_species.reference_image_path`.
4. Se o melhor escore ≥ `species_match_threshold` (**0.65 = 65%**), a visita
   recebe o nome popular da espécie, o vínculo com o catálogo e o selo
   `Identificado pelo Bem-Te-Vi Core`.

O ganho de performance vem do **cache de referências**: as fotos do catálogo
são lidas uma única vez e mantidas em memória. O cache é invalidado
automaticamente pela assinatura `(id, caminho, mtime)` — trocar a foto de
referência de uma espécie já força o recálculo, sem reiniciar a API.

### 2.2 Regras de segurança (curadoria humana sempre vence)

* Visitas com `identification_status` em `Espécie Confirmada`,
  `Reclassificado pelo usuário`, `Identificado por IA Externa` ou
  `Visitante Especial` **nunca** são sobrescritas.
* Visitas que já possuem `species_id` ou espécie real **não** são reescritas.
* Falhas (sem torch, sem catálogo, imagem ilegível, baixa nitidez) degradam
  para “sem associação” — a captura nunca é interrompida.

### 2.3 Configuração

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `SPECIES_AUTO_ASSOCIATION_ENABLED` | `true` | Liga/desliga a auto-associação |
| `SPECIES_MATCH_THRESHOLD` | `0.65` | Similaridade mínima (65%) |
| `SPECIES_MATCH_MIN_SHARPNESS` | `15` | Nitidez mínima do recorte (Laplaciano) |
| `SPECIES_MATCH_MAX_REFERENCES` | `500` | Teto de fotos de referência avaliadas |
| `HD_CROP_MIN_SIDE` | `1080` | Menor lado do recorte HD exportado |
| `HD_CROP_JPEG_QUALITY` | `94` | Qualidade do JPEG HD |

> `get_settings()` é cacheado (`lru_cache`): mudanças no `.env` exigem
> **reinício do backend**.

### 2.4 Endpoints

| Método | Rota | Função |
| --- | --- | --- |
| `POST` | `/api/visits/{id}/auto-identify` | Reexecuta a associação sob demanda |
| `POST` | `/api/visits/{id}/reclassify` | Correção humana + amostra de retreinamento |
| `PUT` | `/api/visits/{id}/assign-species` | Associação direta (dropdown da Galeria) |
| `POST` | `/api/visits/{id}/confirm` | Confirmação do observador |
| `GET` | `/api/visits/{id}/crop/hd` | Download do recorte em alta resolução |

---

## 3. Curadoria e retreinamento (`data/fine_tuning/`)

O botão **“Associação Incorreta / Reclassificar”** abre um modal com o
Catálogo Local (busca por nome popular/científico, foto de referência e marca
de “Atual”). Ao salvar:

1. a visita passa a exibir a espécie correta (`species` + `species_id`);
2. o recorte tratado é gravado em
   `app-data/fine_tuning/{espécie}/{visit_id}.jpg`;
3. a proveniência é registrada em `app-data/fine_tuning/index.jsonl`
   (visita, espécie, origem, observação, confiança e data);
4. a fila operacional de aprendizado (`app-data/training_queue/`) e a
   assinatura visual do indivíduo são atualizadas em segundo plano.

Reclassificar a mesma visita **move** a amostra (o arquivo anterior é
removido), evitando que o mesmo recorte ensine duas classes contraditórias.

A pasta `fine_tuning` é deliberadamente separada da fila do fine-tuning
automático: ela é o material de **auditoria e retreinamento manual**
(inspeção, exportação, versionamento), enquanto `training_queue` alimenta o
botão “Otimizar Bem-Te-Vi Core com Novas Amostras”.

---

## 4. Recorte HD (download)

`GET /api/visits/{id}/crop/hd` gera (uma única vez) um JPEG otimizado em
`app-data/crops/{id}_hd.jpg`:

* reescala Lanczos até o menor lado configurado (1080 px por padrão, com teto
  de 4× o tamanho original para não inventar pixels demais);
* aplica *unsharp mask* discreto e CLAHE leve na luminância;
* é devolvido como **anexo** (`Content-Disposition: attachment`) com nome
  amigável: `alaris-core-{espécie}-{id8}-hd.jpg`.

Na interface, o botão **“Baixar Recorte HD (Crop)”** aparece em cada card da
Galeria e no modal de *deep-dive* das Últimas Visitas do Painel, ao lado das
ações já existentes de clipe e Reel.

---

## 5. Bounding box e rótulos (stream da câmera)

`back/app/infra/ai/annotate.py` foi redesenhado:

* **Cantos arredondados** (raio 10 px) e **borda de 2 px semi-transparente**
  (mistura alfa restrita à região do desenho — o quadro inteiro nunca é
  copiado, preservando o FPS do stream);
* **Cores por status**:
  * **Ciano** (`#22D3EE`) — ave confirmada (espécie real);
  * **Âmbar** (`#F59E0B`) — pré-associação (ainda sem espécie);
  * **Rosa** (`#F472B6`) — fauna não-ave (Visitante Especial);
  * **Azul Prussiano** (`#123B6B`) — apoio cromático do selo dark mode;
* **Rótulo dinâmico** no estilo dark mode (`slate-900` a 90%):
  * ave identificada → `Cardeal-do-norte • 88%`;
  * pré-associação → `Aguardando ID` (a antiga legenda “pássaro 25%” foi
    removida — a confiança do *detector* não é confiança de *espécie*).

Detalhe técnico: as fontes do OpenCV não renderizam Unicode. O “•” é
desenhado como um círculo (`cv2.circle`) e o “✨” da marca como um losango
(`_draw_sparkle`).

---

## 6. Limpeza do status “Desconhecido” no Painel

* A tag estática “⚪ Status desconhecido” (status ecológico inconclusivo) não
  é mais exibida quando a ave já tem identificação — o painel passa a exibir o
  selo elegante correspondente:
  * **Identificado pelo Bem-Te-Vi Core** (auto-associação por re-ID visual);
  * **Espécie Confirmada** (confirmação, reclassificação ou IA externa).
* `resolveEcological()` agora dá prioridade ao status do Catálogo Local quando
  o status gravado na captura é “desconhecida”.
* O rótulo curto genérico dos selos compactos mudou de “Desconhecido” para
  **“Identificando”** (o Bem-Te-Vi Core está resolvendo, não “falhando”).

---

## 7. Vocabulário compartilhado

O conjunto de rótulos genéricos (“bird”, “pássaro desconhecido”, “ave
genérica”…) existia duplicado em três módulos. Agora há uma fonte única em
`back/app/domain/species_labels.py`:

```python
from app.domain.species_labels import is_generic_species, normalize_species_label
```

A normalização remove acentos, colapsa espaços e aplica minúsculas — assim
`"Pássaro Desconhecido"`, `"passaro desconhecido"` e `"PASSARO  DESCONHECIDO"`
caem na mesma chave.

---

## 8. Testes

`back/tests/test_species_association.py` cobre os quatro pilares com um
extrator de embeddings falso (determinístico, sem torch):

1. auto-associação aceita acima do limiar e persiste o nome + metadados;
2. auto-associação **não** sobrescreve curadoria humana;
3. reclassificação grava a amostra em `fine_tuning/` e move o arquivo quando a
   espécie muda;
4. exportação HD gera JPEG ampliado em `app-data/crops/`;
5. renderização usa ciano para ave confirmada e âmbar para pré-associação.

```bash
cd back
venv\Scripts\python.exe -m pytest tests -q
cd front
npm run build   # tsc --noEmit + vite build
```
