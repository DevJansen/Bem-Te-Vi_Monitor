# AviaWatch

Sistema **local** de monitoramento de avifauna por IA.

O AviaWatch recebe vídeo de câmeras USB, RTSP ou ONVIF, detecta aves com YOLOv8 e
registra visitas em SQLite. O painel web permite desenhar zonas de inclusão e
exclusão por câmera, consultar snapshots e clipes e, opcionalmente, pedir a
identificação de uma ave a uma API externa. Alertas pelo Telegram e Discord também
são opcionais. O processamento e os arquivos permanecem locais por padrão.

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
| `AI_EXTERNAL_API_KEY` | Identificação opcional de espécies | Chave da API OpenAI; necessária somente para identificação externa |
| `AI_EXTERNAL_MODEL` | Modelo compatível com visão | Padrão: `gpt-4o-mini` |
| `PORT` | Porta configurada na aplicação | Padrão: `8000`; os comandos de inicialização fornecidos usam a porta `8000` |
| `YOLO_MODEL` | Arquivo/modelo de detecção | Padrão: `yolov8n.pt` |
| `YOLO_CONFIDENCE` | Sensibilidade da detecção (menor = mais sensível) | Padrão: `0.30`; faixa: `0.05` a `1.0` |
| `OBJECT_PERSISTENCE_TIME` | Tempo (s) que o rastreio mantém a visita com a ave imóvel | Padrão: `5.0`; faixa: `0` a `30` |
| `MOTION_SENSITIVITY` | Sensibilidade de detecção de movimento inicial | Padrão: `0.5`; faixa: `0` a `1` |
| `YOLO_BIRD_CLASS_ID` | Classe do COCO usada na inferência | Padrão: `14` (`bird`) |
| `PRE_RECORD_SECONDS` | Duração anterior à detecção incluída no clipe | Padrão/mínimo: `3.0` |
| `POST_RECORD_SECONDS` | Duração posterior à detecção | Padrão: `2.0` |
| `CAMERA_RECONNECT_DELAY_SEC` | Intervalo de reconexão da câmera | Padrão: `3.0` |
| `MEDIA_RETENTION_DAYS` | Retenção de mídia local | Padrão: `30`; mínimo: `1` |
| `APP_DATA_DIR` | Diretório para banco, mídia e segredos de câmera | Opcional; padrão: `back\app-data` |

O painel administra os quatro segredos de integração (Telegram, ID do chat, Discord
e IA Externa). `AI_EXTERNAL_MODEL` e as demais opções avançadas continuam sendo
ajustadas no arquivo `.env`; alterações manuais nesse arquivo exigem reiniciar o
backend.

### Onde obter as credenciais

- **Telegram:** crie um bot com o `@BotFather` e guarde o token recebido. Inicie
  uma conversa com o bot ou adicione-o ao grupo/canal de alertas; informe o ID
  correspondente em `TELEGRAM_CHAT_ID`.
- **Discord:** nas configurações do servidor/canal, crie um webhook em
  **Integrações → Webhooks** e guarde a URL completa em `DISCORD_WEBHOOK_URL`.
- **IA externa:** crie uma chave de API na plataforma OpenAI e configure uso/
  faturamento da API conforme necessário. Guarde-a em `AI_EXTERNAL_API_KEY`.
  Escolha em `AI_EXTERNAL_MODEL` um modelo disponível para sua conta e com suporte
  a imagens.

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
2. Abra a aba **Câmeras** e, em **Importar gravação / cartão de memória**, escolha
   a câmera à qual as visitas devem ser associadas.
3. Selecione um arquivo `.mp4`, `.avi` ou `.mkv` de até 2 GB. É preciso cadastrar
   uma câmera antes: as zonas dessa câmera são usadas para filtrar as detecções.
4. Acompanhe o envio e depois o progresso da análise. O backend percorre os quadros
   localmente com YOLOv8, aplica as zonas de inclusão/exclusão e registra uma visita
   quando a presença atende ao tempo mínimo configurado para a zona.
5. Ao concluir, a aplicação atualiza a Galeria e abre o histórico com as visitas e
   thumbnails encontradas. O snapshot é extraído do quadro que confirmou a visita;
   o vídeo importado temporariamente é apagado ao terminar.

O horário de cada evento é estimado somando a posição temporal do quadro no vídeo
à data de última modificação do arquivo, enviada pelo navegador. Essa data pode não
corresponder ao horário original se o arquivo foi copiado sem preservar seus metadados.
O endpoint aceita upload, não caminhos arbitrários do disco do computador que executa
o backend. Uma análise em andamento e seu progresso ficam na memória do backend e não
são restaurados se o serviço for reiniciado. A fila aceita até cinco análises
aguardando ou em execução.

### Configurar e testar integrações pelo painel

1. Abra **Configurações → Variáveis de ambiente**.
2. Digite apenas os valores novos. Campo vazio mantém o valor salvo; o painel nunca
   recebe a credencial completa do backend. Para substituir uma chave, digite a nova.
   Use **Remover credenciais salvas** somente se quiser apagá-la.
3. Use **Testar Conexão** para validar os dados. O teste não salva a alteração nem
   envia uma mensagem de teste.
4. Clique em **Salvar Alterações**. O backend atualiza `back\.env` e recarrega as
   configurações em execução; um toast informa sucesso ou erro.

Por segurança, `GET /api/settings/env` devolve somente máscaras fixas e indicadores
de configuração (`*_configured`), nunca os segredos nem seus sufixos. Os endpoints
de leitura, gravação e teste são restritos a conexões locais. Não exponha o backend
diretamente à rede ou à Internet.

Na seção **Calibração e Ajustes** o usuário escolhe entre dois perfis prontos —
**Passarinhos Parados / Alimentador** (recomendado) e **Alta Movimentação / Voo
Rápido** — ou ajusta manualmente, com sliders explicativos, a *Sensibilidade da
IA*, o *Tempo de permanência imóvel* (3–15 s) e a *Sensibilidade de movimento
inicial*. Em **Preferências da IA e alertas** ficam os limites de notificação,
gravação pré/pós-detecção e o liga/desliga de notificações. Tudo é aplicado em
tempo de execução, sem reiniciar o backend.

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
│   │   ├── services/     # Notificações, áudio BirdNET, .env e identificação externa
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
| GET/POST | `/api/cameras` | Listar / criar câmeras |
| GET/PUT/DELETE | `/api/cameras/{id}` | Detalhe / atualizar / remover |
| GET/PUT | `/api/cameras/{id}/zones` | Carregar / salvar polígonos de inclusão e exclusão |
| GET | `/api/settings/roi?camera_id={id}` | Ler as Zonas de Interesse (ROI) retangulares da câmera |
| POST | `/api/settings/roi` | Salvar as ROI retangulares (`{camera_id, zones:[{type, x1, y1, x2, y2}]}`) e aplicar em runtime |
| GET | `/api/visits` | Eventos de aves |
| GET | `/api/visits/{id}` | Detalhe de uma visita |
| PUT | `/api/visits/{visit_id}/assign-species` | Associar ou desassociar visita a uma espécie (`{"species_id":"..."}`) |
| POST | `/api/visits/{id}/identify-external` | Identificar sob demanda usando o recorte local da visita |
| GET | `/api/species` | Listar o catálogo local de aves |
| POST | `/api/species` | Cadastrar uma espécie (multipart: `common_name`, `scientific_name`, `description`, `reference_image` opcional) |
| DELETE | `/api/species/{id}` | Excluir espécie e sua foto; preservar visitas sem associação |
| POST | `/api/recordings/import` | Enviar MP4/AVI/MKV e iniciar análise offline (multipart: `file`, `camera_id`, `recorded_at`) |
| GET | `/api/recordings/{analysis_id}` | Consultar status e progresso da análise em segundo plano |
| DELETE | `/api/events/{event_id}` | Excluir visita individual e sua mídia local associada |
| DELETE | `/api/events?older_than_days=N` | Excluir visitas anteriores ao limite de dias informado |
| DELETE | `/api/events/all` | Apagar todo o histórico e a mídia; exige confirmação `EXCLUIR TUDO` |
| GET/PUT | `/api/settings` | Configurações persistidas |
| GET | `/api/settings/calibration` | Calibração de sensibilidade ativa (confiança, permanência e movimento) |
| POST | `/api/settings/calibration` | Atualizar a calibração e aplicar em tempo de execução (perfil ou valores) |
| POST | `/api/settings/test-notification` | Teste Telegram/Discord |
| GET | `/api/settings/env` | Ler integrações com credenciais mascaradas |
| POST | `/api/settings/env` | Salvar variáveis permitidas no `back/.env` e aplicá-las em runtime |
| POST | `/api/settings/env/test` | Testar credenciais digitadas sem salvá-las |
| GET | `/api/stats` | Métricas do painel |
| GET | `/api/analytics/summary` | Visitas de hoje, últimos 7 dias e total; espécie líder, duração média e horário de pico |
| GET | `/api/analytics/hourly-distribution` | Contagem histórica de visitas para cada hora do dia (00h–23h) |
| GET | `/api/analytics/lifelist` | Espécies do catálogo, desbloqueio, primeiro registro, foto e número de avistagens |
| GET | `/api/audio-detections?limit=30` | Detecções sonoras recentes, confiança e visita visual associada |
| GET | `/api/audio-detections/status` | Estado da análise BirdNET e câmeras monitoradas |
| GET | `/api/video-feed/{id}?boxes=true` | Stream MJPEG com caixas de detecção (use `boxes=false` para ocultá-las) |
| GET | `/api/videos/{arquivo}` | Streaming do clipe (MP4/H.264) com suporte a requisições `Range` |
| GET | `/captures/...` | Thumbnails e demais mídias estáticas |

A aba **Estatísticas & Conquistas** do painel mostra os hábitos de visita e a Life
List. Uma espécie é desbloqueada quando uma visita é associada a ela no catálogo;
o gráfico agrupa as visitas de todo o histórico por hora do dia.

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
recorte daquela visita à OpenAI. Telegram/Discord só recebem alertas se configurados.
Os recortes ficam em `back/app-data/crops/`. O armazenamento é local, mas não substitui
backup: proteja a pasta `back/app-data/` e o arquivo `back/.env`. O catálogo e as fotos
de referência também ficam em `back/app-data/`.

O processamento YOLO roda a cada quatro quadros, usando fluxo óptico nos quadros
intermediários e as zonas poligonais e as ROI retangulares como filtros espaciais.
A inferência é restrita à classe `bird` do COCO (id `14`). Quando a ave para de se mover para se alimentar e o
YOLO perde a detecção, o rastreio mantém a mesma caixa "em espera" pela janela de
`OBJECT_PERSISTENCE_TIME`, de modo que a visita não é reiniciada por uma perda
momentânea. Em cenas sem aves rastreadas, a inferência só roda quando há
movimento suficiente (`MOTION_SENSITIVITY`), com uma verificação periódica de
segurança. A pré-gravação inclui os três segundos anteriores à detecção;
saídas temporárias da zona de até dez segundos são consideradas a mesma presença.
Snapshots, recortes e clipes vencidos são limpos diariamente conforme
`MEDIA_RETENTION_DAYS`, sem remover registros do SQLite.

Os clipes são gravados sempre em `.mp4`: o OpenCV grava os quadros
(`avc1`/`H264` e, em último caso, `mp4v`) e, logo em seguida, o `ffmpeg` reencoda
o resultado para **H.264** (`yuv420p`, `+faststart`) — o formato que qualquer
navegador reproduz. Sem o `ffmpeg` no `PATH`, o arquivo do OpenCV é mantido (com
aviso no log quando não for H.264). Arquivos inválidos ou corrompidos são
descartados. A reprodução na Galeria usa o endpoint `/api/videos/{arquivo}`, que
responde a requisições `Range` (status `206`) para permitir avançar e rebobinar o
vídeo sem baixá-lo por inteiro.

---

## Solução de problemas

| Problema | O que fazer |
|----------|-------------|
| `python` não reconhecido | Reinstale o Python marcando “Add to PATH” e abra um terminal novo |
| `npm` não reconhecido | Reinstale o Node.js LTS e abra um terminal novo |
| Porta 8000 ou 5173 em uso | No PowerShell: `Get-NetTCPConnection -LocalPort 8000 -State Listen` e encerre o PID (`Stop-Process -Id <PID> -Force`). Depois rode `start.bat` de novo |
| Front sem dados / 404 nas rotas | Confirme que a API em `:8000` é a do AviaWatch atual (`/docs` deve listar `/api/visits`, `/api/stats`, `/api/settings`). Outro processo antigo na porta 8000 causa 404 |
| Front sem dados | Confirme http://127.0.0.1:8000/api/health e a janela do backend |
| Identificação externa indisponível | Confira `AI_EXTERNAL_API_KEY`, o modelo com suporte a visão e o acesso de rede à API OpenAI |
| Importação de gravação rejeitada | Use MP4, AVI ou MKV com menos de 2 GB e associe o arquivo a uma câmera cadastrada |
| Análise offline falhou | Confirme se o vídeo abre em outro player e se o modelo YOLO foi carregado; tente exportar novamente o arquivo do cartão |
| Clipe não reproduz na Galeria | Os clipes novos usam H.264 (compatível com navegadores). Instale o `ffmpeg` e coloque-o no `PATH` para garantir a melhor compatibilidade. Clipes antigos em `mp4v` podem não abrir no player: use **Baixar clipe** |
| Teste de conexão falha | Confirme token/URL e acesso à Internet; os testes não enviam mensagens e usam os valores digitados ou salvos |
| Tela de variáveis retorna 403 | A configuração de segredos só aceita conexões locais; abra o painel local padrão em `127.0.0.1` |
| YOLO / ultralytics lento na 1ª vez | Normal — baixa pesos e dependências na primeira instalação |
| Webcam não abre | Teste outro índice USB (`1`, `2`…) ou feche apps que usam a câmera |

---

## Privacidade

- Vídeos importados e detecção YOLO são processados localmente; o arquivo importado é apagado após a análise  
- Somente a identificação externa envia a imagem recortada, após ação explícita  
- SQLite, configurações de câmera e mídia em `back/app-data/`  
- Segredos de integração armazenados no `back/.env` do backend; a API nunca os retorna em texto puro  
- Rotas de leitura, gravação e teste das variáveis de ambiente limitadas a conexões locais  
- Sem telemetria do AviaWatch  

---

## Etapas do projeto

1. Estrutura e bootstrap  
2. Backend (visão, DB, notificações)  
3. Frontend (painel React)  
4. Integração, `start.bat` e documentação — **atual**
