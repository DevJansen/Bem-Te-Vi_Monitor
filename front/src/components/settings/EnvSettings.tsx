import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  LoaderCircle,
  MessageCircle,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
} from "lucide-react";
import type {
  AppSettings,
  AudioInputDevices,
  EnvironmentIntegration,
  EnvironmentSettings,
  EnvironmentSettingsUpdate,
} from "@/types";
import type { HistoryDeletionResult } from "@/types";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  deleteAllVisits,
  deleteOlderVisits,
  fetchAudioInputDevices,
  fetchEnvironmentSettings,
  fetchSettings,
  getErrorMessage,
  saveEnvironmentSettings,
  testEnvironmentConnection,
  testGeminiConnection,
  fetchGeminiModels,
  updateSettings,
} from "@/services/api";

type EnvironmentDraft = {
  telegramBotToken: string;
  telegramChatId: string;
  discordWebhookUrl: string;
  /** Chave do Google Gemini (GEMINI_API_KEY). */
  aiExternalApiKey: string;
  /** Modelo Gemini em uso (dropdown fixo, sem texto livre). */
  aiExternalModel: string;
  clearTelegram: boolean;
  clearDiscord: boolean;
  clearAiExternal: boolean;
};

/**
 * Modelos do Google Gemini — nomes oficiais da API.
 *
 * O provedor é único e fixo: **Google Gemini**. O modelo é escolhido em um
 * dropdown simples — sem campos de texto livre, para evitar nomes inválidos
 * (que causariam HTTP 404 na API oficial).
 *
 * **Descoberta dinâmica:** como o Google descontinua modelos com frequência,
 * a lista real disponível para a chave é buscada em `/api/settings/ai/models`.
 * Os presets abaixo são a semente (e o fallback quando a API não responde).
 */
const GEMINI_DEFAULT_MODEL = "gemini-1.5-flash";

const GEMINI_MODEL_PRESETS: Array<{ value: string; label: string }> = [
  {
    value: "gemini-1.5-flash",
    label: "gemini-1.5-flash (Padrão — Rápido, leve e estável)",
  },
  {
    value: "gemini-2.5-flash",
    label: "gemini-2.5-flash (Nova geração Flash)",
  },
  {
    value: "gemini-1.5-pro",
    label: "gemini-1.5-pro (Modo Pro — Análise densa)",
  },
];

/** Rótulos amigáveis para os modelos descobertos pela API. */
function geminiModelLabel(model: string): string {
  const nome = model.toLowerCase();
  if (nome === GEMINI_DEFAULT_MODEL) {
    return "gemini-1.5-flash (Padrão — Rápido, leve e estável)";
  }
  if (nome.includes("flash-lite")) {
    return `${model} (Flash Lite — o mais leve)`;
  }
  if (nome.includes("flash")) {
    return `${model} (Nova geração Flash)`;
  }
  if (nome.includes("pro")) {
    return `${model} (Modo Pro — Análise densa)`;
  }
  return model;
}

/** Texto de ajuda exibido abaixo do seletor de modelo. */
const GEMINI_MODEL_HELP =
  "gemini-1.5-flash: recomendado — rápido, leve e estável. " +
  "gemini-2.5-flash: nova geração Flash. " +
  "gemini-1.5-pro: análise densa (mais lento). " +
  "A lista é atualizada com os modelos disponíveis para a sua chave.";

const EMPTY_DRAFT: EnvironmentDraft = {
  telegramBotToken: "",
  telegramChatId: "",
  discordWebhookUrl: "",
  aiExternalApiKey: "",
  aiExternalModel: GEMINI_DEFAULT_MODEL,
  clearTelegram: false,
  clearDiscord: false,
  clearAiExternal: false,
};

type Props = {
  onSettingsChange?: (settings: AppSettings) => void;
  onHistoryCleared: (cutoff: string | null, failedIds: string[]) => void;
};

export function EnvSettings({ onSettingsChange, onHistoryCleared }: Props) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [environment, setEnvironment] = useState<EnvironmentSettings | null>(null);
  const [draft, setDraft] = useState<EnvironmentDraft>(EMPTY_DRAFT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingEnvironment, setSavingEnvironment] = useState(false);
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState<EnvironmentIntegration | null>(null);
  const [testResult, setTestResult] = useState<{
    integration: EnvironmentIntegration;
    message: string;
    ok: boolean;
  } | null>(null);
  const [retentionDays, setRetentionDays] = useState(30);
  const [audioDevices, setAudioDevices] = useState<AudioInputDevices | null>(null);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [historyCleanup, setHistoryCleanup] = useState<
    { mode: "old"; days: number } | { mode: "all" } | null
  >(null);
  const [cleaningHistory, setCleaningHistory] = useState(false);
  /**
   * Modelos Gemini realmente disponíveis para a chave configurada.
   * Vazio = ainda não consultou (ou a API falhou) → usa os presets oficiais.
   */
  const [apiModels, setApiModels] = useState<string[]>([]);

  // Descoberta dinâmica: o Google descontinua modelos, então buscamos os
  // que realmente respondem para a chave do observador.
  useEffect(() => {
    let ativo = true;
    void fetchGeminiModels()
      .then((modelos) => {
        if (ativo && modelos.length > 0) setApiModels(modelos);
      })
      .catch(() => {
        /* mantém os presets oficiais como fallback */
      });
    return () => {
      ativo = false;
    };
  }, []);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, env] = await Promise.all([
        fetchSettings(),
        fetchEnvironmentSettings(),
      ]);
      setSettings(data);
      setEnvironment(env);
      // Pré-preenche o modelo do Gemini (não é segredo).
      setDraft((current) => ({
        ...current,
        aiExternalModel: env.ai_external_model || GEMINI_DEFAULT_MODEL,
      }));
      onSettingsChange?.(data);
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao carregar configurações"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  // Lista os dispositivos de entrada de áudio quando a análise sonora está ativa.
  const loadAudioDevices = async () => {
    setLoadingDevices(true);
    try {
      setAudioDevices(await fetchAudioInputDevices());
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao listar os dispositivos de áudio"));
    } finally {
      setLoadingDevices(false);
    }
  };

  useEffect(() => {
    if (settings?.audio_analysis_enabled) void loadAudioDevices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.audio_analysis_enabled]);

  useEffect(() => {
    if (!message) return;
    const timeout = window.setTimeout(() => setMessage(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [message]);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateSettings({
        notifications_enabled: settings.notifications_enabled,
        notify_mode: settings.notify_mode,
        audio_analysis_enabled: settings.audio_analysis_enabled,
        audio_confidence_threshold: settings.audio_confidence_threshold,
        audio_input_device: settings.audio_input_device,
        min_confidence_notify: settings.min_confidence_notify,
        pre_record_seconds: settings.pre_record_seconds,
        post_record_seconds: settings.post_record_seconds,
      });
      setSettings(updated);
      onSettingsChange?.(updated);
      setMessage("Configurações salvas localmente.");
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar"));
    } finally {
      setSaving(false);
    }
  };

  const buildEnvironmentPayload = (): EnvironmentSettingsUpdate => ({
    ...(draft.telegramBotToken.trim()
      ? { telegram_bot_token: draft.telegramBotToken.trim() }
      : {}),
    ...(draft.telegramChatId.trim()
      ? { telegram_chat_id: draft.telegramChatId.trim() }
      : {}),
    ...(draft.discordWebhookUrl.trim()
      ? { discord_webhook_url: draft.discordWebhookUrl.trim() }
      : {}),
    ...(draft.aiExternalApiKey.trim()
      ? { ai_external_api_key: draft.aiExternalApiKey.trim() }
      : {}),
    ...(draft.aiExternalModel.trim()
      ? { ai_external_model: draft.aiExternalModel.trim() }
      : {}),
    ...(draft.clearTelegram ? { clear_telegram: true } : {}),
    ...(draft.clearDiscord ? { clear_discord: true } : {}),
    ...(draft.clearAiExternal ? { clear_ai_external: true } : {}),
  });

  const saveEnvironment = async () => {
    setSavingEnvironment(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await saveEnvironmentSettings(buildEnvironmentPayload());
      setEnvironment(updated);
      setDraft(EMPTY_DRAFT);
      setMessage("Variáveis de ambiente salvas e aplicadas.");
      setTestResult(null);
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar as variáveis de ambiente"));
    } finally {
      setSavingEnvironment(false);
    }
  };

  // Salva a seção "Alertas e Notificações": credenciais do Telegram (token/chat)
  // e as preferências (liga/desliga + modo de notificação) de uma só vez.
  const saveAlerts = async () => {
    if (!settings) return;
    setSavingAlerts(true);
    setMessage(null);
    setError(null);
    try {
      const credentials = buildEnvironmentPayload();
      if (Object.keys(credentials).length > 0) {
        const updatedEnv = await saveEnvironmentSettings(credentials);
        setEnvironment(updatedEnv);
        setDraft(EMPTY_DRAFT);
        setTestResult(null);
      }
      const updated = await updateSettings({
        notifications_enabled: settings.notifications_enabled,
        notify_mode: settings.notify_mode,
      });
      setSettings(updated);
      onSettingsChange?.(updated);
      setMessage("Alertas salvos.");
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar os alertas"));
    } finally {
      setSavingAlerts(false);
    }
  };

  const runConnectionTest = async (integration: EnvironmentIntegration) => {
    setTesting(integration);
    setTestResult(null);
    setError(null);
    const credentials: EnvironmentSettingsUpdate = {};
    if (integration === "telegram") {
      if (draft.telegramBotToken.trim()) {
        credentials.telegram_bot_token = draft.telegramBotToken.trim();
      }
      if (draft.telegramChatId.trim()) {
        credentials.telegram_chat_id = draft.telegramChatId.trim();
      }
    } else if (integration === "discord" && draft.discordWebhookUrl.trim()) {
      credentials.discord_webhook_url = draft.discordWebhookUrl.trim();
    } else if (integration === "ai_external") {
      // Rota blindada dedicada ao Gemini: sempre HTTP 200, com `status`
      // (success/warning/error) no corpo — nunca mais o 503 crônico.
      setTesting(integration);
      try {
        const result = await testGeminiConnection(
          draft.aiExternalApiKey.trim() || null,
          draft.aiExternalModel.trim() || GEMINI_DEFAULT_MODEL,
        );
        setTestResult({
          integration,
          message: result.message,
          ok: result.status === "success",
        });
      } catch (err) {
        setTestResult({
          integration,
          message: getErrorMessage(
            err,
            "Não foi possível testar a conexão com o Google Gemini.",
          ),
          ok: false,
        });
      } finally {
        setTesting(null);
      }
      return;
    }
    try {
      const result = await testEnvironmentConnection(integration, credentials);
      setTestResult({ integration, message: result.message, ok: result.ok });
    } catch (err) {
      setTestResult({
        integration,
        message: getErrorMessage(err, "Não foi possível testar a integração"),
        ok: false,
      });
    } finally {
      setTesting(null);
    }
  };

  /**
   * Opções do dropdown de modelo: os presets oficiais + os modelos que a API
   * realmente oferece para a chave configurada (descoberta dinâmica).
   * Se a descoberta falhar, fica só com os presets — nunca quebrado.
   */
  const geminiModelOptions = useMemo(() => {
    const mapa = new Map<string, { value: string; label: string }>();
    // Presets oficiais primeiro (o pedido do observador).
    for (const preset of GEMINI_MODEL_PRESETS) mapa.set(preset.value, preset);
    // Modelos descobertos na API completam a lista.
    for (const modelo of apiModels) {
      if (!mapa.has(modelo)) {
        mapa.set(modelo, { value: modelo, label: geminiModelLabel(modelo) });
      }
    }
    return Array.from(mapa.values());
  }, [apiModels]);

  const cleanHistory = async () => {
    if (!historyCleanup) return;
    const cleanup = historyCleanup;
    setCleaningHistory(true);
    setError(null);
    setMessage(null);
    const cutoff =
      cleanup.mode === "old"
        ? new Date(Date.now() - cleanup.days * 24 * 60 * 60 * 1000).toISOString()
        : null;
    try {
      const result: HistoryDeletionResult =
        cleanup.mode === "all"
          ? await deleteAllVisits()
          : await deleteOlderVisits(cleanup.days);
      onHistoryCleared(cutoff, result.failed_records);
      setHistoryCleanup(null);
      if (result.failed_records.length > 0 || result.failed_media_files.length > 0) {
        setError(
          `${result.deleted_records} registro(s) e ${result.deleted_media_files} mídia(s) removidos. Falhas: ${result.failed_records.length} registro(s) e ${result.failed_media_files.length} arquivo(s) de mídia. Consulte os logs do backend.`,
        );
      } else {
        setMessage(
          `${result.deleted_records} registro(s) e ${result.deleted_media_files} arquivo(s) de mídia excluídos.`,
        );
      }
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao limpar o histórico."));
    } finally {
      setCleaningHistory(false);
    }
  };

  if (loading && !settings) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Carregando configurações…
      </p>
    );
  }

  if (!settings) {
    return (
      <p className="text-sm text-red-300">
        {error ?? "Não foi possível carregar as configurações."}
      </p>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
          Configurações e variáveis de ambiente
        </h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          Configure integrações diretamente no painel. Credenciais existentes são
          mascaradas e não são retornadas em texto aberto.
        </p>
      </div>

      <div className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
        <div className="mb-4">
          <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
            Alertas e Notificações
          </h3>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Receba um aviso no Telegram, com a foto do passarinho, quando ele
            aparecer na câmera.
          </p>
        </div>

        <div className="space-y-5">
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input
              type="checkbox"
              checked={settings.notifications_enabled}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  notifications_enabled: e.target.checked,
                })
              }
              className="accent-emerald-500"
            />
            Alertas habilitados
          </label>

          {settings.notifications_enabled ? (
            <div className="space-y-4 rounded-lg border border-dark-700 bg-dark-900/60 p-4">
              <div>
                <label
                  htmlFor="notify-mode"
                  className="block text-xs font-medium text-[var(--color-text-muted)]"
                >
                  Quando notificar
                </label>
                <select
                  id="notify-mode"
                  value={settings.notify_mode}
                  onChange={(e) =>
                    setSettings({ ...settings, notify_mode: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50"
                >
                  <option value="all">Qualquer visita</option>
                  <option value="new_species">
                    Apenas novas espécies (não estão na Life List)
                  </option>
                </select>
                <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                  {settings.notify_mode === "new_species"
                    ? "Você só será avisado quando aparecer uma ave que ainda não consta no seu catálogo Minhas Aves."
                    : "Você será avisado de toda visita detectada, inclusive de espécies já conhecidas."}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-xs text-[var(--color-text-muted)]">
                  Token do bot do Telegram
                  <span className="mt-1 flex rounded-lg border border-dark-700 bg-dark-900 focus-within:border-emerald-500/50">
                    <input
                      type="password"
                      value={draft.telegramBotToken}
                      placeholder="123456:ABC..."
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          telegramBotToken: e.target.value,
                          clearTelegram: false,
                        })
                      }
                      autoComplete="off"
                      className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
                    />
                  </span>
                </label>
                <label className="block text-xs text-[var(--color-text-muted)]">
                  ID do chat do Telegram
                  <span className="mt-1 flex rounded-lg border border-dark-700 bg-dark-900 focus-within:border-emerald-500/50">
                    <input
                      type="text"
                      value={draft.telegramChatId}
                      placeholder="-1001234567890"
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          telegramChatId: e.target.value,
                          clearTelegram: false,
                        })
                      }
                      autoComplete="off"
                      className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
                    />
                  </span>
                </label>
              </div>

              <div className="flex flex-wrap items-center gap-3 border-t border-dark-700 pt-4">
                <button
                  type="button"
                  onClick={() => void saveAlerts()}
                  disabled={savingAlerts}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
                >
                  {savingAlerts ? "Salvando…" : "Salvar alertas"}
                </button>
                <button
                  type="button"
                  onClick={() => void runConnectionTest("telegram")}
                  disabled={
                    testing !== null ||
                    (!draft.telegramBotToken.trim() &&
                      !environment?.telegram_bot_token_configured)
                  }
                  className="inline-flex items-center gap-2 rounded-lg border border-dark-700 px-4 py-2 text-sm font-medium text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-60"
                >
                  <Send className="h-4 w-4" />
                  {testing === "telegram" ? "Testando…" : "Testar Envio de Mensagem"}
                </button>
                {testResult?.integration === "telegram" ? (
                  <p
                    className={`text-xs ${
                      testResult.ok ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {testResult.message}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {environment ? (
        <div className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
          <div className="mb-4">
            <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Variáveis do arquivo back/.env
            </h3>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              Deixe o campo vazio para manter a chave atual. A limpeza de uma
              credencial é explícita; os valores nunca são enviados de volta pelo GET.
            </p>
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            <IntegrationCard
              title="Discord"
              icon={<MessageCircle className="h-4 w-4" />}
              configured={environment.discord_configured}
              testing={testing === "discord"}
              hasInput={Boolean(draft.discordWebhookUrl.trim())}
              result={testResult?.integration === "discord" ? testResult : null}
              onTest={() => void runConnectionTest("discord")}
              clearRequested={draft.clearDiscord}
              onClearChange={(clearDiscord) =>
                setDraft({ ...draft, clearDiscord })
              }
              fields={[
                {
                  label: "URL do webhook",
                  value: draft.discordWebhookUrl,
                  placeholder: environment.discord_webhook_url_configured
                    ? "Webhook salvo (••••••••)"
                    : "https://discord.com/api/webhooks/...",
                  secret: true,
                  onChange: (discordWebhookUrl) =>
                    setDraft({ ...draft, discordWebhookUrl, clearDiscord: false }),
                },
              ]}
            />
            <IntegrationCard
              title="Inteligência Artificial Externa (Google Gemini)"
              icon={<Sparkles className="h-4 w-4" />}
              configured={environment.ai_external_configured}
              testing={testing === "ai_external"}
              hasInput={Boolean(draft.aiExternalApiKey.trim())}
              result={testResult?.integration === "ai_external" ? testResult : null}
              onTest={() => void runConnectionTest("ai_external")}
              testLabel="Testar Conexão com Gemini"
              clearRequested={draft.clearAiExternal}
              onClearChange={(clearAiExternal) =>
                setDraft({ ...draft, clearAiExternal })
              }
              hint="O Google Gemini é o único provedor de IA do Bem-Ti-Vi. Ele identifica as aves nas fotos, interpreta os espectrogramas dos cantos e monta a ficha ornitológica — tudo local, sem enviar imagens para nenhum outro serviço."
              fields={[
                {
                  label: "Chave da API (GEMINI_API_KEY)",
                  value: draft.aiExternalApiKey,
                  placeholder: environment.ai_external_api_key_configured
                    ? "Chave salva (••••••••)"
                    : "AIzaSy...",
                  secret: true,
                  note: (
                    <>
                      Obtenha sua chave gratuita em{" "}
                      <a
                        href="https://aistudio.google.com"
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-emerald-300 underline underline-offset-2 hover:text-emerald-200"
                      >
                        aistudio.google.com
                      </a>
                    </>
                  ),
                  onChange: (aiExternalApiKey) =>
                    setDraft({ ...draft, aiExternalApiKey, clearAiExternal: false }),
                },
                {
                  label: "Modelo",
                  value: geminiModelOptions.some(
                    (option) => option.value === draft.aiExternalModel,
                  )
                    ? draft.aiExternalModel
                    : (geminiModelOptions[0]?.value ?? GEMINI_DEFAULT_MODEL),
                  placeholder: GEMINI_DEFAULT_MODEL,
                  secret: false,
                  options: geminiModelOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                  })),
                  note: GEMINI_MODEL_HELP,
                  onChange: (aiExternalModel) =>
                    setDraft({ ...draft, aiExternalModel }),
                },
              ]}
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-dark-700 pt-4">
            <button
              type="button"
              onClick={() => void saveEnvironment()}
              disabled={savingEnvironment || testing !== null}
              className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {savingEnvironment ? "Salvando…" : "Salvar Alterações"}
            </button>
            <p className="text-xs text-[var(--color-text-muted)]">
              Aplicação imediata, sem reiniciar o backend.
            </p>
          </div>
        </div>
      ) : null}

      <div className="rounded-xl border border-dark-700 bg-dark-800 p-4">
        <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
          Preferências da IA e alertas
        </h3>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="flex items-start gap-2 text-sm text-[var(--color-text-muted)] sm:col-span-2">
            <input
              type="checkbox"
              checked={settings.audio_analysis_enabled}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  audio_analysis_enabled: e.target.checked,
                })
              }
              className="mt-0.5 accent-emerald-500"
            />
            <span>
              <span className="block text-[var(--color-text-primary)]">
                Ativar detecção sonora com BirdNET
              </span>
              <span className="mt-1 block text-xs">
                Analisa o áudio das câmeras RTSP/ONVIF e de microfones USB em
                segundo plano. Requer FFmpeg e as dependências de bioacústica.
              </span>
            </span>
          </label>

          {settings.audio_analysis_enabled ? (
            <div className="sm:col-span-2">
              <label
                htmlFor="audio-input-device"
                className="block text-xs font-medium text-[var(--color-text-muted)]"
              >
                Dispositivo de áudio (microfone USB/webcam)
              </label>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <select
                  id="audio-input-device"
                  value={settings.audio_input_device}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      audio_input_device: e.target.value,
                    })
                  }
                  className="min-w-56 flex-1 rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50"
                >
                  <option value="">
                    {audioDevices && audioDevices.devices.length > 0
                      ? "Automático (primeiro dispositivo)"
                      : "Nenhum dispositivo detectado"}
                  </option>
                  {(audioDevices?.devices ?? []).map((device) => (
                    <option key={device.name} value={device.name}>
                      {device.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void loadAudioDevices()}
                  disabled={loadingDevices}
                  className="inline-flex items-center gap-2 rounded-lg border border-dark-700 px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-50"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${
                      loadingDevices ? "animate-spin" : ""
                    }`}
                  />
                  Atualizar lista
                </button>
              </div>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Usado pelas câmeras USB. Câmeras RTSP/ONVIF capturam o áudio do
                próprio stream.
                {audioDevices
                  ? ` Plataforma detectada: ${audioDevices.platform}.`
                  : ""}
              </p>
            </div>
          ) : null}
          <NumberField
            label="Confiança mínima do BirdNET (%)"
            value={Math.round(settings.audio_confidence_threshold * 100)}
            min={70}
            max={100}
            step={5}
            onChange={(v) =>
              setSettings({
                ...settings,
                audio_confidence_threshold: v / 100,
              })
            }
          />

          <NumberField
            label="Confiança mínima para notificar"
            value={settings.min_confidence_notify}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => setSettings({ ...settings, min_confidence_notify: v })}
          />
          <NumberField
            label="Pré-gravação (s)"
            value={settings.pre_record_seconds}
            min={3}
            max={30}
            step={1}
            onChange={(v) => setSettings({ ...settings, pre_record_seconds: v })}
          />
          <NumberField
            label="Pós-gravação (s)"
            value={settings.post_record_seconds}
            min={0}
            max={30}
            step={0.5}
            onChange={(v) => setSettings({ ...settings, post_record_seconds: v })}
          />
        </div>

        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          A sensibilidade do YOLO e o tempo de permanência das aves imóveis agora
          ficam na seção{" "}
          <strong className="text-[var(--color-text-primary)]">
            Calibração e Ajustes
          </strong>
          , com perfis prontos e controles explicativos.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 hover:bg-emerald-400 disabled:opacity-60"
          >
            {saving ? "Salvando…" : "Salvar preferências"}
          </button>
          <p className="text-xs text-[var(--color-text-muted)]">
            Modelo ativo: <span className="text-emerald-400">{settings.yolo_model}</span>
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-red-500/20 bg-dark-800 p-4 sm:p-5">
        <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
          Exclusão e limpeza de dados
        </h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          Remove os registros selecionados do SQLite e apaga snapshots, clipes e
          recortes locais associados.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Excluir visitas com mais de
            <span className="mt-1 flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={36500}
                value={retentionDays}
                onChange={(event) =>
                  setRetentionDays(
                    Math.min(36500, Math.max(1, Number(event.target.value) || 1)),
                  )
                }
                className="w-24 rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-red-400/50"
              />
              dias
            </span>
          </label>
          <button
            type="button"
            onClick={() => setHistoryCleanup({ mode: "old", days: retentionDays })}
            disabled={cleaningHistory}
            className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm font-medium text-amber-200 transition hover:bg-amber-500/10 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Limpar histórico antigo
          </button>
          <button
            type="button"
            onClick={() => setHistoryCleanup({ mode: "all" })}
            disabled={cleaningHistory}
            className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-400 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Esvaziar galeria e histórico
          </button>
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-dark-700 bg-dark-800/80 px-3 py-3 text-xs text-[var(--color-text-muted)]">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        Os testes de conexão validam os valores digitados sem salvar nem enviar mensagens.
        As chaves são aplicadas em tempo de execução após salvar.
      </div>

      {message ? (
        <p role="status" className="fixed bottom-5 right-5 z-50 rounded-lg border border-emerald-500/30 bg-emerald-950 px-4 py-3 text-sm text-emerald-300 shadow-xl">
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border border-red-500/30 bg-red-950 px-4 py-3 text-sm text-red-300 shadow-xl">
          {error}
        </p>
      ) : null}
      <ConfirmDialog
        open={historyCleanup !== null}
        title={
          historyCleanup?.mode === "all"
            ? "Esvaziar todo o histórico?"
            : "Limpar histórico antigo?"
        }
        message={
          historyCleanup?.mode === "all"
            ? "Todos os registros de visitas e suas mídias locais serão removidos permanentemente."
            : `Os registros com mais de ${historyCleanup?.days ?? retentionDays} dias e suas mídias serão removidos permanentemente.`
        }
        confirmLabel={
          historyCleanup?.mode === "all" ? "Esvaziar tudo" : "Limpar histórico"
        }
        requiredText={historyCleanup?.mode === "all" ? "EXCLUIR TUDO" : undefined}
        busy={cleaningHistory}
        onCancel={() => setHistoryCleanup(null)}
        onConfirm={() => void cleanHistory()}
      />
    </section>
  );
}

type EnvironmentFieldProps = {
  label: string;
  value: string;
  placeholder: string;
  secret: boolean;
  onChange: (value: string) => void;
  /** Opções fixas: quando presentes, o campo vira um <select>. */
  options?: { value: string; label: string }[];
  /** Sugestões: campo de texto livre com lista de sugestões (datalist). */
  suggestions?: string[];
  /** Campo somente-leitura (ex.: URL fixa do Google Gemini). */
  disabled?: boolean;
  /** Texto auxiliar exibido abaixo do campo. */
  note?: ReactNode;
};

function EnvironmentField({
  label,
  value,
  placeholder,
  secret,
  onChange,
  options,
  suggestions,
  disabled = false,
  note,
}: EnvironmentFieldProps) {
  const [visible, setVisible] = useState(false);
  const listId = useId();

  if (options) {
    return (
      <label className="block text-xs text-[var(--color-text-muted)]">
        {label}
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="mt-1 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="block text-xs text-[var(--color-text-muted)]">
      {label}
      <span
        className={`mt-1 flex rounded-lg border border-dark-700 bg-dark-900 focus-within:border-emerald-500/50 ${
          disabled ? "opacity-60" : ""
        }`}
      >
        <input
          type={secret && !visible ? "password" : "text"}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          autoComplete="off"
          disabled={disabled}
          list={suggestions && suggestions.length > 0 ? listId : undefined}
          className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] disabled:cursor-not-allowed"
        />
        {suggestions && suggestions.length > 0 ? (
          <datalist id={listId}>
            {suggestions.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        ) : null}
        {secret ? (
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            aria-label={visible ? `Ocultar ${label}` : `Mostrar ${label}`}
            className="px-3 text-[var(--color-text-muted)] hover:text-emerald-300"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        ) : null}
      </span>
      {note ? (
        <span className="mt-1 block text-[10px] leading-snug text-[var(--color-text-muted)]">
          {note}
        </span>
      ) : null}
    </label>
  );
}

function IntegrationCard({
  title,
  icon,
  configured,
  testing,
  hasInput,
  result,
  onTest,
  clearRequested,
  onClearChange,
  fields,
  hint,
  testLabel,
}: {
  title: string;
  icon: ReactNode;
  configured: boolean;
  testing: boolean;
  hasInput: boolean;
  result: { message: string; ok: boolean } | null;
  onTest: () => void;
  clearRequested: boolean;
  onClearChange: (clear: boolean) => void;
  fields: EnvironmentFieldProps[];
  hint?: string;
  /** Rótulo do botão de teste (padrão: "Testar Conexão"). */
  testLabel?: string;
}) {
  return (
    <div className="space-y-3 rounded-xl border border-dark-700 bg-dark-900/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[var(--color-text-primary)]">
          <span className="text-emerald-400">{icon}</span>
          <h4 className="font-display text-sm font-semibold">{title}</h4>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ${configured ? "bg-emerald-500/15 text-emerald-400" : "bg-dark-700 text-[var(--color-text-muted)]"}`}>
          {configured ? (
            <>
              <CheckCircle2 className="h-3 w-3" /> Configurado
            </>
          ) : (
            "Não configurado"
          )}
        </span>
      </div>
      {hint ? (
        <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
          {hint}
        </p>
      ) : null}
      {fields.map((field) => (
        <EnvironmentField key={field.label} {...field} />
      ))}
      {configured ? (
        <label className="flex items-center gap-2 text-[11px] text-red-300">
          <input
            type="checkbox"
            checked={clearRequested}
            onChange={(event) => onClearChange(event.target.checked)}
            className="accent-red-500"
          />
          Remover credenciais salvas
        </label>
      ) : null}
      <button
        type="button"
        disabled={testing || (!configured && !hasInput) || clearRequested}
        onClick={onTest}
        className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {testing ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : null}
        {testing ? "Testando conexão…" : (testLabel ?? "Testar Conexão")}
      </button>
      {result ? (
        <p
          role={result.ok ? "status" : "alert"}
          className={`text-xs ${result.ok ? "text-emerald-300" : "text-red-300"}`}
        >
          {result.message}
        </p>
      ) : null}
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block text-xs text-[var(--color-text-muted)]">
      {label}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50"
      />
    </label>
  );
}
