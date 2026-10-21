# Bem-Te-Vi Monitor — Guia Técnico

Aplicação **local** de monitoramento de vida silvestre, operada pelo motor de
IA **Bem-Te-Vi Core**.

> **Sobre o nome:** o projeto nasceu como *AviaWatch* e hoje vive no ecossistema
> **Bem-Te-Vi** — em homenagem ao pássaro que "avisa" quando chega visita ao
> jardim. A **aplicação** (interface web/desktop) chama-se **Bem-Te-Vi Monitor**
> e o **motor de IA** (backend FastAPI, visão computacional e aprendizado)
> assina como **Bem-Te-Vi Core**.

O Bem-Te-Vi Monitor recebe vídeo de câmeras USB, RTSP, ONVIF, HLS, HTTP ou WebRTC —
inclusive streams externos ao vivo (de outras casas/locais remotos) —, detecta
aves com YOLOv8 e registra visitas em SQLite. O painel web permite desenhar zonas
de inclusão e exclusão por câmera, consultar snapshots e clipes e, opcionalmente,
pedir a identificação de uma ave a uma API externa. Alertas pelo Telegram e Discord também
são opcionais. O processamento e os arquivos permanecem locais por padrão.

> **Quer entender como usar sem precisar programar?** Leia o
> [**Guia do Usuário (README.md)**](README.md) — explica todas as funcionalidades
> em linguagem simples, com exemplos do dia a dia.

---

## Requisitos

Instale **antes** de executar o projeto:

| Software | Versão mínima | Download |
|----------|---------------|----------|
| Python | 3.11+ | https://www.python.org/downloads/ |
| Node.js (inclui npm) | 20+ LTS | https://nodejs.org/ |
| Windows | 10/11 | — |

### Dicas na instalação

1. **Python:** na tela inicial do instalador, marque **“Add python.exe to PATH”**.
2. **Node.js:** use o instalador LTS; o `npm` já vem incluído.
3. Abra um **novo** Prompt de Comando ou PowerShell e confira:

```bat
python --version
npm --version
```

> O **FFmpeg é opcional**: se não estiver instalado no sistema, o Bem-Te-Vi usa o
> binário embutido no pacote Python `imageio-ffmpeg`, instalado automaticamente.
> Nenhum outro software precisa ser instalado.

---

## Instalação e execução rápida (Windows) — `start.bat`

O jeito mais simples de subir o Bem-Te-Vi:

### Passo 1 — Abrir a pasta do projeto

No Explorador de Arquivos, vá até a pasta `Bem-Te-Vi` (onde estão `start.bat`, `back\` e `front\`).

### Passo 2 — (Opcional) Configurar integrações

1. Copie `back\.env.example` para `back\.env` (o `start.bat` também faz isso automaticamente se o `.env` não existir).
2. Edite `back\.env` se quiser Telegram/Discord ou identificação por IA externa:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=
# IA Externa: Google Gemini é o ÚNICO provedor suportado.
# Chave gratuita: https://aistudio.google.com
GEMINI_API_KEY=
AI_EXTERNAL_MODEL=gemini-3.5-flash
PORT=8000
```

Deixe os campos vazios para manter Telegram, Discord ou identificação externa
desabilitados. As integrações também podem ser configuradas depois em
**Configurações → Variáveis de ambiente**.

> **Proteja o arquivo:** não compartilhe nem publique `back\.env`. Não cole tokens
> em chamados, capturas de tela ou commits. O arquivo contém segredos e deve ficar
> apenas na máquina que executa o backend.

O backend usa confiança YOLO de `0.22` (alta sensibilidade, ideal para aves
distantes, pequenas, camufladas ou paradas ao pousar), tempo de permanência de
`10` segundos para aves imóveis, sensibilidade de movimento de `0.80`, mantém
pelo menos `3` segundos de pré-gravação e remove clipes, snapshots e recortes
locais com mais de 30 dias. Esses padrões podem ser ajustados no `back\.env`
(`YOLO_CONFIDENCE`, `OBJECT_PERSISTENCE_TIME`, `MOTION_SENSITIVITY`,
`PRESENCE_GRACE_SECONDS`, `ALERT_COOLDOWN_SECONDS`, `PRE_RECORD_SECONDS` e
`MEDIA_RETENTION_DAYS`) ou em tempo real no painel, em
**Configurações → Calibração e Ajustes**. O limite mínimo de confiança é `0.05`
e a retenção deve ser de pelo menos um dia.

### Variáveis disponíveis

O arquivo `back\.env.example` contém os nomes e os valores padrão. Copie-o para
`back\.env` e preencha somente as integrações que pretende usar:

| Variável | Para que serve | Exemplo/observação |
|----------|----------------|-------------------|
| `TELEGRAM_BOT_TOKEN` | Token do bot do Telegram | Obtenha um bot com o BotFather; trate como senha |
| `TELEGRAM_CHAT_ID` | Destino dos alertas no Telegram | ID da conversa, grupo ou canal acessível pelo bot |
| `DISCORD_WEBHOOK_URL` | Envio de alertas ao Discord | URL secreta de um webhook do seu servidor |
| `GEMINI_API_KEY` | Identificação opcional de espécies (Google Gemini) | Chave do Google Gemini — obtenha a sua gratuita em [aistudio.google.com](https://aistudio.google.com). Tem precedência sobre `AI_EXTERNAL_API_KEY` |
| `AI_EXTERNAL_API_KEY` | Legado da chave do Gemini | Mantido por compatibilidade; use `GEMINI_API_KEY` |
| `AI_EXTERNAL_MODEL` | Modelo Gemini com suporte a visão | Padrão: `gemini-3.5-flash`. Testados: `gemini-3.5-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-3.1-pro-preview`. O prefixo `models/` é removido automaticamente (evita HTTP 404) |
| `PORT` | Porta configurada na aplicação | Padrão: `8000`; os comandos de inicialização fornecidos usam a porta `8000` |
| `YOLO_MODEL` | Arquivo/modelo de detecção | Padrão: `yolov8n.pt` |
| `YOLO_CONFIDENCE` | Sensibilidade da detecção (menor = mais sensível) | Padrão: `0.22`; faixa: `0.05` a `1.0` |
| `OBJECT_PERSISTENCE_TIME` | Tempo (s) que o rastreio mantém a visita com a ave imóvel | Padrão: `10.0`; faixa: `0` a `30` |
| `MOTION_SENSITIVITY` | Sensibilidade de detecção de movimento inicial | Padrão: `0.80`; faixa: `0` a `1` |
| `YOLO_BIRD_CLASS_ID` | Classe do COCO usada na inferência | Padrão: `14` (`bird`) |
| `YOLO_ACCELERATION` | Backend de inferência (Edge AI) | `auto` (padrão: TensorRT > ONNX > PyTorch), `engine`/`tensorrt`, `onnx` ou `pt` |
| `YOLO_DEVICE` | Dispositivo de inferência | `auto` (padrão: GPU se houver, senão CPU), `cpu` ou `0`/`1`… (GPU) |
| `YOLO_HALF` | FP16 no PyTorch em GPU CUDA | Padrão: `false`; ignorado em CPU/TRT/ONNX |
| `YOLO_IMGSZ` | Tamanho de entrada da inferência (px) | Padrão: `640`; `960`/`1280` aumentam o recall de aves pequenas |
| `YOLO_TTA` | Test-Time Augmentation global (reforço de recall) | Padrão: `false` (mais lento) |
| `ROI_ADAPTIVE_CONTRAST` | Contraste adaptativo (CLAHE) antes da inferência | Padrão: `true`; revela aves pequenas/camufladas sem afetar a imagem gravada |
| `PRESENCE_GRACE_SECONDS` | Ausência (s) para encerrar a presença — anti-spam "mesma ave = mesmo evento" | Padrão: `30`; faixa: `0` a `600` (ajuste para `30` ou `60`) |
| `ALERT_COOLDOWN_SECONDS` | Cooldown mínimo (s) entre alertas na mesma zona (piso) | Padrão: `30`; faixa: `0` a `600` |
| `PRE_RECORD_SECONDS` | Duração anterior à detecção incluída no clipe | Padrão/mínimo: `3.0` |
| `POST_RECORD_SECONDS` | Duração posterior à detecção | Padrão: `3.0` (com o pré-roll, o clipe cobre ~6 s) |
| `CAMERA_RECONNECT_DELAY_SEC` | Intervalo de reconexão da câmera | Padrão: `3.0` |
| `MEDIA_RETENTION_DAYS` | Retenção de mídia local | Padrão: `30`; mínimo: `1` |
| `APP_DATA_DIR` | Diretório para banco, mídia e segredos de câmera | Opcional; padrão: `back\app-data` |
| `LATITUDE` | Latitude do alimentador (usada pela integração meteorológica) | Padrão: `-23.5505` (São Paulo/SP) |
| `LONGITUDE` | Longitude do alimentador (usada pela integração meteorológica) | Padrão: `-46.6333` (São Paulo/SP) |
| `WEATHER_CACHE_MINUTES` | Intervalo (min) de atualização do cache local de clima | Padrão: `30`; mínimo: `5` |
| `RARE_MOMENTS_ENABLED` | Liga/desliga o agendador de curadoria dos Momentos Raros | Padrão: `true` (`false` desativa a varredura automática) |
| `RARE_MOMENTS_SCAN_HOURS` | Intervalo (h) entre varreduras automáticas de nitidez das capturas | Padrão: `6`; faixa: `1` a `48` |
| `RARE_MOMENTS_DAYS` | Janela padrão (dias) da curadoria exibida na galeria | Padrão: `7`; faixa: `1` a `90` |
| `TIMELAPSE_ENABLED` | Liga/desliga a geração automática do resumo do dia | Padrão: `true` (`false` desativa o agendador) |
| `TIMELAPSE_SPEED` | Fator de aceleração dos clipes no time-lapse | Padrão: `8` (8× mais rápido); faixa: `1` a `60` |
| `TIMELAPSE_HOUR` | Hora local em que o resumo do dia é montado automaticamente | Padrão: `23` (0 a 23) |
| `TIMELAPSE_MINUTE` | Minuto da hora acima | Padrão: `55` (0 a 59) |
| `TIMELAPSE_BACKFILL_DAYS` | Quantos dias anteriores sem resumo são reprocessados ao iniciar | Padrão: `7` (0 a 90) |
| `NIGHT_VISION_MODE` | Modo da visão noturna (infravermelho / baixa luz) | `auto` (padrão), `on` ou `off`; também aceita `true`/`false` |
| `NIGHT_VISION_THRESHOLD` | Luminância média (0–255) que separa claro de escuro no modo `auto` | Padrão: `60` |
| `NIGHT_VISION_CLAHE_CLIP` | Intensidade do realce de contraste local (CLAHE) | Padrão: `2.5`; faixa: `1.0` a `8.0` |
| `NIGHT_VISION_CLAHE_GRID` | Tamanho da grade do CLAHE (blocos por lado) | Padrão: `8`; faixa: `2` a `16` |
| `NIGHT_VISION_DENOISE` | Redução de ruído leve antes do realce | Padrão: `true` |
| `NIGHT_FAUNA_ENABLED` | Expande a detecção para fauna noturna além de aves | Padrão: `false` |
| `NIGHT_FAUNA_CLASS_IDS` | Classes extras do COCO quando a fauna noturna está ligada | Padrão: `15,16` (gato, cachorro) |
| `OFFLINE_YOLO_CONFIDENCE` | Limiar de confiança dedicado à análise offline (mais sensível) | Padrão: `0.25`; faixa: `0.05` a `1.0` |
| `OFFLINE_FRAME_STRIDE` | Passo de amostragem de quadros na análise offline | Padrão: `2` (um a cada dois quadros); faixa: `1` a `10` |
| `OFFLINE_MAX_CLIPS` | Máximo de trechos curtos gerados por vídeo (um por ave) | Padrão: `12`; faixa: `0` a `100` |
| `OFFLINE_CLIP_SECONDS` | Duração (s) do trecho salvo ao redor da melhor captura | Padrão: `4.0`; faixa: `1.0` a `20.0` |
| `BEST_FRAME_ENABLED` | Escolhe automaticamente o quadro mais nítido da janela de gravação | Padrão: `true` (`false` volta a usar o instante do gatilho) |
| `BEST_FRAME_IDEAL_AREA_RATIO` | Proporção ideal da tela (0–1) que a ave deve ocupar no melhor quadro | Padrão: `0.08` |
| `BEST_FRAME_SHARPNESS_SCALE` | Escala de normalização da nitidez (variância do Laplaciano) | Padrão: `120` |
| `BEST_FRAME_MIN_SHARPNESS` | Nitidez mínima para aceitar o quadro (abaixo = desfoque, descartado) | Padrão: `20`; `0` desativa o corte |
| `ENHANCEMENT_ENABLED` | Melhoria automática (CLAHE + redução de ruído) da foto oficial | Padrão: `true` |
| `ENHANCEMENT_CLAHE_CLIP` | Intensidade do CLAHE na foto tratada | Padrão: `2.0`; faixa: `1.0` a `8.0` |
| `ENHANCEMENT_CLAHE_GRID` | Grade do CLAHE (blocos por lado) na foto tratada | Padrão: `8`; faixa: `2` a `16` |
| `ENHANCEMENT_DENOISE` | Redução de ruído leve (não-linear) na foto tratada | Padrão: `true` |
| `ENHANCEMENT_DENOISE_STRENGTH` | Força da redução de ruído | Padrão: `5.0`; faixa: `0` a `20` |
| `ENHANCEMENT_MAX_WIDTH` | Largura máxima (px) da foto tratada (limita o custo do denoise) | Padrão: `1280`; faixa: `320` a `4096` |
| `ENHANCEMENT_MIN_WIDTH` | Largura mínima (px) da foto tratada (garante "alta definição") | Padrão: `720`; faixa: `0` a `4096` |
| `ENHANCEMENT_JPEG_QUALITY` | Qualidade JPEG da foto tratada | Padrão: `95`; faixa: `50` a `100` |
| `CLIP_OVERLAY_ENABLED` | Grava a tarja de identificação (Bem-Te-Vi Core + espécie + confiança) nos clipes salvos | Padrão: `true` (`false` salva o vídeo sem a tarja) |
| `SMART_CROP_MARGIN` | Margem de contexto ao redor da ave no recorte (fração da caixa) | Padrão: `0.25` |
| `SMART_CROP_MIN_DIMENSION` | Dimensão mínima (px) do recorte da ave (amplia se menor) | Padrão: `640` |
| `SMART_CROP_MAX_DIMENSION` | Dimensão máxima (px) do recorte da ave (reduz se maior) | Padrão: `1024` |
| `ADAPTIVE_CONTEXT_ENABLED` | IA ciente do contexto: ajusta a sensibilidade por clima/horário | Padrão: `true` (só torna mais permissivo) |
| `BEHAVIOR_REQUIRE_FEEDING` | Só registra a visita se a ave estiver se alimentando (bico no comedouro) | Padrão: `false` |
| `ANOMALY_LOG_ENABLED` | Log de anomalias: alerta quando uma espécie reaparece após longo intervalo | Padrão: `true` |
| `ANOMALY_SPECIES_GAP_DAYS` | Intervalo (dias) sem registro a partir do qual o retorno é anomalia | Padrão: `180` (~6 meses) |
| `ANOMALY_COOLDOWN_DAYS` | Janela (dias) para não repetir a mesma anomalia de espécie | Padrão: `30` |
| `ALLOW_REMOTE_ACCESS` | Libera acesso à API fora do computador local | Padrão: `false` (somente loopback). Use `true` só com VPN/proxy autenticado |
| `ALLOWED_HOSTS` | Hosts aceitos no cabeçalho `Host` | Padrão: `127.0.0.1,localhost` |
| `GLOBAL_NETWORK_ENABLED` | Liga/desliga o Feed Global e o webhook de entrada | Padrão: `true`; o webhook só funciona com token |
| `GLOBAL_NETWORK_INSTANCE_NAME` | Nome deste jardim exibido nas outras instâncias | Padrão: `Meu Jardim` |
| `GLOBAL_NETWORK_TOKEN` | Segredo compartilhado do webhook | Vazio desativa o recebimento; use uma string longa e aleatória |
| `GLOBAL_NETWORK_PEERS` | URLs base das instâncias parceiras | Separadas por vírgula; o envio vai para `{url}/api/network/webhook` |
| `GLOBAL_NETWORK_SHARE_ALL` | Compartilha também avistamentos comuns | Padrão: `false` (apenas raros/incomuns) |
| `GLOBAL_NETWORK_FEED_DAYS` | Janela (dias) do card Feed Global | Padrão: `7`; faixa: `1` a `90` |
| `GLOBAL_NETWORK_FEED_LIMIT` | Máximo de eventos exibidos no card | Padrão: `20`; faixa: `1` a `100` |
| `GLOBAL_NETWORK_TIMEOUT_SECONDS` | Timeout (s) da publicação em cada parceiro | Padrão: `5.0`; faixa: `1` a `30` |
| `SPECIES_AUTO_ASSOCIATION_ENABLED` | Auto-associação de espécie por re-ID visual contra o Catálogo Local | Padrão: `true` |
| `SPECIES_MATCH_THRESHOLD` | Similaridade de cosseno mínima para aceitar a associação automática | Padrão: `0.65` (65%); faixa: `0.0` a `1.0` |
| `SPECIES_MATCH_MIN_SHARPNESS` | Nitidez mínima (Laplaciano) do recorte para tentar a associação | Padrão: `15`; `0` desativa o corte |
| `SPECIES_MATCH_MAX_REFERENCES` | Teto de fotos de referência avaliadas por consulta | Padrão: `500`; faixa: `10` a `5000` |
| `HD_CROP_MIN_SIDE` | Menor lado (px) do recorte HD exportado | Padrão: `1080`; faixa: `480` a `4096` |
| `HD_CROP_JPEG_QUALITY` | Qualidade JPEG do recorte HD | Padrão: `94`; faixa: `60` a `100` |

O painel administra a integração de IA Externa por completo (chave do Gemini e
modelo), os segredos do Telegram e do Discord, e as preferências de
alerta. A seção **Alertas e Notificações** permite ligar/desligar os avisos,
escolher o modo (`all` ou `new_species`), informar token e chat do Telegram e
disparar um teste de envio real. As demais opções avançadas continuam sendo
ajustadas no arquivo `.env`; alterações manuais nesse arquivo exigem reiniciar o
backend.

### Onde obter as credenciais

- **Telegram:** crie um bot com o `@BotFather` e guarde o token recebido. Inicie
  uma conversa com o bot ou adicione-o ao grupo/canal de alertas; informe o ID
  correspondente em `TELEGRAM_CHAT_ID`.
- **Discord:** nas configurações do servidor/canal, crie um webhook em
  **Integrações → Webhooks** e guarde a URL completa em `DISCORD_WEBHOOK_URL`.
- **IA externa (Google Gemini):** o Bem-Te-Vi usa **exclusivamente** o Google
  Gemini, via a biblioteca oficial `google-genai`. A chave é gratuita e sai de
  [aistudio.google.com](https://aistudio.google.com) — informe em
  `GEMINI_API_KEY` (ou no painel, em **Configurações → Inteligência Artificial
  Externa**). Modelos suportados: `gemini-3.5-flash` (padrão),
  `gemini-3.7-flash`, `gemini-3.8-flash` e `gemini-3.1-pro-preview`.

  O nome do modelo é **sanitizado** pelo backend (`sanitize_model_name`): um
  prefixo `models/` gravado por engano é removido, evitando o `HTTP 404
  NOT_FOUND` da API oficial. O botão **Testar Conexão com Gemini** usa um prompt
  mínimo, faz *backoff exponencial* (3 tentativas) em 429/503 e, se o modelo
  responder 404, tenta automaticamente o próximo modelo validado (`gemini-3.5-flash` → `gemini-3.7-flash` → …).

  A **ficha ornitológica** é pedida em JSON com ~15 campos. Como os modelos
  Gemini 3.x descontam os *tokens de raciocínio* do mesmo `max_output_tokens`,
  a ficha usa um orçamento de **4096 tokens**; se a resposta ainda vier
  truncada (`finish_reason=MAX_TOKENS`), o backend **dobra o orçamento
  automaticamente** (até 8192) antes de trocar de modelo. O JSON é lido de
  forma tolerante (cercas Markdown, texto ao redor e vírgulas finais), o que
  elimina o erro *"ficha ornitológica em formato inválido"*.

  Provedores legados removidos: OpenAI, Anthropic, OpenRouter, Groq e Ollama.


Tokens de bot, URL de webhook e chaves de API funcionam como senhas: qualquer pessoa
que os obtenha pode usar a integração associada. Revogue e gere uma nova credencial
se houver suspeita de exposição.

### Passo 3 — Executar o `start.bat`

Dê um duplo clique em `start.bat`, ou no Prompt:

```bat
cd caminho\para\Bem-Te-Vi
start.bat
```

O script irá, nesta ordem:

1. Verificar Python (3.11+) e Node.js (20+) no PATH  
2. Criar o ambiente virtual em `back\venv` (se ainda não existir)  
3. Instalar/atualizar as dependências Python (`back\requirements.txt`) — só reinstala quando o arquivo muda  
4. Instalar/atualizar as dependências Node (`front\package.json` / `package-lock.json`) — idem  
5. **Iniciar ao mesmo tempo:**
   - **Backend:** `uvicorn` em `http://127.0.0.1:8000`
   - **Frontend:** `vite` em `http://127.0.0.1:5173`
6. Aguardar o health-check da API e exibir os endereços

Duas janelas de console serão abertas:

- `Bem-Te-Vi Backend`
- `Bem-Te-Vi Frontend`

### Passo 4 — Abrir o painel

O `start.bat` tenta abrir o navegador sozinho. Se não abrir, use:

- **Painel (use este):** http://127.0.0.1:5173  
- **API / docs:** http://127.0.0.1:8000/docs  

> **Atenção:** a porta **8000** é só a API. O aplicativo visual é a porta **5173**.  
> Se você abrir `http://127.0.0.1:8000` e achar que “não rodou”, troque para `http://127.0.0.1:5173`.

### Passo 5 — Encerrar

Feche as janelas `Bem-Te-Vi Backend` e `Bem-Te-Vi Frontend`, ou pressione `Ctrl+C` em cada uma.

> Na **primeira execução**, o download do modelo YOLO (`yolov8n.pt`) e dos pacotes Python/Node pode demorar vários minutos.
>
> As dependências são conferidas a cada execução pelo **hash** do `requirements.txt`
> e do `package-lock.json`: depois de um `git pull`, o `start.bat` reinstala sozinho
> o que faltar, sem precisar apagar `back\venv` nem `front\node_modules`.

### Movi/copiei a pasta do projeto — e agora?

Pode mover a pasta inteira sem medo. O `start.bat` foi feito para isso:

- Ele chama **sempre** `back\venv\Scripts\python.exe -m <módulo>` pelo caminho
  absoluto e **nunca** usa `activate.bat`, `pip.exe`, `uvicorn.exe` ou `yolo.exe`.
  Esses arquivos gravam o caminho absoluto da pasta onde o venv nasceu, então
  continuam apontando para a pasta antiga depois de mover — era exatamente essa
  a causa do erro na inicialização.
- Se o `python.exe` do venv não executar, o `start.bat` **recria** o ambiente
  automaticamente (`back\venv`) e reinstala o `requirements.txt`.
- Os caminhos absolutos da fila de aprendizado ativo
  (`training_samples.image_path`) são corrigidos na subida da API, pelo método
  `ActiveLearningService.repair_sample_paths()`.

Se for usar o terminal manualmente, rode `back\venv\Scripts\python.exe -m pip …`
em vez de `pip …` — assim você não depende dos `.exe` antigos do venv.

---

## Instalação manual (alternativa)

Use estes passos se preferir não usar o `start.bat`.

### Backend (Python)

```bat
cd Bem-Te-Vi\back
python -m venv venv
REM Prefira o python.exe do venv a "activate": funciona mesmo se a pasta mudar.
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

copy .env.example .env

venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A API fica em http://127.0.0.1:8000 — docs em http://127.0.0.1:8000/docs

Para rodar os testes automatizados, instale também as dependências de
desenvolvimento e execute o `pytest`:

```bat
pip install -r requirements-dev.txt
python -m pytest tests -q
```

### Frontend (Node.js)

Em **outro** terminal:

```bat
cd Bem-Te-Vi\front
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

A interface fica em http://127.0.0.1:5173

O Vite encaminha automaticamente:

| Caminho no front | Destino |
|------------------|---------|
| `/api/*` | `http://127.0.0.1:8000/api/*` |
| `/captures/*` | `http://127.0.0.1:8000/captures/*` |

Assim o Axios (`baseURL: "/api"`) fala com o FastAPI **sem erros de CORS** no desenvolvimento.

---

## Aplicação desktop (Tauri) — Bem-Te-Vi Monitor

Além do navegador, o **Bem-Te-Vi Monitor** pode rodar como aplicativo desktop
nativo. A casca Tauri fica em `front/src-tauri/` e usa a marca oficial:

| Item | Valor |
|------|-------|
| `productName` | `Bem-Te-Vi Monitor` |
| Título da janela | `Bem-Te-Vi Monitor` |
| Identificador do pacote | `com.bemtevimonitor.app` |
| Ícones | `front/src-tauri/icons/` (gerados por `icons/generate_icons.py`) |

### Pré-requisitos

- [Rust](https://rustup.rs/) (toolchain estável) e as dependências de sistema do
  Tauri 2 para a sua plataforma;
- o **Bem-Te-Vi Core** (backend) rodando em `http://127.0.0.1:8000` — a janela
  desktop é a interface; a inteligência continua no backend local.

### Executar

```bat
cd Bem-Te-Vi\front
cargo install tauri-cli --version "^2"   :: uma única vez
cargo tauri dev                          :: janela de desenvolvimento
cargo tauri build                        :: instalador em front\src-tauri\target\release\bundle
```

> A interface empacotada não passa pelo proxy do Vite, então as URLs precisam
> apontar para o backend local. O frontend aceita as variáveis abaixo (vazio =
> comportamento atual, URLs relativas):
>
> | Variável | Exemplo | Efeito |
> |----------|---------|--------|
> | `VITE_API_BASE` | `http://127.0.0.1:8000/api` | Base do cliente Axios |
> | `VITE_API_ORIGIN` | `http://127.0.0.1:8000` | Prefixo das URLs de API e mídia |
>
> Exemplo (PowerShell) antes de `cargo tauri build`:
>
> ```powershell
> $env:VITE_API_BASE   = "http://127.0.0.1:8000/api"
> $env:VITE_API_ORIGIN = "http://127.0.0.1:8000"
> ```

---

## Verificação rápida da conexão Front ↔ Back

Com o backend no ar, teste no navegador ou no PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/cameras
Invoke-RestMethod http://127.0.0.1:8000/api/visits
Invoke-RestMethod http://127.0.0.1:8000/api/stats
Invoke-RestMethod http://127.0.0.1:8000/api/settings
```

Pelo front (com Vite rodando), as mesmas rotas passam pelo proxy:

- http://127.0.0.1:5173/api/health  
- http://127.0.0.1:5173/api/stats  

Se o painel mostrar “Não foi possível conectar à API”, confirme se a janela **Bem-Te-Vi Backend** está aberta e sem erros.

---

## Funcionalidades e como usar

### Cadastrar câmeras

1. Abra o painel → aba **Central de Câmeras** → **Adicionar câmera externa**.
2. Para uma webcam, escolha **Webcam local (USB)** e informe o índice (ex.: `0`).
3. Para uma câmera IP, stream externo ou **live do YouTube**, cole a **URL do
   Stream ao Vivo** (`rtsp://…`, `https://…/stream.m3u8`, `http://…`,
   `https://www.youtube.com/watch?v=…`). O tipo (RTSP/HLS/HTTP/WebRTC) é
   **detectado automaticamente** a partir do link.
4. **Login e senha são opcionais.** Links públicos/abertos conectam direto, sem
   credenciais. Se a câmera exigir autenticação, abra a seção
   **"Esta câmera exige login e senha? (Opcional)"** e preencha usuário/senha.
5. **Localização global (opcional).** Para câmeras fora do seu fuso — lives do
   YouTube e streams de outros países — abra a seção **"Localização & fuso
   horário (Opcional)"**: informe a **Localidade / Cidade / País** (ex.:
   *Costa Rica - Comedouro de Beija-Flores*) e use **Buscar** para resolver a
   cidade em **coordenadas e fuso IANA** automaticamente (seletor de cidade
   inteligente), ou preencha latitude/longitude/fuso à mão. A partir daí o
   painel daquela câmera exibe o **clima e o horário locais do jardim** em tempo
   real (temperatura, condição e a hora exata de lá — ex.: sol na Costa Rica
   enquanto é noite no Brasil) e os **gráficos de horário de pico** passam a usar
   o fuso da câmera, evitando distorções nas estatísticas (ver
   `back\app\services\camera_weather.py`).

As credenciais (usuário/senha) são armazenadas criptografadas localmente com
**Fernet**. A chave mestra vem de `ENCRYPTION_KEY` no `.env`; se não definida,
uma chave é gerada em `back\app-data\secrets\camera_key.fernet`. Se você colar um
link que **já contenha** usuário/senha (`rtsp://user:senha@host/…`), o backend os
**extrai** da URL, criptografa e grava a URL **sem** as credenciais. O **Smart
Stream Resolver** decide, no worker de captura, se injeta as credenciais na URI
em memória (quando existem) ou usa a URL crua (quando é pública). A URL real e as
credenciais **nunca** chegam ao navegador: o vídeo é entregue por um **proxy
seguro** (`GET /api/streams/proxy/{id}`). A URL exibida na interface tem a
userInfo mascarada (`****:****@host`). O estado aparece no painel como conectado,
reconectando ou offline.

### Mural multi-câmera (Bem-Te-Vi Core distribuído)

No painel principal, o **Mural de Câmeras** exibe 1, 2 ou 4 câmeras simultâneas
(lado a lado) ou uma em foco. Cada fluxo roda em seu **próprio worker** (thread de
captura + IA), com **Bem-Te-Vi Core independente** por câmera: buffer temporal de
~6 s (3 s antes + 3 s depois), cálculo de nitidez (variância do Laplaciano) e
gravação dos melhores quadros no bebedouro/comedouro. Cada feed traz selos em
tempo real do Bem-Te-Vi Core: status de conexão (Online 🟢 / Reconectando 🟡), FPS e a
contagem de aves ativas no bebedouro/comedouro. Se um stream externo cair, o
worker se reconecta sozinho com **backoff exponencial** (sem derrubar o servidor).
O estado por stream é exposto em `GET /api/streams`.

### Lives do YouTube (tradução de link → stream direto)

Além de câmeras IP, você pode cadastrar o link de uma **live do YouTube**
(`https://www.youtube.com/watch?v=…`, `https://youtu.be/…` ou o atalho de canal
`https://www.youtube.com/@canal/live`). O OpenCV/FFmpeg **não** abre a página web
do YouTube, então o backend usa o **`yt-dlp`** para traduzir o link para o
**stream HLS direto** (`m3u8`) antes de abrir a captura. O link direto é então
consumido pelo worker da câmera normalmente — com Bem-Te-Vi Core, selos de status,
FPS e contagem de aves.

- A tradução fica em `app/services/stream_resolver.py` (`resolver_url_direta`).
- Links que **não** são do YouTube (RTSP/HTTP/HLS) passam direto, sem alteração.
- Como o token de acesso de uma live **expira após algumas horas**, a reconexão
  do worker **re-extrai** automaticamente um link novo quando o stream cai
  (backoff exponencial). O cache curto (`YOUTUBE_RESOLVER_CACHE_SEC`) evita
  re-extrair a cada tentativa, mas é ignorado na reconexão.
- Para desligar a tradução: `YOUTUBE_RESOLVER_ENABLED=false` no `.env`.
- Alguns vídeos/lives caem no bloqueio **"Sign in to confirm you're not a bot"**.
  Nesse caso o backend repete a extração com um **cliente alternativo** do
  YouTube (`android`) automaticamente. Se ainda assim falhar (live restrita),
  informe um **arquivo de cookies** em `YOUTUBE_COOKIES_FILE` no `.env`.

> Dica: instale um runtime JavaScript (ex.: `deno`) para o `yt-dlp` acessar
> **todos** os formatos do YouTube. Sem ele, o yt-dlp ainda entrega o vídeo da
> live (HLS), mas alguns formatos podem ficar de fora.

### Desenhar zonas de leitura (ROI)

1. Na câmera cadastrada, abra **Editar área** / **Áreas de leitura**.
2. Selecione **Incluir** para desenhar uma região monitorada (verde) ou **Excluir**
   para marcar uma região ignorada (vermelho).
3. Clique na imagem ao vivo para adicionar vértices. Uma área precisa de pelo menos
   três pontos; use **Desfazer ponto** para corrigir e **Concluir área** para fechar
   o polígono.
4. Salve as áreas. As coordenadas são normalizadas entre `0` e `1`, vinculadas à
   câmera e persistidas localmente no SQLite.

Quando não há zonas de inclusão, a imagem inteira é elegível. Havendo inclusões,
somente regiões dentro de uma delas são elegíveis; zonas de exclusão removem suas
regiões mesmo quando sobrepostas a uma inclusão. O pipeline mascara a imagem antes
da inferência e também valida a posição das detecções antes de criar visitas.
Alterações nas zonas reiniciam o pipeline daquela câmera.

### Selecionar Zonas de Interesse (ROI) retangulares

Além das áreas poligonais, cada câmera conta com um editor visual de **Zonas de
Interesse (ROI)** retangulares, pensado para recortes rápidos sobre o feed:

1. Na câmera, clique em **Zonas ROI**.
2. Escolha o modo de desenho:
   - 🟢 **Zona de Inclusão (Monitorar):** só registra visitas e fotos se o
     passarinho aparecer dentro do quadrado.
   - 🔴 **Zona de Exclusão (Ignorar):** descarta qualquer detecção dentro do
     quadrado (galhos balançando, vento, tráfego, reflexos).
3. Clique e arraste o mouse sobre o vídeo para desenhar o retângulo, com borda
   colorida e fundo translúcido. Os botões flutuantes **Desfazer Último**,
   **Limpar Tudo** e **Salvar Zonas** agilizam a edição, e a lista lateral permite
   remover zonas individualmente.

As coordenadas são normalizadas (`x1, y1, x2, y2` entre `0` e `1`) e vinculadas à
câmera. O filtro usa o **centro da caixa delimitadora** da ave: havendo inclusões, a
ave precisa estar em pelo menos uma delas; qualquer exclusão sobreposta descarta a
detecção. As ROI retangulares somam-se às áreas poligonais (união de inclusões e
união de exclusões) e o pipeline recarrega as zonas automaticamente após salvar,
sem reiniciar o backend.

### Consultar visitas e pedir identificação externa

- **Painel:** acompanhe streams, indicadores e estatísticas.
- **Galeria:** consulte visitas e thumbnails, reproduza os clipes no player
  embutido (clique na miniatura ou em **Reproduzir clipe**) e use a exportação CSV.
- Em uma visita genérica/não identificada, clique em **🤖 Perguntar à IA Externa**.
  A Galeria mostra **Analisando ave...** durante a solicitação e atualiza o cartão
  com os nomes comum e científico retornados.
- A identificação usa a **imagem tratada** da visita — o recorte da ave ou a
  thumbnail oficial em alta definição geradas pelo pipeline —, enviada por HTTPS
  ao **Google Gemini** (único provedor suportado) através da biblioteca oficial
  `google-genai`. Basta definir `GEMINI_API_KEY` (ou informar a chave em
  **Configurações → Inteligência Artificial Externa**).
- Ao identificar, o Bem-Te-Vi **cadastra automaticamente a espécie no Catálogo
  Local (Life List)** e associa a visita (a foto tratada vira a imagem de
  referência da espécie), sem gerar duplicatas. Pela API, o parâmetro
  `add_to_catalog=false` desativa esse cadastro automático.
- No cartão da **Galeria**, o **recorte tratado** da ave (close-up) aparece em
  destaque como miniatura **Recorte** — dá para conferir a plumagem sem abrir o
  registro. O recorte é servido por `GET /api/visits/{id}/crop` (arquivos em
  `back\app-data\crops\`).
- Depois de identificada, use **🔎 Ficha ornitológica (IA)** no cartão da Galeria
  ou **Perguntar à IA Externa** no detalhe da visita para pedir uma **consulta
  profunda** da espécie (`POST /api/visits/{id}/ask-ai`): nome científico,
  família, ordem, status de conservação, dieta, comportamento alimentar, habitat,
  distribuição, dados biogeográficos, migração, porte, longevidade e
  curiosidades, exibidos em um modal formatado. A ficha fica em cache nos
  metadados da visita; use **Atualizar** (ou `refresh=true`) para reconsultar.
- A mesma consulta também está disponível **no nível da espécie**, a partir de
  **Minhas Aves** (botão **Ficha IA** no cartão) e do **Álbum de Conquistas** /
  ficha técnica (botão **🔎 Ficha ornitológica (IA)**) —
  `POST /api/species/{id}/ask-ai`. Aqui o *prompt* usa o nome popular/científico
  cadastrado e a **foto de referência tratada**; o resultado fica em cache na
  própria espécie (`bird_species.ai_consult_json`, migração 7) e é reaproveitado
  pela ficha técnica da espécie.
- Sem imagem tratada disponível ou chave configurada, a API informa o erro. Os
  recortes ficam em `back\app-data\crops\` e seguem a política de retenção de mídia.

### Detecção Sonora (aba dedicada)

Além de ver, o Bem-Te-Vi **escuta**. A aba **Detecção Sonora** reúne os cantos
identificados pelo **BirdNET** em **blocos de 5 itens**, carregados de forma
**incremental** pelo botão **"Ver mais…"** (sem paginação numérica), e dá ações de
curadoria a cada registro:

- **Player integrado por card:** cada detecção tem o **clipe de áudio** gravado
  (WAV) reproduzível ali mesmo — botão play/pause, barra de progresso arrastável,
  volume e mudo. Nada toca sozinho: o observador decide quando ouvir.
- **Espectrograma visual:** ao lado do player, o card exibe o gráfico de
  **frequência × tempo** do canto, gerado com **Librosa + Matplotlib** (backend
  `Agg`) e salvo em `back\app-data\spectrograms\{id}.png`. O mesmo PNG é enviado
  à IA externa quando o observador pede a identificação. Clique na imagem para
  ampliar. Endpoint: `GET /api/audio-detections/{id}/spectrogram` (gera sob
  demanda e reaproveita o arquivo).
- **🌙 Viajantes Noturnos (Migração — NFC):** o alternador no topo do painel troca
  entre **Todos os cantos** e **Viajantes Noturnos (Migração)**. Durante a janela
  noturna configurada (padrão 22:00–05:00 no horário local da câmera), o limiar
  de confiança do BirdNET é reduzido (`NFC_CONFIDENCE_THRESHOLD`, padrão 0.45) para
  captar os **chamados de voo curtos** (*flight calls*) de aves migrantes que
  cruzam o céu acima do jardim. Cada detecção noturna recebe `is_nfc=1`, pontuação
  `nfc_score` e a `night_date` (data local da noite que começou no dia anterior).
  A migração v17 adiciona as colunas `is_nfc`, `nfc_score` e `night_date` à tabela
  `audio_detections`. Endpoint: `GET /api/audio-detections/nfc`.
- **Associar manualmente:** o seletor **Associar à espécie** vincula o canto a um
  card já existente da **Life List** (`Minhas Aves`), sem duplicar espécies.
- **Identificar com IA Externa:** o botão envia o **espectrograma** do áudio
  (gerado localmente pelo módulo de espectrogramas, com fallback OpenCV quando o
  Matplotlib não está instalado) para o provedor de IA
  configurado e devolve o nome popular/científico — cadastrando a espécie quando
  for nova. Endpoint: `POST /api/audio-detections/{id}/identify-external`.
- **Perguntar à IA Externa:** abre a **ficha ornitológica profunda** da espécie
  detectada (família, conservação, dieta, habitat, biogeografia, curiosidades),
  com cache reaproveitado. Endpoint: `POST /api/audio-detections/{id}/ask-ai`.
- **Excluir:** remove a detecção sonora do histórico (com o áudio no disco).

O mesmo painel aparece na **Galeria → aba "Áudios"**, mantendo **imagens/vídeos** e
**áudios** em galerias separadas. A análise é 100% local; nenhum áudio sai da máquina.

### Diário de Campo e exportação para ciência cidadã (eBird)

A aba **Diário de Campo** compila automaticamente o relatório de observação do
dia — e transforma o histórico local em dados prontos para a ciência global.

- **Relatório do dia:** data, horários de primeira/última observação, clima
  (Open-Meteo, gravado em cada visita e com consulta ao vivo quando necessário),
  coordenadas de cada jardim/câmera, espécies, comportamento, confiança e as
  fotos/clipes das aves avistadas. O botão **Ler o diário completo em texto**
  mostra a versão para imprimir ou copiar.
- **Exportar eBird:** gera um CSV no **eBird Record Format** (Cornell Lab of
  Ornithology), com as 19 colunas oficiais, uma linha por espécie/jardim. O
  arquivo sai **sem cabeçalho**, com data `mês/dia/ano`, nomes popular/científico
  (gênero e espécie separados), contagem, coordenadas decimais, horário local,
  duração, protocolo `Stationary`, país em código ISO e observações. Rótulos
  genéricos (`bird`, "Pássaro Desconhecido") são omitidos — o eBird exige uma
  espécie válida. O checklist é marcado como automático/incompleto (`N` em
  *All observations reported?*), pois a IA pode não registrar todas as aves.
- **Baixar CSV limpo:** planilha em pt-BR, uma linha por espécie/jardim, com
  clima, confiança, status ecológico e observações.
- **Rotas:** `GET /api/journal?date=AAAA-MM-DD`, `GET /api/journal/export/ebird`
  e `GET /api/journal/export/csv` (todas aceitam `camera_id` para filtrar um
  jardim). O serviço fica em `app/services/field_journal.py` e é somente leitura.

### Alertas Preditivos e Resumo Matinal Automatizado

#### Central de Regras de Alerta Personalizadas (Smart Alerts)

A aba **Configurações** ganhou a seção **Regras de Alerta Personalizadas**. O
observador cria regras condicionais que são avaliadas em background antes de
disparar qualquer notificação (Telegram/Discord):

- **Campos:** espécie nova, espécie rara, nitidez mínima, confiança mínima,
  jardim específico, tipo de visitante, indivíduo recorrente.
- **Operadores:** `=`, `≠`, `>`, `≥`, `<`, `≤`, `contém`, `em lista`.
- **Lógica:** OR entre regras habilitadas, AND entre condições de uma regra.
  Uma regra sem condições é sempre satisfeita.
- **Endpoints:** `GET/PUT/POST/DELETE/PATCH /api/settings/smart-alerts`
- **Serviço:** `app/services/smart_alerts.py` — persiste regras como JSON no
  `SettingsRepository` sob a chave `smart_alert_rules`.

#### Resumo Matinal Automatizado (Morning Briefing)

Agendador diário (`MorningBriefingScheduler`) que dispara no horário configurado
(padrão 07:00). Compila e envia via Telegram/Discord:

- **Clima:** previsão Open-Meteo para cada jardim cadastrado.
- **Predição:** visitas prováveis do dia via Bem-Te-Vi Core (memória comportamental).
- **Foto de destaque:** postal do Momento Raro do dia anterior.

Configuração: `MORNING_BRIEFING_ENABLED`, `MORNING_BRIEFING_HOUR`,
`MORNING_BRIEFING_MINUTE` (env) ou via painel de configurações.

### Feed Global Bem-Te-Vi (jardins conectados)

O Painel Principal ganhou o card **Feed Global Bem-Te-Vi**: um mural em tempo
real com os destaques **raros e incomuns** deste jardim e das instâncias
parceiras (ex.: *“🦜 Rara Tangará avistada no Jardim de Paris há 5 minutos”*).

- **Funciona sozinho:** mesmo sem parceiros, o feed mostra os destaques das
  câmeras locais. O status de conservação regional (`rara`, `endêmica`,
  `migratória`), as anomalias de reaparecimento e a **frequência local**
  (primeiros registros de uma espécie no jardim) definem o destaque.
- **Webhook seguro (opcional):** `POST /api/network/webhook` recebe eventos de
  outra instância. Só responde quando `GLOBAL_NETWORK_TOKEN` está definido; o
  token vai no cabeçalho `X-Bem-Te-Vi-Token` e é comparado em tempo constante
  (`hmac.compare_digest`). Sem token, a rota responde **503**; token inválido,
  **401**. A rota tem *rate limit* e não aceita mídia/URLs externas.
- **Publicação assíncrona:** ao registrar uma ave rara/incomum, o backend grava
  o evento em `network_feed_events` (migração v16) e envia aos parceiros em uma
  thread separada, com timeout curto. A captura nunca espera a rede.
- **Configuração:** `GLOBAL_NETWORK_ENABLED`, `GLOBAL_NETWORK_INSTANCE_NAME`,
  `GLOBAL_NETWORK_TOKEN`, `GLOBAL_NETWORK_PEERS` (URLs base separadas por
  vírgula), `GLOBAL_NETWORK_SHARE_ALL`, `GLOBAL_NETWORK_FEED_DAYS`,
  `GLOBAL_NETWORK_FEED_LIMIT` e `GLOBAL_NETWORK_TIMEOUT_SECONDS`.
- **Rotas de leitura:** `GET /api/network/feed` e `GET /api/network/status`
  (o status nunca devolve token nem URLs privadas).

### Montar resumos do dia (time-lapse)

O Bem-Te-Vi junta os clipes de um dia em um único vídeo acelerado — o **Resumo do
Dia** — para rever os melhores momentos em segundos, sem assistir a cada gravação
individual.

- **Automático:** por padrão, ao fim do dia (23h55, ajustável em
  `TIMELAPSE_HOUR`/`TIMELAPSE_MINUTE`), o backend monta
  `back\app-data\captures\timelapses\timelapse_AAAA-MM-DD.mp4` a partir dos clipes
  das visitas daquele dia.
- **Sob demanda:** na aba **Galeria → Resumos do Dia (Time-Lapse)**, use **Gerar
  resumo de hoje** para montar (ou regerar) o vídeo na hora.
- **Recuperação:** ao iniciar, o backend reprocessa os últimos
  `TIMELAPSE_BACKFILL_DAYS` dias que tenham clipes mas ainda não tenham resumo
  (útil quando o computador ficou desligado).

A montagem usa o `ffmpeg` via `subprocess`: os clipes são concatenados com o
*demuxer* `concat` e acelerados pelo filtro `setpts` (fator `TIMELAPSE_SPEED`).
Como as câmeras podem gravar em resoluções diferentes, os quadros são normalizados
para 1280×720 (`scale`+`pad`) e recodificados em **H.264** (`yuv420p`,
`+faststart`), garantindo um MP4 que o navegador reproduz. O dia é interpretado no
**fuso local** do computador e convertido para o intervalo UTC na consulta ao
banco. O player fica embutido na própria aba e usa o endpoint
`/api/videos/timelapse/{arquivo}`, com suporte a `Range`. Se o `ffmpeg` não estiver
instalado no sistema, o Bem-Te-Vi usa automaticamente o binário embutido no pacote
Python `imageio-ffmpeg` (instalado pelo `requirements.txt`); só quando nem esse
binário existe a geração fica indisponível (com aviso no log) e o restante do
sistema segue normal.

### Reels verticais (9:16) para redes sociais

O Bem-Te-Vi gera vídeos verticais **1080×1920** prontos para Instagram Reels,
TikTok e YouTube Shorts a partir do clipe de ~6 segundos de cada visita.

- **Corte inteligente:** o `crop` do FFmpeg é centrado na **bounding box** da ave
  (ou no centro do quadro, sem bbox), mantendo a proporção 9:16.
- **Moldura translúcida:** faixas escuras no topo e na base (`drawbox`) garantem a
  legibilidade da sobreposição.
- **Sobreposição oficial:** marca d'água **Bem-Te-Vi**, nome popular e científico
  da espécie, temperatura do momento e data, com `drawtext`.
- **Geração preguiçosa:** o MP4 é criado uma única vez por visita (cache em
  `app-data/captures/reels/{visit_id}.mp4`) e reaproveitado nas próximas chamadas.
- **Onde usar:** botão **🎬 Gerar Reel p/ Redes** em cada card da **Galeria** e no
  player dos **Resumos do Dia (Time-Lapse)** (que usa a melhor visita do dia).
- **Endpoints:** `POST /api/media/generate-reel/{visit_id}` (gera),
  `GET /api/media/reel/{visit_id}` (streaming), `DELETE /api/media/reel/{visit_id}`.

### Monitorar 24 horas com visão noturna (infravermelho)

O Bem-Te-Vi continua enxergando no escuro. Quando a luminosidade cai (ou a
câmera entra em modo infravermelho e passa a entregar imagens em preto e branco),
o backend realça o contraste e reduz o ruído de cada quadro **antes** da
inferência do YOLOv8, ajudando a IA a identificar formas mesmo à noite.

- **Automático (recomendado):** o realce entra apenas quando a luminância média
  do quadro fica abaixo do limiar configurado (`NIGHT_VISION_THRESHOLD`). De dia,
  nada é alterado.
- **Sempre ligada:** aplica o realce em todos os quadros — útil para câmeras IR
  que não escurecem o suficiente.
- **Desligada:** os quadros seguem originais para a detecção.

O ajuste fica em **Configurações → Calibração e Ajustes → Visão Noturna
(Infravermelho)**, com o modo, o limiar de luminosidade e a opção de **monitorar
fauna noturna além de aves** (gatos, cachorros e outros animais do COCO). Corujas
já são aves e continuam sendo detectadas normalmente. As mudanças são aplicadas em
tempo de execução, sem reiniciar o backend.

Onde você vê o status noturno:

- **Painel → Transmissão ao vivo:** ícone de lua 🌙 e um filtro suave sobre o vídeo
  enquanto o realce está ativo.
- **Câmeras:** um selo **Visão noturna** no cartão da câmera.
- **Galeria:** um selo **Noturno** nas capturas registradas com o realce ativo.

Tecnicamente, o realce usa **CLAHE** (contraste local adaptativo) no canal de
luminosidade e um **median blur** leve contra o ruído de sensor. O portão de
movimento continua medindo o quadro **cru**, para que o realce não gere falsos
positivos. O modo `auto` só gasta processamento quando a cena está escura.

### Motor de IA avançado (Edge AI + inteligência biológica)

O motor local evoluiu de um simples "detector de presença" para um **assistente
biológico autônomo**, rápido e sensível, pensado também para uso científico.

**1. Velocidade e sensibilidade (Edge AI).** O YOLOv8 pode rodar acelerado por
**TensorRT**, **ONNX** ou **FP16** em GPU, com queda automática para CPU quando
não há aceleração disponível. Gere o artefato otimizado uma vez com:

```bat
cd back
venv\Scripts\python.exe -m tools.exportar_modelo --formato onnx
```

Com `YOLO_ACCELERATION=auto`, o Bem-Te-Vi passa a usar o `.onnx`/`.engine`
automaticamente. Ajuste `YOLO_DEVICE`, `YOLO_HALF`, `YOLO_IMGSZ` e `YOLO_TTA`
conforme o hardware. A telemetria do backend informa o backend em uso.

**2. Sensibilidade dinâmica por ROI.** Cada ROI retangular pode ter um **papel**
(comedouro, bebedouro, poleiro) e um **limiar de confiança próprio**. No
comedouro, o sistema usa um limiar mais permissivo (ex.: 0,22–0,28) e aplica um
**filtro de contraste adaptativo (CLAHE)** antes da inferência, revelando aves
pequenas e camufladas (saíras, cambacicas) sem afetar o resto da cena nem a
imagem gravada.

**3. Contagem de bandos (multi-espécie).** O rastreador atribui um **ID estável**
a cada indivíduo. O sistema conta o **pico simultâneo** e o **total de
indivíduos** da janela, registrando frases como *"3 Cambacicas e 2 Saíras
presentes simultaneamente"*. A Galeria mostra o selo **👥 N** quando há bando.

**4. Status ecológico regional.** Cada espécie é cruzada com uma base curada da
**avifauna do Sul do Brasil / Santa Catarina** e recebe um selo: 🟢 Nativa,
🟡 Migratória, 🔵 Endêmica, ⭐ Rara/Acidental, 🟠 Exótica. Os selos aparecem em
**Minhas Aves**, no **Álbum** e na **Galeria**, apoiando monitoramento de
conservação.

**5. IA ciente do contexto.** O motor lê a calibração do usuário, respeita as
zonas de exclusão e correlaciona o **clima** (Open-Meteo). Em chuva, nevoeiro ou
céu encoberto, a visibilidade cai: o limiar é relaxado e o contraste adaptativo
(TTA leve nos casos severos) entra em ação — sempre de forma conservadora, nunca
acima do que o usuário configurou.

**Extras.** Análise de comportamento (**alimentando-se** × **pousada** × **em
movimento**) e **log de anomalias**: se uma espécie que não era registrada há
mais de 6 meses reaparecer, um alerta é criado no painel (`GET /api/anomalies`).

**9. Auto-associação de espécie (re-ID visual).** Quando o detector devolve
apenas o rótulo genérico (`bird`), o módulo `app/ai/species_association.py`
compara a **assinatura visual** do recorte tratado com as fotos de referência do
Catálogo Local (`bird_species.reference_image_path`) por **similaridade de
cosseno**:

- acima de `SPECIES_MATCH_THRESHOLD` (**0.65 = 65%**), a visita recebe o nome
  popular da espécie, o vínculo com o catálogo e o selo
  `Identificado pelo Bem-Te-Vi Core`;
- as referências ficam em **cache**, invalidado pela assinatura
  `(id, caminho, mtime)` — trocar uma foto de referência recalcula só o que
  mudou;
- visitas com curadoria humana (`Espécie Confirmada`, `Reclassificado pelo
  usuário`, `Identificado por IA Externa`) **nunca** são sobrescritas;
- o extrator é o mesmo da re-identificação individual: **MobileNetV3-Small**
  (576 dims) com fallback **OpenCV** (180 dims) para instalações offline.

Variáveis: `SPECIES_AUTO_ASSOCIATION_ENABLED`, `SPECIES_MATCH_THRESHOLD`,
`SPECIES_MATCH_MIN_SHARPNESS`, `SPECIES_MATCH_MAX_REFERENCES`.

**10. Reclassificação e pasta de retreinamento.** O botão **“Associação
Incorreta / Reclassificar”** (`POST /api/visits/{id}/reclassify`) aplica a
espécie correta, grava o recorte em
`app-data/fine_tuning/{espécie}/{visit_id}.jpg` e registra a proveniência em
`app-data/fine_tuning/index.jsonl` (visita, espécie, origem, observação,
confiança e data). Reclassificar a mesma visita **move** a amostra, evitando
que o mesmo recorte ensine duas classes contraditórias. A fila operacional do
fine-tuning automático continua em `app-data/training_queue/`.

**11. Recorte HD sob demanda.** `GET /api/visits/{id}/crop/hd` gera
`app-data/crops/{id}_hd.jpg` (reescala Lanczos até `HD_CROP_MIN_SIDE`,
*unsharp mask* + CLAHE na luminância) e devolve o arquivo como anexo, pronto
para compartilhar ou servir de material de retreinamento.

**7. Bem-Te-Vi Core Smart Match.** Toda identificação é comparada com a Life List
antes de virar cadastro: espécies repetidas apenas **incrementam o contador de
visitas** e agregam a nova mídia ao card existente (sem duplicatas); espécies
**novas** ganham automaticamente um card no Álbum de Conquistas, com a melhor
foto tratada e o status ecológico regional.

**8. Horário local por câmera (fuso global).** Cada visita guarda a **hora e a
data locais do jardim** (fuso IANA cadastrado na câmera — migração 8). Com isso,
os histogramas de horário de pico, o "pico do dia" e as medalhas de
madrugada/noite do Bem-Te-Vi Core são calculados pelo **relógio do jardim**, e não
pelo UTC: uma visita às 10h na Costa Rica não aparece mais como "madrugada" no
Brasil. Câmeras sem fuso cadastrado continuam usando o UTC (comportamento
anterior, sem quebrar o histórico).

**6. IA visível — Bem-Te-Vi Core.** O motor de IA do Bem-Te-Vi assina como
**Bem-Te-Vi Core v1.0** (a assinatura aparece em `GET /api/ai/status` e nos metadados
de cada visita). O painel ganha um **Núcleo de IA** (widget futurista em Dark Mode
com pulsos neon, selo "Potencializado por Bem-Te-Vi Core") que mostra em tempo real o
estado do modelo, o FPS do stream, a latência da inferência, o número de
inferências/detecções (hoje e total), o uso de CPU/RAM, o backend em uso
(TensorRT/ONNX/PyTorch) e o tempo de atividade. Ao lado, um **terminal de logs
cognitivos** lista os "pensamentos" do Bem-Te-Vi Core conforme acontecem (detecção,
nitidez do quadro escolhido, identificação da espécie, auto-calibração por clima,
bandos e anomalias), cada linha assinada com `[Bem-Te-Vi Core]`. A **Galeria** passa a
exibir, em cada card, um **Índice de Certeza da IA** (barra 0–100%) e a
**anotação ornitológica** gerada automaticamente (ex.: "Espécie identificada:
Tangara sayaca (Nativa) — alimentando-se em grupo de 3 indivíduos, sob
temperatura de 24°C e céu limpo."). Os endpoints `GET /api/ai/status` e
`GET /api/ai/logs` expõem essa telemetria para integração externa. O comportamento
pode ser desligado com `AI_INSIGHTS_ENABLED=false`.

**7. Alta sensibilidade e anti-spam (Bem-Te-Vi Core).** Para não perder aves
pequenas ou paradas no comedouro **e** evitar alertas/gravações repetidos da
mesma visita, o motor já inicia com:

- **Confiança `0.22`** por padrão (mais permissiva), com **CLAHE** ligado antes
  da inferência para destacar a plumagem contra o fundo do comedouro;
- **Retenção de rastreio de `10 s`** e **sensibilidade de movimento `0.80`**,
  mantendo a ave na mesma visita mesmo quando o YOLO a perde por instantes;
- **Regra de permanência:** enquanto a ave estiver no comedouro, o Bem-Te-Vi Core mantém
  o rastreio e o buffer ativos, mas **não cria novos alertas/registros** — o
  movimento contínuo é tratado como o **mesmo evento em andamento**;
- **Encerramento por ausência:** um novo alerta só ocorre se a ave **sair
  completamente** da zona por mais de `PRESENCE_GRACE_SECONDS` (padrão `30 s`) e
  uma nova ave pousar, respeitando ainda o `ALERT_COOLDOWN_SECONDS` (padrão
  `30 s`) por zona.

Tudo isso já vem **ativado por padrão** — não é preciso ajustar nada a cada
inicialização. Os valores podem ser afinados no `back\.env` (`YOLO_CONFIDENCE`,
`OBJECT_PERSISTENCE_TIME`, `MOTION_SENSITIVITY`, `PRESENCE_GRACE_SECONDS`,
`ALERT_COOLDOWN_SECONDS`) ou, no caso do cooldown, por zona no painel.

**8. Overlays visuais e identificação nos vídeos (Bem-Te-Vi Core).** O Bem-Te-Vi Core deixa
de ser "invisível": ele passa a **desenhar a própria atuação** sobre o vídeo.

- **No stream ao vivo** (câmeras locais e remotas), cada ave detectada recebe uma
  **caixa delimitadora arredondada** e um **selo flutuante** com a marca
  `✨ Bem-Te-Vi Core`, o **nome da espécie** e a **confiança** (ex.: `Tangara sayaca
  96%`). Aves aparecem em esmeralda e a fauna noturna em âmbar. O desenho é feito
  com poucas operações por caixa (sem cópias extras de quadro), então **não
  introduz atraso** no stream.
- **No painel**, o feed da câmera se **ilumina** (borda e brilho esmeralda)
  enquanto o Bem-Te-Vi Core está rastreando uma ave, com um **card flutuante**
  *"Bem-Te-Vi Core rastreando"* mostrando a contagem e as **espécies ativas naquele
  instante**. O Mural multi-câmera recebe o mesmo realce e o selo de espécies.
- **Nos clipes gravados (6 s)**, o vídeo é salvo **já com uma tarja fosca de
  identificação** no rodapé (marca `Bem-Te-Vi Core`, espécie, confiança, câmera e
  horário). Assim a espécie é inconfundível mesmo se o arquivo for baixado,
  compartilhado ou aberto fora do painel. A tarja é pré-renderizada **uma única
  vez por clipe** e apenas mesclada em cada quadro — a gravação continua barata.
  Pode ser desligada com `CLIP_OVERLAY_ENABLED=false`.
- **Na Galeria**, o player de vídeo exibe um **selo elegante sobre o vídeo**
  (tarja fosca em Dark Mode com ícone de ave, o nome da espécie em destaque e a
  confiança), além dos selos ecológicos e de bando — resolvendo de imediato a
  pergunta "qual ave está neste vídeo?".

### Manter o catálogo local de aves

1. Abra **Minhas Aves** e escolha **Cadastrar Nova Ave**.
2. Preencha o nome popular, o nome científico e, se desejar, observações e uma foto
   de referência de até 8 MB. A imagem é validada e armazenada localmente como JPEG.
3. Na **Galeria**, use o menu **Associar ao catálogo** de uma visita para vincular
   o evento a uma espécie. O cartão mostra os nomes popular e científico; a seleção
   é salva na visita e atualiza o histórico sem recarregar o painel.
4. Para remover uma espécie, confirme a exclusão. A foto de referência também é
   removida. As visitas antigas são preservadas, mas deixam de apontar para a espécie
   removida.
5. Clique em qualquer card (**Minhas Aves** ou **Álbum de Conquistas**) para abrir
   a **ficha técnica** da espécie: histórico de avistagens, horários de pico no
   comedouro, temperatura média preferida (cruzada com a Open-Meteo), notas
   científicas e status ecológico regional (`GET /api/species/{id}/profile`).
   A miniatura do card usa o **recorte tratado** da melhor visita (close-up).

O **Bem-Te-Vi Core Smart Match** compara automaticamente cada identificação com a
Life List antes de virar cadastro: se a espécie **já existe**, a visita é
vinculada ao card existente (sem duplicar registros) — o contador de visitas sobe
e a nova foto/vídeo passam a integrar a galeria daquela espécie; se é **nova**,
um card estruturado é criado no Álbum de Conquistas, já com a melhor foto tratada
e o status ecológico. Se o card ainda não tinha foto de referência, ela é
preenchida com o recorte tratado desta captura.

O catálogo fica na tabela `bird_species` do SQLite, com imagens em
`back\app-data\reference_birds\`. A associação de visitas usa `species_id`; ela é
opcional e não altera a detecção automática do YOLO. Use a Galeria para revisar e
associar manualmente as detecções com as espécies conhecidas.

### Visitantes Silvestres / Convidados do Jardim (Modo Esquilo)

O Bem-Te-Vi Core classifica o animal que aparece no comedouro com uma camada de
**taxonomia pos-deteccao** (`app/domain/fauna_taxonomy.py`): aves seguem o fluxo
ornitologico normal; mamiferos (esquilos, gatos, gambas, morcegos...) viram
**Visitantes Especiais** -- nao entram na Life List ("Minhas Aves") nem nas
estatisticas de aves, nao disparam alertas de Telegram/Webhook e nao geram
anomalia ornitologica, mas ganham:

1. **Painel "Visitas de Hoje" -> aba "Visitantes Especiais"**: contador secundario
   com as aparicoes do dia e as estatisticas divertidas do "Modo Esquilo"
   (ex.: esquilo 3 visitas hoje, ~36 sementes roubadas hoje).
2. **Galeria -> aba "Convidados do Jardim"**: capturas dos bichos, agrupadas sob a
   categoria tematica (ex.: Convidados do Jardim (Esquilos)).
3. **Album de Conquistas -> badge secreta "O Ladrao de Sementes"**: desbloqueada
   automaticamente na primeira aparicao de um esquilo. As medalhas secretas
   aparecem mascaradas ("???") ate serem conquistadas.
4. **Resumo dedicado**: `GET /api/wildlife/summary` (totais, por grupo, sementes
   estimadas, badge desbloqueada) e `GET /api/wildlife/visits?today=true`.

A deteccao dos Visitantes Especiais pode vir de duas fontes:
- **Fauna noturna** (classes extras do COCO, ex.: gato/cachorro) quando
  `NIGHT_FAUNA_ENABLED=true`;
- **Identificacao externa** (Gemini Vision): se a IA externa identifica o
  animal como esquilo/gato/etc., a visita e reclassificada como Visitante
  Especial e **nao** e cadastrada na Life List (guarda anti-esquilo).

A classificacao e conservadora: na duvida, o animal e tratado como **ave**, para
nunca descartar um passaro legitimo.

### Analisar vídeos gravados ou cartões de memória

1. Copie a gravação do cartão de memória para o computador.
2. Abra a aba **Câmeras** e, na área **Análise de Cartão de Memória**, escolha a
   câmera à qual as visitas devem ser associadas (as zonas dessa câmera filtram
   as detecções).
3. **Arraste e solte** um ou vários arquivos `.mp4`, `.avi`, `.mov` ou `.mkv`
   (até 2 GB cada) na área pontilhada — ou clique para selecionar. É preciso
   cadastrar uma câmera antes: as zonas dessa câmera são usadas para filtrar as
   detecções.
4. Acompanhe o envio e a análise. A **barra de progresso flutuante** mostra, em
   tempo real, o percentual e o quadro processado (ex.: `65% — Processando
   frame 450/1200…`) e **continua visível ao trocar de aba**, porque quem
   processa é o backend, não o navegador.
5. Ao concluir, aparece um cartão com selo de sucesso e a contagem exata (ex.:
   **🐦 3 Pássaros Encontrados**), com miniaturas das capturas e o botão
   **Ver na Galeria** para assistir aos trechos.

A IA da análise offline é **mais sensível** que a captura ao vivo: usa um limiar
de confiança dedicado (`OFFLINE_YOLO_CONFIDENCE`, padrão `0.25`) e agrupa as
detecções em *aves distintas* por associação temporal (IoU + proximidade de
centro). Assim, uma ave contínua conta **uma** vez, mesmo aparecendo em centenas
de quadros, e aves diferentes no mesmo vídeo contam separadamente. Para cada ave
distinta o sistema salva a melhor miniatura e o recorte ampliado, cria
automaticamente uma visita na Galeria e gera um trecho curto
(`OFFLINE_CLIP_SECONDS`) para o botão de reprodução.

O horário de cada evento é estimado somando a posição temporal do quadro no vídeo
à data de última modificação do arquivo, enviada pelo navegador. Essa data pode não
corresponder ao horário original se o arquivo foi copiado sem preservar seus metadados.
O endpoint aceita upload, não caminhos arbitrários do disco do computador que executa
o backend. O **estado de cada análise fica no backend** (`GET /api/offline/jobs`), então
ele não se perde se o painel desconectar, recarregar ou trocar de aba; o histórico é
mantido enquanto o serviço está em execução. A fila aceita até cinco análises
aguardando ou em execução.

### Configurar e testar integrações pelo painel

1. Abra **Configurações → Alertas e Notificações** (Telegram) ou
   **Configurações → Variáveis de ambiente** (Discord e IA externa).
2. Digite apenas os valores novos. Campo vazio mantém o valor salvo; o painel nunca
   recebe a credencial completa do backend. Para substituir uma chave, digite a nova.
   Use **Remover credenciais salvas** somente se quiser apagá-la.
3. Use **Testar Conexão** para validar os dados. O teste não salva a alteração.
   No Telegram, **Testar Envio de Mensagem** valida o token (`getMe`) e envia uma
   mensagem real de teste ao chat configurado, confirmando o caminho ponta a ponta.
4. Clique em **Salvar Alterações**. O backend atualiza `back\.env` e recarrega as
   configurações em execução; um toast informa sucesso ou erro.

Por segurança, `GET /api/settings/env` devolve somente máscaras fixas e indicadores
de configuração (`*_configured`), nunca os segredos nem seus sufixos. Os endpoints
de leitura, gravação e teste são restritos a conexões locais. Não exponha o backend
diretamente à rede ou à Internet.

Na seção **Alertas e Notificações** ficam o liga/desliga dos alertas e o **modo de
notificação**: `all` avisa a cada visita válida; `new_species` avisa apenas quando a
espécie detectada ainda não consta no catálogo local (a *Life List*). A decisão de
enviar considera ainda o limiar de confiança e o modo configurado, e nunca bloqueia
o pipeline de vídeo — o envio é assíncrono (`NotificationService` + `notifier.py`).

Na seção **Calibração e Ajustes** o usuário escolhe entre dois perfis prontos —
**Passarinhos Parados / Alimentador** (recomendado) e **Alta Movimentação / Voo
Rápido** — ou ajusta manualmente, com sliders explicativos, a *Sensibilidade da
IA*, o *Tempo de permanência imóvel* (3–15 s), a *Sensibilidade de movimento
inicial*, o *Tempo de presença da ave* (`PRESENCE_GRACE_SECONDS`) e o *Intervalo
mínimo entre alertas* (`ALERT_COOLDOWN_SECONDS`) — os dois últimos aplicados ao
vivo no validador de zonas, sem reiniciar as câmeras. O perfil recomendado já vem
**ativo por padrão** (confiança `0.22`, permanência `10 s`, movimento `0.80`),
entregando alta sensibilidade sem ajustes manuais. A **regra anti-spam** (mesma
ave = mesmo evento) atua de forma transparente: enquanto a ave permanece no
comedouro, o Bem-Te-Vi Core segue rastreando, mas não cria novos alertas/registros; um
novo evento só nasce após a ave sair por completo da zona e outra pousar. A mesma
tela traz a **Visão Noturna (Infravermelho)**: modo automático/sempre/desligado, o
limiar de luminosidade e a opção de monitorar a fauna noturna além de aves. Em
**Preferências da IA e
alertas** ficam os limites de notificação, gravação pré/pós-detecção e o
liga/desliga de notificações. Tudo é aplicado em tempo de execução, sem reiniciar
o backend.

### Excluir visitas e limpar o histórico

- Na **Galeria**, use **Excluir registro** no cartão desejado e confirme a ação.
  O registro, snapshot, clipe e recorte associados são removidos do banco e das
  pastas locais de mídia. A interface remove o cartão imediatamente e atualiza
  as estatísticas.
- Em **Configurações → Exclusão e limpeza de dados**, escolha uma idade mínima e
  use **Limpar histórico antigo** para remover visitas e arquivos associados
  anteriores ao limite. Revise e confirme no modal.
- **Esvaziar galeria e histórico** remove todas as visitas e suas mídias locais,
  inclusive arquivos de mídia órfãos nas pastas de snapshots, clipes e recortes.
  Para confirmar essa ação irreversível, digite `EXCLUIR TUDO`.
- Câmeras, zonas, credenciais, configurações e o banco SQLite em si são mantidos;
  a limpeza geral apaga os registros de visitas, não as tabelas nem o arquivo do
  banco. Se algum arquivo não puder ser excluído, o painel informa que houve uma
  falha parcial e os itens afetados permanecem reportados.

---

## Estrutura do projeto

```
Bem-Te-Vi/
├── back/                 # FastAPI + OpenCV + YOLOv8 + SQLite
│   ├── app/
│   │   ├── api/         # Analytics (resumo/distribuição por jardim)
│   │   ├── controllers/  # Rotas REST (inclui audio_detections)
│   │   ├── core/         # Configuração e descoberta do ffmpeg/ffprobe
│   │   ├── domain/       # Modelos e taxonomia da fauna (anti-esquilo)
│   │   ├── infra/        # AI, câmera, DB, mídia
│   │   ├── services/     # Notificações, áudio BirdNET (audio_clips/audio_analysis), .env e IA externa
│   │   └── main.py
│   ├── app-data/         # Banco, capturas, recortes, clipes e áudios (local)
│   ├── requirements.txt
│   └── .env.example
├── front/                # React 19 + Vite + TypeScript + Tailwind
│   ├── src/
│   ├── src-tauri/        # Casca desktop do Bem-Te-Vi Monitor (Tauri 2)
│   └── package.json
├── start.bat             # Sobe uvicorn + vite juntos (Windows)
├── README.md             # Guia do Usuário (uso no dia a dia)
└── README-DEV.md         # Este guia técnico (instalação, arquitetura e API)
```

---

## API local (resumo)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Saúde da API |
| GET/POST | `/api/cameras` | Listar / criar câmeras (cada item inclui `night_mode`, se a visão noturna está ativa) |
| GET/PUT/DELETE | `/api/cameras/{id}` | Detalhe / atualizar / remover. **Excluir arquiva a câmera (soft-delete)**: nada da galeria, dos clipes, das fotos ou dos áudios é apagado — o histórico do jardim é preservado permanentemente |
| GET/PUT | `/api/cameras/{id}/zones` | Carregar / salvar polígonos de inclusão e exclusão |
| GET | `/api/cameras/{id}/weather` | Clima e horário **locais** do jardim da câmera (Open-Meteo; requer coordenadas) |
| GET | `/api/weather/geocode?q=` | Seletor de cidade inteligente: nome → coordenadas + fuso IANA |
| GET | `/api/settings/roi?camera_id={id}` | Ler as Zonas de Interesse (ROI) retangulares da câmera |
| POST | `/api/settings/roi` | Salvar as ROI retangulares (`{camera_id, zones:[{type, x1, y1, x2, y2}]}`) e aplicar em runtime |
| GET | `/api/visits` | Eventos de aves |
| GET | `/api/visits/today` | Visitas de hoje (mais recentes primeiro) |
| GET | `/api/visits/{id}` | Detalhe de uma visita |
| GET | `/api/visits/{id}/crop` | Recorte tratado (close-up) da ave, servido de `app-data/crops/` |
| GET | `/api/visits/{id}/crop/hd` | **Download do recorte HD**: JPEG reescalado/realçado em alta resolução (`Content-Disposition: attachment`) |
| PUT | `/api/visits/{visit_id}/assign-species` | Associar ou desassociar visita a uma espécie (`{"species_id":"..."}`) |
| POST | `/api/visits/{id}/reclassify` | **Reclassificação** (correção humana): aplica a espécie correta, grava o recorte em `app-data/fine_tuning/{espécie}/` + `index.jsonl` e alimenta o aprendizado ativo |
| POST | `/api/visits/{id}/auto-identify` | Reexecutar a auto-associação visual (re-ID contra o Catálogo Local); preserva a curadoria humana |
| POST | `/api/visits/{id}/identify-external` | Identificar sob demanda usando o recorte local da visita |
| POST | `/api/visits/{id}/ask-ai` | Consulta ornitológica profunda na IA externa (ficha formatada; `refresh=true` reconsulta) |
| GET | `/api/species` | Listar o catálogo local de aves |
| POST | `/api/species` | Cadastrar uma espécie (multipart: `common_name`, `scientific_name`, `description`, `reference_image` opcional) |
| GET | `/api/species/{id}/profile` | Ficha técnica da espécie (histórico, horários de pico, temperatura média, clima, notas e status ecológico) |
| POST | `/api/species/{id}/ask-ai` | Consulta ornitológica profunda na IA externa **por espécie** (Minhas Aves / Álbum; `refresh=true` reconsulta) |
| DELETE | `/api/species/{id}` | Excluir espécie e sua foto; preservar visitas sem associação |
| POST | `/api/offline/upload` | Enviar MP4/AVI/MOV/MKV e iniciar a análise offline em background (multipart: `file`, `camera_id`, `recorded_at`) |
| GET | `/api/offline/jobs` | Estado de todas as análises offline (em andamento e concluídas) com progresso, contagem de aves e detecções |
| GET | `/api/offline/jobs/{job_id}` | Estado detalhado de uma análise offline |
| DELETE | `/api/offline/jobs/{job_id}` | Remover do histórico uma análise já finalizada |
| POST | `/api/offline/jobs/clear` | Limpar do histórico todas as análises finalizadas |
| DELETE | `/api/events/{event_id}` | Excluir visita individual e sua mídia local associada |
| DELETE | `/api/events?older_than_days=N` | Excluir visitas anteriores ao limite de dias informado |
| DELETE | `/api/events/all` | Apagar todo o histórico e a mídia; exige confirmação `EXCLUIR TUDO` |
| GET/PUT | `/api/settings` | Configurações persistidas (`notifications_enabled`, `notify_mode`, `min_confidence_notify`, …) |
| GET | `/api/settings/calibration` | Calibração ativa (confiança, permanência, movimento e visão noturna) |
| POST | `/api/settings/calibration` | Atualizar a calibração (perfil, valores e visão noturna/fauna) e aplicar em tempo de execução |
| POST | `/api/settings/test-notification` | Teste Telegram/Discord com as credenciais já salvas |
| GET | `/api/settings/env` | Ler integrações com credenciais mascaradas |
| POST | `/api/settings/env` | Salvar variáveis permitidas no `back/.env` e aplicá-las em runtime |
| POST | `/api/settings/env/test` | Testar credenciais digitadas sem salvá-las (no Telegram envia uma mensagem real) |
| POST | `/api/settings/test-ai` | **Testar Conexão com Gemini**: prompt mínimo, *backoff exponencial* (3 tentativas) em 429/503 e *fallback* automático no `proximo modelo validado (gemini-3.5-flash)` quando o modelo responde 404. Sempre retorna HTTP 200 com `status` (`success`/`warning`/`error`) |
| GET | `/api/stats` | Métricas do painel |
| GET | `/api/analytics/summary?camera_id=` | Visitas de hoje, últimos 7 dias e total; espécie líder, duração média e horário de pico. Com `camera_id`, restringe a um jardim (visão por jardim × consolidada) |
| GET | `/api/analytics/hourly-distribution?camera_id=` | Contagem histórica de visitas para cada hora do dia (00h–23h), consolidada ou de um jardim |
| GET | `/api/analytics/lifelist` | Espécies do catálogo, desbloqueio, primeiro registro, foto, avistagens e status ecológico |
| GET | `/api/analytics/achievements` | Conquistas desbloqueadas e disponíveis |
| GET | `/api/anomalies` | Log de anomalias acústico-visuais (ex.: espécie que reaparece após meses); aceita `limit` e `only_pending` |
| GET | `/api/anomalies/pending-count` | Quantidade de anomalias ainda não reconhecidas (badge do painel) |
| POST | `/api/anomalies/{id}/acknowledge` | Marca uma anomalia como reconhecida |
| GET | `/api/ai/status` | **Bem-Te-Vi Core**: estado do motor (`signature: "Bem-Te-Vi Core v1.0"`), FPS, latência da inferência, inferências hoje/total, detecções, recursos (CPU/RAM), modelo/backend/dispositivo e tempo de atividade |
| GET | `/api/ai/logs?limit=&since_id=` | **Logs cognitivos do Bem-Te-Vi Core**: "pensamentos" em tempo real assinados com `[Bem-Te-Vi Core]` (detecção, nitidez do frame, espécie identificada, auto-calibração por clima, anomalias); `since_id` habilita polling incremental |
| GET | `/api/ai/learning/status` | **Aprendizado ativo**: fila de amostras por espécie, elegibilidade para o fine-tuning, modelo adaptado e última execução |
| POST | `/api/ai/learning/optimize` | Dispara o fine-tuning incremental do Bem-Te-Vi Core com as amostras da fila (roda em segundo plano) |
| GET | `/api/ai/behavioral-prediction?species=&horizon_hours=&limit=` | **Memória comportamental**: probabilidade de pico por espécie nas próximas horas, cruzando horário, temperatura/umidade, clima e sazonalidade. Devolve `highlight` com a frase pronta do card |
| GET | `/api/ai/behavioral-memory` | Resumo dos perfis comportamentais persistidos (dias de histórico, espécies e visitas) |
| POST | `/api/ai/behavioral-memory/refresh` | Reconstrói os perfis comportamentais agora (fora do ciclo automático) |
| GET | `/api/ai/individuals?species_id=&limit=` | **Conhecidos do Jardim**: indivíduos re-identificados por assinatura visual, com avistagens recentes e similaridade |
| GET | `/api/ai/individuals/{id}` | Histórico completo de um indivíduo (visitas, fotos, similaridade, clima e jardim) |
| GET | `/api/ai/visual/status` | Contadores das assinaturas visuais: amostras, indivíduos, recorrentes, modelo e limiar de similaridade |
| POST | `/api/visits/{id}/confirm` | Confirma a detecção (rótulo já associado ou informado no corpo) e enfileira a amostra + assinatura visual |
| GET | `/api/streams` | **Multi-câmera**: estado em tempo real de cada stream (status de conexão, FPS, backend, aves ativas no comedouro, pico de indivíduos e inferências) |
| GET | `/api/streams/proxy/{id}` | **Proxy seguro de vídeo (MJPEG)**: anonimiza a URL e as credenciais da câmera externa — o navegador nunca as vê |
| GET | `/api/analytics/weather-correlation` | Relação entre o clima (chuva/temperatura/vento) e as visitas |
| GET | `/api/analytics/weather-insights` | Insights automáticos cruzando clima e hábitos: faixas de temperatura, chuva × seco, horário no frio × no calor e horário por espécie |
| GET | `/api/analytics/weather-feeding-insights` | **Previsão de alimentação**: cruza a previsão horária (Open-Meteo) de cada jardim com o histórico chuva × seco e devolve titular, detalhe, ação sugerida, tom, confiança e o destaque entre jardins |
| GET | `/api/analytics/garden-radar` | **Radar Global**: todos os jardins com coordenadas — clima local, estado online, estatísticas de hoje, principais espécies e URL do vídeo ao vivo; informa também quantos jardins ficaram sem localização |
| GET | `/api/gallery/rare-moments?days=&limit=` | **Momentos Raros**: curadoria que pontua a nitidez (variância do Laplaciano) e a raridade da espécie, com foto-destaque, grade diversificada e contadores |
| POST | `/api/gallery/rare-moments/refresh` | Força uma varredura imediata das capturas ainda não pontuadas (usado pelo botão "Atualizar curadoria") |
| GET | `/api/gallery/rare-moments/{visit_id}/postcard` | **Foto de postal**: gera na hora um JPEG com moldura elegante, legenda (nome popular/científico), data, jardim e marca d'água Bem-Te-Vi |
| GET | `/api/analytics/timelapses` | Lista os resumos do dia (time-lapses) já gerados |
| POST | `/api/analytics/timelapses/generate` | Gera sob demanda o resumo de um dia (`day` opcional; `force` regera) |
| DELETE | `/api/analytics/timelapses/{arquivo}` | Remove um resumo do dia |
| GET | `/api/audio-detections?limit=30` | Detecções sonoras recentes, confiança e visita visual associada |
| GET | `/api/audio-detections/page?limit=5&offset=` | Página de detecções sonoras para a aba **Detecção Sonora** (blocos de 5, carregamento incremental pelo botão "Ver mais…") |
| GET | `/api/audio-detections/nfc?limit=5&offset=&night_date=` | **Viajantes Noturnos (Migração)**: detecções NFC da janela noturna (flight calls) |
| GET | `/api/audio-detections/status` | Estado da análise BirdNET e câmeras monitoradas |
| GET | `/api/audio-detections/devices` | Dispositivos de áudio de entrada disponíveis (microfones) |
| GET | `/api/audio-detections/{id}/audio` | Clipe de áudio (WAV) da detecção, para o player integrado ao card |
| GET | `/api/audio-detections/{id}/spectrogram` | **Espectrograma** (PNG) do canto, gerado sob demanda com Librosa/Matplotlib e cacheado em `app-data/spectrograms/` |
| PUT | `/api/audio-detections/{id}/identify` | Associação **manual** do canto a uma espécie da Life List (`{"species_id":"..."}`) |
| POST | `/api/audio-detections/{id}/identify-external` | IA externa identifica a espécie pelo **espectrograma** do áudio (`add_to_catalog` opcional) |
| POST | `/api/audio-detections/{id}/ask-ai` | Ficha ornitológica profunda (IA externa) da espécie detectada por som (`refresh=true` reconsulta) |
| DELETE | `/api/audio-detections/{id}` | Remove a detecção sonora (e o clipe de áudio no disco) |
| GET | `/api/journal?date=AAAA-MM-DD&camera_id=` | **Diário de Campo** do dia: clima, coordenadas, espécies, fotos, clipes e texto em pt-BR |
| GET | `/api/journal/export/ebird?date=&camera_id=` | Checklist CSV no **eBird Record Format** (19 colunas, sem cabeçalho, data mês/dia/ano) |
| GET | `/api/journal/export/csv?date=&camera_id=` | Planilha CSV limpa em pt-BR (uma linha por espécie/jardim) |
| GET | `/api/network/feed?days=&limit=` | **Feed Global Bem-Te-Vi**: destaques raros/incomuns locais e de jardins parceiros |
| GET | `/api/network/status` | Estado da rede global (webhook, parceiros e contadores; sem expor token/URLs) |
| POST | `/api/network/webhook` | Recebe um destaque de outra instância; exige `X-Bem-Te-Vi-Token` e `GLOBAL_NETWORK_TOKEN` |
| POST | `/api/media/generate-reel/{visit_id}` | Gera o **Reel vertical (9:16)** da visita (`force` regera) |
| GET | `/api/media/reel/{visit_id}` | Streaming do Reel vertical gerado |
| DELETE | `/api/media/reel/{visit_id}` | Remove o Reel gerado |
| GET | `/api/visits/day/{day}` | Visitas de um dia (`AAAA-MM-DD`) para o Reel do Resumo do Dia |
| GET | `/api/video-feed/{id}?boxes=true` | Stream MJPEG com caixas de detecção (use `boxes=false` para ocultá-las) |
| GET | `/api/video-feed/{id}/snapshot` | Foto atual da câmera |
| GET | `/api/weather/current` | Clima atual no alimentador (temperatura, chuva e vento) |
| GET | `/api/videos/{arquivo}` | Streaming do clipe (MP4/H.264) com suporte a requisições `Range` |
| GET | `/api/videos/timelapse/{arquivo}` | Streaming do resumo do dia (time-lapse) com suporte a `Range` |
| GET | `/captures/...` | Thumbnails e demais mídias estáticas |

A aba **Estatísticas & Conquistas** do painel mostra os hábitos de visita e a Life
List. Um seletor no topo alterna entre **cada jardim** e a **Visão Total
Consolidada**: visitas, horário de pico, distribuição por hora e **espécies
presentes** acompanham o escopo escolhido. Uma espécie é desbloqueada quando uma
visita é associada a ela no catálogo.

> **Nomenclatura:** detecções que o YOLO/BirdNET ainda não nomearam aparecem
> sempre como **"Pássaro Desconhecido"** — nunca "Ave Genérica" nem "Bird" — com
> a **silhueta padrão** do sistema no lugar da foto. Visitantes que não são aves
> (esquilos, gatos…) ficam isolados na aba **Visitantes Especiais** e **não**
> entram na contagem de pássaros.

A seção **Insights Comportamentais & Clima** (`/api/analytics/weather-insights`)
cruza cada visita com a temperatura, a umidade e a condição do tempo gravadas no
momento da captura e monta, automaticamente:

- **faixas de temperatura** (visitas, espécies diferentes, visitas/dia e horário
  médio) — destaca a faixa que atrai mais espécies;
- **chuva × tempo seco** — compara a média de visitas por dia em cada condição;
- **horário no frio × no calor** — horário médio de aparecimento em cada regime
  (o limiar frio/quente é a mediana das temperaturas dos dias observados);
- **horário por espécie** — quanto cada espécie aparece mais cedo ou mais tarde
  conforme a temperatura;
- **cards de resumo inteligente** com frases prontas em pt-BR.

O cálculo usa o **horário local** do computador e exige apenas visitas com dados de
clima; quanto mais capturas, mais confiáveis ficam os insights.

### Previsão de alimentação (`weather_forecast.py` + `weather_insights.py`)

O `WeatherForecastService` estende a mesma chamada Open-Meteo que já busca o clima
atual (`current` + `forecast_hours`) para trazer a **previsão horária** seguinte, sem
requisições extras. A resposta é normalizada em janelas com data/hora local,
temperatura, precipitação, probabilidade de chuva e código WMO, e fica em cache por
coordenada com **trava por chave** (`threading.Lock` por lat/lon) para permitir buscas
paralelas de vários jardins sem serializar chamadas.

O `build_feeding_insight()` recebe o histórico (`weather_visit_rows`) e a previsão e
monta um `FeedingWeatherHighlight`: quando há chuva à frente, calcula o **lift** de
atividade esperado (média de visitas/dia em dias de chuva ÷ dias secos), estima em
quantas horas a chuva chega e escolhe um tom/ícone; sem histórico de chuva, cai em uma
**estimativa inicial** conservadora com confiança declarada. Se nenhuma câmera tiver
coordenadas, o endpoint usa `LATITUDE`/`LONGITUDE` como **Jardim Principal** e agrega
o histórico de todas as câmeras, de modo que o card funciona na instalação padrão. O
endpoint `/api/analytics/weather-feeding-insights` roda os jardins em um
`ThreadPoolExecutor` com orçamento curto e devolve **dados parciais** em caso de
timeout, sem bloquear o painel. Nada disso depende de internet para a captura
continuar.

### Radar Global de Jardins

O `AnalyticsRepository.garden_radar()` agrega, por câmera com coordenadas, o clima
local (via cache do `CameraWeatherService`), o estado online (`CameraManager`), as
visitas/espécies de hoje e o histórico total, além da URL do player ao vivo. O
frontend renderiza um **mapa-múndi em SVG** com a costa de Natural Earth 1:110m
embutida no bundle (`worldMapPath.ts`, projeção equirretangular 1000×500) — funciona
**offline**, sem tiles externos nem dependências novas. O componente
`GardenRadarMap` é carregado por `React.lazy` (chunk próprio) e desenha marcadores
pulsantes proporcionais; ao selecionar um jardim, abre o painel lateral com clima,
vídeo/áudio ao vivo, estatísticas e espécies daquele local.

### Momentos Raros / Fotos de Postal (`rare_moments.py`)

Ao salvar a visita, o melhor quadro calcula a **variância do Laplaciano** e a grava
em `visits.sharpness` (migração v14, com índice). O `RareMomentsService`:

- **pontua** candidatas não avaliadas (`score_pending`) reabrindo a imagem do recorte e
  medindo a nitidez — até 80 por requisição, para resposta rápida;
- **cura** os destaques combinando nitidez normalizada e **raridade** derivada de
  `bird_species.ecological_status` + contagem de avistagens (1–2 = Rara, 3–9 =
  Incomum, 10+ = Comum), limitando a 2 fotos por espécie e depois preenchendo;
- gera o **postal** com Pillow: recorte centralizado, moldura, faixa de legenda
  (nome popular/científico), data/hora **no fuso do jardim**, e marca d'água
  Bem-Te-Vi; usa fontes do sistema (`segoeui`) com fallback para a fonte padrão.

O `RareMomentsWorker` roda em background (`RARE_MOMENTS_SCAN_HOURS`, com atraso
inicial) e o endpoint `POST /api/gallery/rare-moments/refresh` força a varredura sob
demanda. Toda a curadoria é local; nada sai do computador.

### Inteligência adaptativa (`back/app/ai/`)

Três módulos opcionais transformam as correções do dia a dia em aprendizado
contínuo. Todos são tolerantes a falhas: um erro neles nunca interrompe a captura.

**Aprendizado ativo (`active_learning.py`)** — sempre que o usuário associa uma
espécie, confirma uma detecção ou usa a identificação externa, o recorte tratado
da visita é copiado para `back/app-data/training_queue/{espécie}/` e registrado na
tabela `training_samples` (idempotente por `visit_id`). Rótulos genéricos
(`bird`, `Pássaro Desconhecido`, …) são recusados. Em **Configurações →
Bem-Te-Vi Core adaptativo**, o botão *"Otimizar Bem-Te-Vi Core com Novas
Amostras"* monta um dataset `train/val` determinístico e roda um fine-tuning
YOLOv8-cls em segundo plano (`fine_tune_runs`). O `best.pt` é copiado para
`back/app-data/models/bem_te_vi_core.pt` e o classificador do pipeline passa a
usá-lo sem reiniciar o servidor. Requer `ultralytics` + `torch`
(`FINE_TUNE_*` no `.env`).

**Memória comportamental (`behavioral_memory.py`)** — agrega o histórico por
espécie em perfis de hora do dia, temperatura/umidade, condição climática e mês.
O `BehavioralMemoryWorker` reconstrói os perfis a cada
`BEHAVIORAL_REFRESH_MINUTES` e persiste o cache em `app_settings`
(`behavioral_memory_profiles_v1`). O card **Previsão de picos do jardim** mostra,
por exemplo: *"Probabilidade de pico de Beija-Flores nas próximas 2 horas: 85% —
condizente com a umidade e histórico de temperatura"*, com os fatores que
pesaram na conta.

**Assinaturas visuais (`visual_embeddings.py`)** — extrai um vetor normalizado do
recorte (MobileNetV3-Small via `torchvision`, 576-D; fallback OpenCV
HSV/gradientes, 180-D) apenas de fotos nítidas. A similaridade de cosseno é
comparada aos centróides por espécie em `bird_individuals`; acima de
`INDIVIDUAL_MATCH_THRESHOLD` a visita é ligada ao mesmo indivíduo e o centróide é
atualizado incrementalmente. Cada ave recorrente vira um **"Conhecido do
Jardim"**, com histórico individual no painel do Dashboard. Os vetores ficam em
`bird_embedding_samples` como BLOBs `float32` (100% local).

**Associação de espécie (`species_association.py`)** — re-ID **no nível da
espécie**: o mesmo extrator de embeddings é comparado com as fotos de
referência do Catálogo Local (`bird_species.reference_image_path`). A
similaridade de cosseno decide (limiar de 65% por padrão) se a visita recebe o
nome popular da espécie; acima do limiar, o serviço grava o vínculo, o selo
`Identificado pelo Bem-Te-Vi Core` e o status ecológico no metadado da visita.
As referências ficam em cache (invalidado por `(id, caminho, mtime)`) e a
curadoria humana tem sempre prioridade.

**Reclassificação (`fine_tuning.py`)** — a correção feita pelo observador
(“Associação Incorreta / Reclassificar”) grava o recorte tratado em
`app-data/fine_tuning/{espécie}/{visit_id}.jpg` e registra a proveniência em
`app-data/fine_tuning/index.jsonl`. Reclassificar a mesma visita move a
amostra (o arquivo anterior é removido), evitando classes contraditórias. A
fila operacional do fine-tuning automático continua em
`app-data/training_queue/`.

### Capas da documentação (`docs/`)

As imagens do [`README.md`](README.md) são geradas automaticamente em modo
headless (Chrome/Edge), usando o **deep-link por hash** do painel:

```powershell
python docs\capturar-telas.py
```

O script renderiza cada aba (`#dashboard`, `#cameras`, `#gallery`,
`#journal`, `#audio`, `#species`, `#analytics`, `#settings`) e salva o PNG em
`docs/images/`. Para refazer os ícones do aplicativo desktop:

```powershell
python front\src-tauri\icons\generate_icons.py
```

### Bioacústica com BirdNET

A análise sonora pode ser ativada em **Configurações → Preferências da IA e
alertas**. Quando habilitada, o backend extrai blocos mono de três segundos do
áudio das câmeras RTSP/ONVIF habilitadas e os analisa em segundo plano. O
threshold padrão é 70%; detecções acima do valor configurado são salvas como
eventos `AUDIO_DETECTION` no SQLite e associadas à visita visual da mesma câmera
quando houver uma em até 30 segundos.

Para usar esse recurso, instale as dependências Python de `back\requirements.txt`
e um runtime TensorFlow Lite/TensorFlow compatível com a versão de Python
selecionada (o `ai-edge-litert` já vem no `requirements.txt`). O **FFmpeg** é
necessário para capturar o áudio: o sistema procura o executável no `PATH`, nas
pastas do winget e, por fim, usa o binário embutido no pacote `imageio-ffmpeg`.
O modelo BirdNET é inicializado sob demanda; a configuração de análise fica
desativada por padrão.
O painel mostra o motivo quando algum pré-requisito não está disponível. A análise
é executada localmente e não envia áudio para serviços externos.

Credenciais de câmera usam Fernet (chave em `back/app-data/secrets/`). Vídeos e imagens
permanecem locais por padrão; somente a ação explícita de identificação transmite o
recorte daquela visita à OpenAI. Telegram/Discord só recebem alertas se configurados,
respeitando o modo de notificação e o limiar de confiança escolhidos no painel.
Os recortes ficam em `back/app-data/crops/`. O armazenamento é local, mas não substitui
backup: proteja a pasta `back/app-data/` e o arquivo `back/.env`. O catálogo e as fotos
de referência também ficam em `back/app-data/`.

O processamento YOLO roda a cada quatro quadros, usando fluxo óptico nos quadros
intermediários e as zonas poligonais e as ROI retangulares como filtros espaciais.
Por padrão, a inferência é restrita à classe `bird` do COCO (id `14`); quando a
**fauna noturna** está habilitada, ela é expandida para as classes extras
configuradas em `NIGHT_FAUNA_CLASS_IDS` (padrão: gato e cachorro). Antes da
inferência, o módulo de **visão noturna** aplica CLAHE e redução de ruído nos
quadros escuros/IR quando necessário (`NIGHT_VISION_MODE`). Quando a ave para de se mover para se alimentar e o
YOLO perde a detecção, o rastreio mantém a mesma caixa "em espera" pela janela de
`OBJECT_PERSISTENCE_TIME`, de modo que a visita não é reiniciada por uma perda
momentânea. Em cenas sem aves rastreadas, a inferência só roda quando há
movimento suficiente (`MOTION_SENSITIVITY`), com uma verificação periódica de
segurança. A **pré-gravação** mantém em RAM, em um buffer circular
(`collections.deque`, com trava de thread), os três segundos anteriores à
detecção; saídas temporárias da zona de até dez segundos são consideradas a
mesma presença. Snapshots, recortes e clipes vencidos são limpos diariamente
conforme `MEDIA_RETENTION_DAYS`, sem remover registros do SQLite.

Os clipes são gravados sempre em `.mp4`: o OpenCV grava os quadros
(`avc1`/`H264` e, em último caso, `mp4v`) e, logo em seguida, o `ffmpeg` reencoda
o resultado para **H.264** (`yuv420p`, `+faststart`) — o formato que qualquer
navegador reproduz. Sem o `ffmpeg` no `PATH`, o arquivo do OpenCV é mantido (com
aviso no log quando não for H.264). Arquivos inválidos ou corrompidos são
descartados. A reprodução na Galeria usa o endpoint `/api/videos/{arquivo}`, que
responde a requisições `Range` (status `206`) para permitir avançar e rebobinar o
vídeo sem baixá-lo por inteiro.

**Gravação inteligente (pré/pós-evento + melhor quadro).** Ao confirmar uma ave,
o pipeline despeja os três segundos do buffer no clipe e continua gravando mais
três (`POST_RECORD_SECONDS`), totalizando uma janela de ~6 s que começa *antes*
do pouso. Durante a janela, o seletor de melhor quadro
(`app/infra/ai/best_frame.py`) avalia cada detecção e guarda apenas a vencedora,
combinando três sinais: **nitidez** (variância do Laplaciano no recorte da ave),
**confiança** do YOLOv8 e **enquadramento** (proporção ideal da tela). Quadros com
nitidez abaixo de `BEST_FRAME_MIN_SHARPNESS` são **descartados como desfoque de
movimento**; se nenhum quadro da janela passar no corte, usa-se o melhor
disponível (fallback), de modo que a visita nunca fica sem foto. Em seguida, o
módulo de enhancement (`app/infra/ai/enhancement.py`) aplica **CLAHE** e **redução
de ruído leve** (`fastNlMeansDenoisingColored`) nesse quadro e o salva como a
**thumbnail oficial** em alta definição (`ENHANCEMENT_*`). O recorte da ave passa
por um **crop inteligente** (`SMART_CROP_*`): ganha margem de contexto ao redor da
caixa e é ajustado para uma faixa de resolução nítida. Essa foto alimenta a Galeria
e o Álbum de Conquistas (Life List), e é a imagem enviada à IA externa quando o
usuário pede a identificação da espécie. Todo o pós-processamento (ffmpeg +
enhancement) roda em um *thread pool* dedicado, fora do laço de captura, para não
travar a leitura da câmera. A visita expõe no banco as notas do quadro escolhido
(`best_frame_score`, `best_frame_sharpness`, `best_frame_area_ratio`,
`best_frame_confidence`, `best_frame_sharpness_ok`) e o selo `enhanced`.

Os resumos do dia (time-lapse) ficam em `back\app-data\captures\timelapses\` e
**não** são removidos pela política de retenção (`MEDIA_RETENTION_DAYS`); apague-os
manualmente pela aba **Galeria → Resumos do Dia (Time-Lapse)** se quiser liberar
espaço.

---

## Solução de problemas

| Problema | O que fazer |
|----------|-------------|
| `python` não reconhecido | Reinstale o Python marcando “Add to PATH” e abra um terminal novo |
| `npm` não reconhecido | Reinstale o Node.js LTS e abra um terminal novo |
| Porta 8000 ou 5173 em uso | No PowerShell: `Get-NetTCPConnection -LocalPort 8000 -State Listen` e encerre o PID (`Stop-Process -Id <PID> -Force`). Depois rode `start.bat` de novo |
| Front sem dados / 404 nas rotas | Confirme que a API em `:8000` é a do Bem-Te-Vi atual (`/docs` deve listar `/api/visits`, `/api/stats`, `/api/settings`). Outro processo antigo na porta 8000 causa 404 |
| `ModuleNotFoundError` ao iniciar a API | Alguma dependência nova não foi instalada. Rode o `start.bat` de novo (ele reinstala pelo hash do `requirements.txt`) ou `back\venv\Scripts\python.exe -m pip install -r back\requirements.txt` |
| Front sem dados | Confirme http://127.0.0.1:8000/api/health e a janela do backend |
| Identificação externa indisponível | Confira `GEMINI_API_KEY` (ou a chave salva em Configurações), o modelo escolhido (`AI_EXTERNAL_MODEL`) e o acesso de rede ao Google. Um **HTTP 404** indica que o nome do modelo foi gravado com o prefixo `models/` — o backend já o remove automaticamente via `sanitize_model_name`, mas confira o valor salvo. Mensagens de **401/403** significam chave inválida; **429/503** significam instabilidade temporária do Google (o sistema já tenta 3 vezes com *backoff*) |
| Importação de gravação rejeitada | Use MP4, AVI, MOV ou MKV com menos de 2 GB e associe o arquivo a uma câmera cadastrada |
| Análise offline falhou | Confirme se o vídeo abre em outro player e se o modelo YOLO foi carregado; tente exportar novamente o arquivo do cartão |
| Clipe não reproduz na Galeria | Os clipes novos usam H.264 (compatível com navegadores). O Bem-Te-Vi usa o `ffmpeg` do sistema ou o embutido no pacote `imageio-ffmpeg`; se nenhum estiver disponível, instale o `ffmpeg` e coloque-o no `PATH`. Clipes antigos em `mp4v` podem não abrir no player: use **Baixar clipe** |
| Teste de conexão falha | Confirme token/URL e acesso à Internet; os testes não enviam mensagens e usam os valores digitados ou salvos |
| Tela de variáveis retorna 403 | A configuração de segredos só aceita conexões locais; abra o painel local padrão em `127.0.0.1` |
| YOLO / ultralytics lento na 1ª vez | Normal — baixa pesos e dependências na primeira instalação |
| Webcam não abre | Teste outro índice USB (`1`, `2`…) ou feche apps que usam a câmera |

---

## Privacidade e segurança

- Vídeos importados e detecção YOLO são processados localmente; o arquivo importado é apagado após a análise  
- Somente a identificação externa envia a imagem recortada, após ação explícita  
- SQLite, configurações de câmera e mídia em `back/app-data/`  
- Segredos de integração armazenados no `back/.env` do backend; a API nunca os retorna em texto puro  
- Segredos são **mascarados** nas respostas de configuração (ex.: `AIza...****`) e redigidos em logs/erros  
- **Acesso somente local por padrão:** a API responde apenas a conexões do próprio computador
  (loopback). Para expor na rede é preciso definir `ALLOW_REMOTE_ACCESS=true` (idealmente atrás
  de VPN ou proxy reverso com autenticação)  
- Rotas de leitura, gravação e teste das variáveis de ambiente limitadas a conexões locais  
- Cabeçalhos de segurança HTTP (CSP, `X-Frame-Options`, `nosniff` etc.) em todas as respostas  
- Validação do cabeçalho `Host` (`ALLOWED_HOSTS`) contra Host Header Injection  
- Consultas SQLite sempre parametrizadas e caminhos de mídia validados contra *path traversal*  
- Sem telemetria do Bem-Te-Vi  

> A auditoria completa (achados, correções e remediação de histórico do Git) está em
> [`docs/SEGURANCA.md`](docs/SEGURANCA.md).

---

## Etapas do projeto

1. Estrutura e bootstrap  
2. Backend (visão, DB, notificações)  
3. Frontend (painel React)  
4. Integração, `start.bat` e documentação — **atual**
