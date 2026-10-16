# AviaWatch

Sistema **local** de monitoramento de avifauna por IA.

O AviaWatch recebe vídeo de câmeras USB, RTSP ou ONVIF, detecta aves com YOLOv8 e
registra visitas em SQLite. O painel web permite desenhar zonas de inclusão e
exclusão por câmera, consultar snapshots e clipes e, opcionalmente, pedir a
identificação de uma ave a uma API externa. Alertas pelo Telegram e Discord também
são opcionais. O processamento e os arquivos permanecem locais por padrão.

> **Quer entender como usar sem precisar programar?** Leia o
> [**Guia do Usuário (README-USO.md)**](README-USO.md) — explica todas as funcionalidades
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

---

## Instalação e execução rápida (Windows) — `start.bat`

O jeito mais simples de subir o AviaWatch:

### Passo 1 — Abrir a pasta do projeto

No Explorador de Arquivos, vá até a pasta `aviawatch` (onde estão `start.bat`, `back\` e `front\`).

### Passo 2 — (Opcional) Configurar integrações

1. Copie `back\.env.example` para `back\.env` (o `start.bat` também faz isso automaticamente se o `.env` não existir).
2. Edite `back\.env` se quiser Telegram/Discord ou identificação por IA externa:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=
AI_EXTERNAL_API_KEY=
AI_EXTERNAL_BASE_URL=https://api.openai.com/v1
AI_EXTERNAL_MODEL=gpt-4o-mini
PORT=8000
```

Deixe os campos vazios para manter Telegram, Discord ou identificação externa
desabilitados. As integrações também podem ser configuradas depois em
**Configurações → Variáveis de ambiente**.

> **Proteja o arquivo:** não compartilhe nem publique `back\.env`. Não cole tokens
> em chamados, capturas de tela ou commits. O arquivo contém segredos e deve ficar
> apenas na máquina que executa o backend.

O backend usa confiança YOLO de `0.30` (sensibilidade maior, ideal para aves
distantes ou paradas), tempo de permanência de `5` segundos para aves imóveis,
sensibilidade de movimento de `0.5`, mantém pelo menos `3` segundos de
pré-gravação e remove clipes, snapshots e recortes locais com mais de 30 dias.
Esses padrões podem ser ajustados no `back\.env` (`YOLO_CONFIDENCE`,
`OBJECT_PERSISTENCE_TIME`, `MOTION_SENSITIVITY`, `PRE_RECORD_SECONDS` e
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
| `AI_EXTERNAL_API_KEY` | Identificação opcional de espécies | Chave do provedor de IA; necessária somente para identificação externa |
| `AI_EXTERNAL_BASE_URL` | URL base do provedor de IA (compatível com OpenAI) | Padrão: `https://api.openai.com/v1`. Aceita OpenRouter, Groq, Ollama, Gemini etc. |
| `AI_EXTERNAL_MODEL` | Modelo compatível com visão | Padrão: `gpt-4o-mini` |
| `PORT` | Porta configurada na aplicação | Padrão: `8000`; os comandos de inicialização fornecidos usam a porta `8000` |
| `YOLO_MODEL` | Arquivo/modelo de detecção | Padrão: `yolov8n.pt` |
| `YOLO_CONFIDENCE` | Sensibilidade da detecção (menor = mais sensível) | Padrão: `0.30`; faixa: `0.05` a `1.0` |
| `OBJECT_PERSISTENCE_TIME` | Tempo (s) que o rastreio mantém a visita com a ave imóvel | Padrão: `5.0`; faixa: `0` a `30` |
| `MOTION_SENSITIVITY` | Sensibilidade de detecção de movimento inicial | Padrão: `0.5`; faixa: `0` a `1` |
| `YOLO_BIRD_CLASS_ID` | Classe do COCO usada na inferência | Padrão: `14` (`bird`) |
| `PRE_RECORD_SECONDS` | Duração anterior à detecção incluída no clipe | Padrão/mínimo: `3.0` |
| `POST_RECORD_SECONDS` | Duração posterior à detecção | Padrão: `3.0` (com o pré-roll, o clipe cobre ~6 s) |
| `CAMERA_RECONNECT_DELAY_SEC` | Intervalo de reconexão da câmera | Padrão: `3.0` |
| `MEDIA_RETENTION_DAYS` | Retenção de mídia local | Padrão: `30`; mínimo: `1` |
| `APP_DATA_DIR` | Diretório para banco, mídia e segredos de câmera | Opcional; padrão: `back\app-data` |
| `LATITUDE` | Latitude do alimentador (usada pela integração meteorológica) | Padrão: `-23.5505` (São Paulo/SP) |
| `LONGITUDE` | Longitude do alimentador (usada pela integração meteorológica) | Padrão: `-46.6333` (São Paulo/SP) |
| `WEATHER_CACHE_MINUTES` | Intervalo (min) de atualização do cache local de clima | Padrão: `30`; mínimo: `5` |
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
| `ENHANCEMENT_ENABLED` | Melhoria automática (CLAHE + redução de ruído) da foto oficial | Padrão: `true` |
| `ENHANCEMENT_CLAHE_CLIP` | Intensidade do CLAHE na foto tratada | Padrão: `2.0`; faixa: `1.0` a `8.0` |
| `ENHANCEMENT_CLAHE_GRID` | Grade do CLAHE (blocos por lado) na foto tratada | Padrão: `8`; faixa: `2` a `16` |
| `ENHANCEMENT_DENOISE` | Redução de ruído leve (não-linear) na foto tratada | Padrão: `true` |
| `ENHANCEMENT_DENOISE_STRENGTH` | Força da redução de ruído | Padrão: `5.0`; faixa: `0` a `20` |
| `ENHANCEMENT_MAX_WIDTH` | Largura máxima (px) da foto tratada (limita o custo do denoise) | Padrão: `1280`; faixa: `320` a `4096` |
| `ENHANCEMENT_MIN_WIDTH` | Largura mínima (px) da foto tratada (garante "alta definição") | Padrão: `720`; faixa: `0` a `4096` |
| `ENHANCEMENT_JPEG_QUALITY` | Qualidade JPEG da foto tratada | Padrão: `95`; faixa: `50` a `100` |
| `ALLOW_REMOTE_ACCESS` | Libera acesso à API fora do computador local | Padrão: `false` (somente loopback). Use `true` só com VPN/proxy autenticado |
| `ALLOWED_HOSTS` | Hosts aceitos no cabeçalho `Host` | Padrão: `127.0.0.1,localhost` |

O painel administra a integração de IA Externa por completo (chave, URL base e
modelo), os segredos do Telegram e do Discord, e as preferências de alerta. A
seção **Alertas e Notificações** permite ligar/desligar os avisos, escolher o modo
(`all` ou `new_species`), informar token e chat do Telegram e disparar um teste de
envio real. As demais opções avançadas continuam sendo ajustadas no arquivo `.env`;
alterações manuais nesse arquivo exigem reiniciar o backend.

### Onde obter as credenciais

- **Telegram:** crie um bot com o `@BotFather` e guarde o token recebido. Inicie
  uma conversa com o bot ou adicione-o ao grupo/canal de alertas; informe o ID
  correspondente em `TELEGRAM_CHAT_ID`.
- **Discord:** nas configurações do servidor/canal, crie um webhook em
  **Integrações → Webhooks** e guarde a URL completa em `DISCORD_WEBHOOK_URL`.
- **IA externa:** use a chave do provedor de sua preferência. O AviaWatch aceita
  qualquer API compatível com a de chat da OpenAI: a própria OpenAI, OpenRouter,
  Groq, Ollama (local) ou o endpoint OpenAI-compatível do Gemini. Configure a
  chave em `AI_EXTERNAL_API_KEY`, a URL em `AI_EXTERNAL_BASE_URL` e, em
  `AI_EXTERNAL_MODEL`, um modelo do provedor com suporte a imagens. Também é
  possível preencher tudo pela tela **Configurações → Variáveis de ambiente**.

Tokens de bot, URL de webhook e chaves de API funcionam como senhas: qualquer pessoa
que os obtenha pode usar a integração associada. Revogue e gere uma nova credencial
se houver suspeita de exposição.

### Passo 3 — Executar o `start.bat`

Dê um duplo clique em `start.bat`, ou no Prompt:

```bat
cd caminho\para\aviawatch
start.bat
```

O script irá, nesta ordem:

1. Verificar se Python e Node.js estão no PATH  
2. Criar o ambiente virtual em `back\venv` (se ainda não existir)  
3. Instalar as dependências Python (`back\requirements.txt`)  
4. Instalar as dependências Node (`front\package.json`)  
5. **Iniciar ao mesmo tempo:**
   - **Backend:** `uvicorn` em `http://127.0.0.1:8000`
   - **Frontend:** `vite` em `http://127.0.0.1:5173`
6. Aguardar o health-check da API e exibir os endereços

Duas janelas de console serão abertas:

- `AviaWatch Backend`
- `AviaWatch Frontend`

### Passo 4 — Abrir o painel

O `start.bat` tenta abrir o navegador sozinho. Se não abrir, use:

- **Painel (use este):** http://127.0.0.1:5173  
- **API / docs:** http://127.0.0.1:8000/docs  

> **Atenção:** a porta **8000** é só a API. O aplicativo visual é a porta **5173**.  
> Se você abrir `http://127.0.0.1:8000` e achar que “não rodou”, troque para `http://127.0.0.1:5173`.

### Passo 5 — Encerrar

Feche as janelas `AviaWatch Backend` e `AviaWatch Frontend`, ou pressione `Ctrl+C` em cada uma.

> Na **primeira execução**, o download do modelo YOLO (`yolov8n.pt`) e dos pacotes Python/Node pode demorar vários minutos.

---

## Instalação manual (alternativa)

Use estes passos se preferir não usar o `start.bat`.

### Backend (Python)

```bat
cd aviawatch\back
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A API fica em http://127.0.0.1:8000 — docs em http://127.0.0.1:8000/docs

### Frontend (Node.js)

Em **outro** terminal:

```bat
cd aviawatch\front
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

Se o painel mostrar “Não foi possível conectar à API”, confirme se a janela **AviaWatch Backend** está aberta e sem erros.

---

## Funcionalidades e como usar

### Cadastrar câmeras

1. Abra o painel → aba **Câmeras** → **Nova câmera**.
2. Para uma webcam, escolha tipo `USB` e URI `0`.
3. Para uma câmera IP, escolha `RTSP` ou `ONVIF` e informe endereço e, se necessário,
   usuário e senha.

As credenciais de câmeras IP são armazenadas criptografadas localmente com Fernet.
O estado aparece no painel como conectado, reconectando ou offline.

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
- A identificação é opcional e depende de `AI_EXTERNAL_API_KEY`. Somente ao clicar
  nesse botão, o recorte local da ave é enviado por HTTPS à API OpenAI configurada
  (`AI_EXTERNAL_MODEL`). A visita atualizada fica registrada no banco local.

Se não houver recorte disponível ou chave configurada, a API informa o erro. Os
recortes ficam em `back\app-data\crops\` e seguem a política de retenção de mídia.

### Montar resumos do dia (time-lapse)

O AviaWatch junta os clipes de um dia em um único vídeo acelerado — o **Resumo do
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
`/api/videos/timelapse/{arquivo}`, com suporte a `Range`. Sem o `ffmpeg` instalado,
a geração fica indisponível (com aviso no log) e o restante do sistema segue normal.

### Monitorar 24 horas com visão noturna (infravermelho)

O AviaWatch continua enxergando no escuro. Quando a luminosidade cai (ou a
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

O catálogo fica na tabela `bird_species` do SQLite, com imagens em
`back\app-data\reference_birds\`. A associação de visitas usa `species_id`; ela é
opcional e não altera a detecção automática do YOLO. Use a Galeria para revisar e
associar manualmente as detecções com as espécies conhecidas.

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
IA*, o *Tempo de permanência imóvel* (3–15 s) e a *Sensibilidade de movimento
inicial*. A mesma tela traz a **Visão Noturna (Infravermelho)**: modo
automático/sempre/desligado, o limiar de luminosidade e a opção de monitorar a
fauna noturna além de aves. Em **Preferências da IA e alertas** ficam os limites de
notificação, gravação pré/pós-detecção e o liga/desliga de notificações. Tudo é
aplicado em tempo de execução, sem reiniciar o backend.

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
aviawatch/
├── back/                 # FastAPI + OpenCV + YOLOv8 + SQLite
│   ├── app/
│   │   ├── api/         # Analytics
│   │   ├── controllers/  # Rotas REST
│   │   ├── core/         # Configuração
│   │   ├── domain/       # Modelos
│   │   ├── infra/        # AI, câmera, DB, mídia
│   │   ├── services/     # Notificações (notifier/NotificationService), áudio BirdNET, .env e identificação externa
│   │   └── main.py
│   ├── app-data/         # Banco, capturas e segredos (local)
│   ├── requirements.txt
│   └── .env.example
├── front/                # React 19 + Vite + TypeScript + Tailwind
│   ├── src/
│   └── package.json
├── start.bat             # Sobe uvicorn + vite juntos (Windows)
└── README.md
```

---

## API local (resumo)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Saúde da API |
| GET/POST | `/api/cameras` | Listar / criar câmeras (cada item inclui `night_mode`, se a visão noturna está ativa) |
| GET/PUT/DELETE | `/api/cameras/{id}` | Detalhe / atualizar / remover |
| GET/PUT | `/api/cameras/{id}/zones` | Carregar / salvar polígonos de inclusão e exclusão |
| GET | `/api/settings/roi?camera_id={id}` | Ler as Zonas de Interesse (ROI) retangulares da câmera |
| POST | `/api/settings/roi` | Salvar as ROI retangulares (`{camera_id, zones:[{type, x1, y1, x2, y2}]}`) e aplicar em runtime |
| GET | `/api/visits` | Eventos de aves |
| GET | `/api/visits/today` | Visitas de hoje (mais recentes primeiro) |
| GET | `/api/visits/{id}` | Detalhe de uma visita |
| PUT | `/api/visits/{visit_id}/assign-species` | Associar ou desassociar visita a uma espécie (`{"species_id":"..."}`) |
| POST | `/api/visits/{id}/identify-external` | Identificar sob demanda usando o recorte local da visita |
| GET | `/api/species` | Listar o catálogo local de aves |
| POST | `/api/species` | Cadastrar uma espécie (multipart: `common_name`, `scientific_name`, `description`, `reference_image` opcional) |
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
| GET | `/api/stats` | Métricas do painel |
| GET | `/api/analytics/summary` | Visitas de hoje, últimos 7 dias e total; espécie líder, duração média e horário de pico |
| GET | `/api/analytics/hourly-distribution` | Contagem histórica de visitas para cada hora do dia (00h–23h) |
| GET | `/api/analytics/lifelist` | Espécies do catálogo, desbloqueio, primeiro registro, foto e número de avistagens |
| GET | `/api/analytics/achievements` | Conquistas desbloqueadas e disponíveis |
| GET | `/api/analytics/weather-correlation` | Relação entre o clima (chuva/temperatura/vento) e as visitas |
| GET | `/api/analytics/weather-insights` | Insights automáticos cruzando clima e hábitos: faixas de temperatura, chuva × seco, horário no frio × no calor e horário por espécie |
| GET | `/api/analytics/timelapses` | Lista os resumos do dia (time-lapses) já gerados |
| POST | `/api/analytics/timelapses/generate` | Gera sob demanda o resumo de um dia (`day` opcional; `force` regera) |
| DELETE | `/api/analytics/timelapses/{arquivo}` | Remove um resumo do dia |
| GET | `/api/audio-detections?limit=30` | Detecções sonoras recentes, confiança e visita visual associada |
| GET | `/api/audio-detections/status` | Estado da análise BirdNET e câmeras monitoradas |
| GET | `/api/audio-detections/devices` | Dispositivos de áudio de entrada disponíveis (microfones) |
| GET | `/api/video-feed/{id}?boxes=true` | Stream MJPEG com caixas de detecção (use `boxes=false` para ocultá-las) |
| GET | `/api/video-feed/{id}/snapshot` | Foto atual da câmera |
| GET | `/api/weather/current` | Clima atual no alimentador (temperatura, chuva e vento) |
| GET | `/api/videos/{arquivo}` | Streaming do clipe (MP4/H.264) com suporte a requisições `Range` |
| GET | `/api/videos/timelapse/{arquivo}` | Streaming do resumo do dia (time-lapse) com suporte a `Range` |
| GET | `/captures/...` | Thumbnails e demais mídias estáticas |

A aba **Estatísticas & Conquistas** do painel mostra os hábitos de visita e a Life
List. Uma espécie é desbloqueada quando uma visita é associada a ela no catálogo;
o gráfico agrupa as visitas de todo o histórico por hora do dia.

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

### Bioacústica com BirdNET

A análise sonora pode ser ativada em **Configurações → Preferências da IA e
alertas**. Quando habilitada, o backend extrai blocos mono de três segundos do
áudio das câmeras RTSP/ONVIF habilitadas e os analisa em segundo plano. O
threshold padrão é 70%; detecções acima do valor configurado são salvas como
eventos `AUDIO_DETECTION` no SQLite e associadas à visita visual da mesma câmera
quando houver uma em até 30 segundos.

Para usar esse recurso, instale as dependências Python de `back\requirements.txt`,
disponibilize o executável **FFmpeg** no `PATH` e instale um runtime TensorFlow
Lite/TensorFlow compatível com a versão de Python selecionada. O modelo BirdNET é
inicializado sob demanda; a configuração de análise fica desativada por padrão.
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
**confiança** do YOLOv8 e **enquadramento** (proporção ideal da tela). Em
seguida, o módulo de enhancement (`app/infra/ai/enhancement.py`) aplica **CLAHE**
e **redução de ruído leve** (`fastNlMeansDenoisingColored`) nesse quadro e o salva
como a **thumbnail oficial** em alta definição (`ENHANCEMENT_*`), além do recorte
da ave. Essa foto alimenta a Galeria e o Álbum de Conquistas (Life List). Todo o
pós-processamento (ffmpeg + enhancement) roda em um *thread pool* dedicado, fora
do laço de captura, para não travar a leitura da câmera. A visita expõe no banco
as notas do quadro escolhido (`best_frame_score`, `best_frame_sharpness`,
`best_frame_area_ratio`, `best_frame_confidence`) e o selo `enhanced`.

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
| Front sem dados / 404 nas rotas | Confirme que a API em `:8000` é a do AviaWatch atual (`/docs` deve listar `/api/visits`, `/api/stats`, `/api/settings`). Outro processo antigo na porta 8000 causa 404 |
| Front sem dados | Confirme http://127.0.0.1:8000/api/health e a janela do backend |
| Identificação externa indisponível | Confira `AI_EXTERNAL_API_KEY`, `AI_EXTERNAL_BASE_URL`, o modelo com suporte a visão e o acesso de rede ao provedor escolhido |
| Importação de gravação rejeitada | Use MP4, AVI, MOV ou MKV com menos de 2 GB e associe o arquivo a uma câmera cadastrada |
| Análise offline falhou | Confirme se o vídeo abre em outro player e se o modelo YOLO foi carregado; tente exportar novamente o arquivo do cartão |
| Clipe não reproduz na Galeria | Os clipes novos usam H.264 (compatível com navegadores). Instale o `ffmpeg` e coloque-o no `PATH` para garantir a melhor compatibilidade. Clipes antigos em `mp4v` podem não abrir no player: use **Baixar clipe** |
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
- Sem telemetria do AviaWatch  

> A auditoria completa (achados, correções e remediação de histórico do Git) está em
> [`docs/SEGURANCA.md`](docs/SEGURANCA.md).

---

## Etapas do projeto

1. Estrutura e bootstrap  
2. Backend (visão, DB, notificações)  
3. Frontend (painel React)  
4. Integração, `start.bat` e documentação — **atual**
