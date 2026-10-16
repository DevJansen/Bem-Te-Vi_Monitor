# AviaWatch — Relatório de Auditoria de Segurança e Proteção de Dados

**Escopo:** Backend (FastAPI + YOLOv8 + SQLite) e Frontend (React + Vite).
**Foco:** Gestão de segredos, higiene do Git, OWASP Top 10 e conformidade com
LGPD (Lei 13.709/2018) e GDPR.
**Data:** 2026-10-15.

---

## 1. Resumo executivo

A auditoria revisou 100% dos pontos de entrada da API, o tratamento de segredos,
a camada de acesso a dados (SQLite) e os pontos que servem arquivos ao navegador.

**Ponto crítico encontrado e tratado:** arquivos sensíveis (banco de dados,
mídia de capturas e a **chave de criptografia de credenciais de câmera**) foram
versionados por engano no commit inicial `f133209` e, embora tenham sido
removidos do rastreamento no commit `430ae66`, **permanecem no histórico do Git**.
Isso exige reescrita de histórico (Seção 5) — e a chave já foi rotacionada pelo
mantenedor, o que é o correto.

As correções de código desta rodada **já estão aplicadas** no repositório:

- Mascaramento estrito de segredos (`AIza...****`) nas respostas de configuração.
- Redação de segredos em mensagens de erro de provedores externos.
- `.gitignore` endurecido (bloqueia `.env*`, `*.db`, logs, mídia e gravações).
- Cabeçalhos de segurança HTTP em todas as respostas.
- Bloqueio de acesso remoto por padrão (somente loopback) + validação de `Host`.

Nenhuma credencial *hardcoded* foi encontrada no código-fonte.

---

## 2. Metodologia

- Inspeção estática do código (`git grep`, revisão manual dos controladores e serviços).
- Análise de histórico do Git (`git log --diff-filter=A`).
- Verificação de padrões de query SQL e de resolução de caminhos de arquivo.
- Testes de execução locais (importação do app, mascaramento, compilação).

---

## 3. Achados por pilar

### Pilar 1 — Gestão de Segredos e Chaves de API

| # | Achado | Severidade | Situação |
|---|--------|-----------|----------|
| 1.1 | Nenhuma credencial *hardcoded* no backend/frontend | — | ✅ Conforme |
| 1.2 | Credenciais carregadas via `os.getenv` + `python-dotenv` | — | ✅ Conforme |
| 1.3 | Mascaramento era total (`********`), sem dica visual | Baixa | ✅ Corrigido |
| 1.4 | Erros de provedor externo podiam ecoar a chave | Média | ✅ Corrigido |
| 1.5 | Segredos não aparecem em logs do servidor | — | ✅ Conforme |

**Evidências e correções**

- `back/app/core/redaction.py` (novo): `mask_secret`, `mask_url_secret`,
  `is_masked` e `redact_secrets`. Exibe apenas o prefixo (`AIza...****`).
- `back/app/services/environment_settings.py`: passa a mascarar token do
  Telegram, chat ID, chave de IA e **URL de webhook do Discord** (mantendo só o
  host). O salvamento reconhece a máscara e **não grava o valor mascarado por
  cima do segredo real**.
- `back/app/services/external_species_identifier.py` e `environment_settings.py`:
  `redact_secrets(...)` remove a chave de qualquer mensagem de erro antes de
  exibir/logar.

### Pilar 2 — Higiene do Git e Prevenção de Vazamentos

| # | Achado | Severidade | Situação |
|---|--------|-----------|----------|
| 2.1 | `.gitignore` não bloqueava `.env.local`/`.env.production` | Alta | ✅ Corrigido |
| 2.2 | `.gitignore` sem `*.db`, logs, `media/`, `recordings/` | Média | ✅ Corrigido |
| 2.3 | Banco, mídia e **chave Fernet** no histórico do Git | **Crítica** | ⚠️ Requer reescrita (Seção 5) |

**2.1 / 2.2 — `.gitignore` endurecido** (raiz do projeto):

```
.env
.env.*
**/.env
**/.env.*
!.env.example
!**/.env.example
back/*env
front/*env
...
*.db
*.db-wal
*.db-shm
*.sqlite
*.sqlite3
*.log
logs/
media/
recordings/
back/app-data/*
!back/app-data/.gitkeep
```

> O `.env.example` (modelo **sem valores reais**) continua versionado de propósito.

**2.3 — Vazamento no histórico.** Foram commitados em `f133209`:

```
back/app-data/aviawatch.db (+ -wal, -shm)
back/app-data/calibration.json
back/app-data/captures/clips/*.mp4
back/app-data/captures/thumbs/*.jpg
back/app-data/crops/*.jpg
back/app-data/secrets/camera_key.fernet   <-- chave de criptografia!
```

Estado atual: apenas `back/app-data/.gitkeep` está rastreado (a remoção ocorreu
em `430ae66`). **O conteúdo, porém, continua recuperável em `f133209`.**

Impacto LGPD/GDPR: as capturas podem conter **dados pessoais** (pessoas no
quintal, rotina da residência) e a chave Fernet permitia **decriptar as
credenciais de câmeras** daquele banco. A chave já foi rotacionada; ainda assim,
o histórico deve ser limpo.

### Pilar 3 — Vulnerabilidades e OWASP Top 10

| # | Achado | Severidade | Situação |
|---|--------|-----------|----------|
| 3.1 | Path Traversal em vídeos/recortes | — | ✅ Já protegido |
| 3.2 | SQL Injection nas queries SQLite | — | ✅ Já protegido |
| 3.3 | CORS com `allow_origins=["*"]` | — | ✅ Não ocorre |
| 3.4 | Ausência de cabeçalhos de segurança | Média | ✅ Corrigido |
| 3.5 | Rotas administrativas sem controle de acesso por padrão | Alta | ✅ Corrigido |
| 3.6 | Sem validação de `Host` (Host Header Injection) | Média | ✅ Corrigido |
| 3.7 | Uploads sem validação de tipo/tamanho | — | ✅ Já protegido |
| 3.8 | Ausência de sinks de XSS no frontend | — | ✅ Conforme |

**3.1 — Path Traversal.** `back/app/controllers/videos.py` usa
`filename != Path(filename).name`, rejeita `/`, `\`, `.`, `..`, valida a extensão
e confere que o caminho resolvido está **diretamente** dentro da pasta de clipes
(`candidate.parent != clips_dir`). O mesmo padrão aparece em `visits.py` (recorte
de visita) e `recordings.py`/`species.py` (nome gerado por UUID). Conforme.

**3.2 — SQL Injection.** Todas as consultas usam parâmetros (`?`). Não há
interpolação de string em SQL (`git grep` de `execute(f...`/`.format`/`%` retornou
zero ocorrências). Conforme.

**3.3 — CORS.** `main.py` lista apenas origens locais (`localhost/127.0.0.1` nas
portas 5173 e 3000). Não há `*`. Conforme.

**3.4 — Cabeçalhos de segurança** (novo `back/app/core/security_middleware.py`):
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Permissions-Policy` restritiva,
`Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` e
`Content-Security-Policy`. Implementado em **ASGI puro** para não quebrar o
streaming MJPEG de `/api/video-feed`.

**3.5 — Controle de acesso.** Antes, apenas as rotas de `.env` eram restritas ao
loopback; as demais dependiam só do bind em `127.0.0.1`. Agora há
`LocalAccessGuardMiddleware`: por padrão **toda** a API responde somente a
conexões locais; qualquer origem externa recebe `403`, exceto os *health checks*
(`/health`, `/api/health`) e a raiz. Para expor na rede, é obrigatório definir
`ALLOW_REMOTE_ACCESS=true` (conscientemente). As rotas de `.env` continuam
**sempre** restritas ao loopback (defesa em profundidade).

**3.6 — Host Header.** `TrustedHostMiddleware` com `ALLOWED_HOSTS`
(padrão `127.0.0.1,localhost`) rejeita cabeçalhos `Host` não autorizados.

**3.7 — Uploads.** `recordings.py`: extensão em allowlist (`.mp4/.avi/.mkv`),
limite de 2 GB, nome gerado por UUID. `species.py`: limite de 8 MB, decodificação
real da imagem via OpenCV antes de salvar. Conforme.

**3.8 — XSS.** Não há `dangerouslySetInnerHTML`, `innerHTML`, `eval` ou
`document.write` no frontend. Conforme.

---

## 4. Arquivos alterados nesta auditoria

| Arquivo | Mudança |
|---------|---------|
| `.gitignore` | Bloqueio de `.env*`, `*.db`, logs, `media/`, `recordings/` |
| `back/app/core/redaction.py` | **Novo** — mascaramento/redação de segredos |
| `back/app/core/security_middleware.py` | **Novo** — cabeçalhos e guarda de acesso local |
| `back/app/core/config.py` | `ALLOW_REMOTE_ACCESS`, `ALLOWED_HOSTS` |
| `back/app/main.py` | Middlewares de segurança e `TrustedHost` |
| `back/app/services/environment_settings.py` | Mascaramento estrito + redação |
| `back/app/services/external_species_identifier.py` | Redação de segredos em erros |
| `back/.env.example` | Documenta as novas variáveis |
| `docs/SEGURANCA.md` | Este relatório |

---

## 5. Remediação do histórico do Git (ação necessária)

> **Faça um backup antes.** Estes comandos reescrevem o histórico e exigem
> `push --force`. Quem mais tiver clonado o repositório deve **apagar o clone e
> clonar de novo** depois.

### 5.1. Opção recomendada — `git filter-repo`

```bash
# Instale: pip install git-filter-repo
git filter-repo --path back/app-data --invert-paths
git push origin --force --all
git push origin --force --tags
```

### 5.2. Alternativa sem instalar ferramentas — `git filter-branch`

```bash
git filter-branch --force --index-filter \
  "git rm -r --cached --ignore-unmatch back/app-data" \
  --prune-empty --tag-name-filter cat -- --all

# Limpeza dos objetos órfãos
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

git push origin --force --all
git push origin --force --tags
```

### 5.3. Alternativa — BFG Repo-Cleaner

```bash
java -jar bfg.jar --delete-folders app-data --no-blob-protection .git
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push origin --force --all
```

### 5.4. Verificação pós-limpeza

```bash
# Não deve retornar nada:
git log --all --oneline -- back/app-data
git rev-list --objects --all | grep app-data
```

### 5.5. Rotação de credenciais (obrigatório se já houve exposição)

1. **Chave Fernet** (`camera_key.fernet`): já rotacionada em `430ae66`. Apague o
   arquivo atual e **recadastre as credenciais das câmeras** para gerar um novo
   par chave/segredo.
2. **Telegram / Discord / IA externa:** se qualquer valor real chegou a ser
   commitado, gere novos tokens/keys e invalide os antigos.
3. Confirme que `back/.env` **nunca** foi versionado (verificado: apenas
   `back/.env.example` consta no histórico, sem valores reais).

---

## 6. Recomendações operacionais (LGPD/GDPR)

1. **Minimização e retenção:** manter `MEDIA_RETENTION_DAYS` ajustado; a mídia é
   dado pessoal potencial. O worker de retenção já existe — revise o prazo.
2. **Base legal e transparência:** sinalize a área monitorada. Capturas de
   pessoas exigem base legal (segurança patrimonial) e aviso adequado.
3. **Criptografia em repouso:** o SQLite não é cifrado por padrão; para dados
   sensíveis, considere disco cifrado (BitLocker/LUKS) na máquina do usuário.
4. **Acesso:** mantenha `ALLOW_REMOTE_ACCESS=false`. Se precisar de acesso
   remoto, use VPN ou proxy reverso com autenticação e TLS.
5. **Backups:** ao exportar `app-data`, proteja o pacote (contém mídia e banco).
6. **Dependências:** rode `pip-audit`/`npm audit` periodicamente.
7. **Direitos do titular:** garanta meios de localizar e apagar mídia por período
   (a retenção e a Galeria já permitem exclusão).

---

## 7. Checklist de conformidade

- [x] Segredos fora do código-fonte (env + dotenv).
- [x] Mascaramento de segredos em respostas e logs.
- [x] `.gitignore` bloqueando segredos, banco, logs e mídia.
- [ ] Histórico do Git limpo (**ação pendente — Seção 5**).
- [x] SQL parametrizado.
- [x] Proteção contra Path Traversal.
- [x] CORS restrito.
- [x] Cabeçalhos de segurança HTTP.
- [x] Controle de acesso (somente local por padrão).
- [x] Validação de `Host`.
- [x] Uploads validados.
- [x] Chave de credenciais rotacionada após exposição.
