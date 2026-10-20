import { useState } from "react";
import {
  Brain,
  Camera,
  Settings2,
  Shield,
} from "lucide-react";
import { cn } from "@/utils/cn";
import { CalibrationPanel } from "@/components/settings/CalibrationPanel";
import { ActiveLearningPanel } from "@/components/settings/ActiveLearningPanel";
import { SmartAlertsPanel } from "@/components/settings/SmartAlertsPanel";
import { EnvSettings } from "@/components/settings/EnvSettings";

type SettingsTabId = "general" | "ai" | "cameras" | "integrations";

const TABS: Array<{
  id: SettingsTabId;
  label: string;
  icon: typeof Settings2;
  description: string;
}> = [
  {
    id: "general",
    label: "Geral / Sistema",
    icon: Settings2,
    description: "Fuso horário, retenção de mídias e preferências gerais",
  },
  {
    id: "ai",
    label: "Inteligência Artificial",
    icon: Brain,
    description: "Chave do Gemini, token iNaturalist, sensibilidade do YOLO",
  },
  {
    id: "cameras",
    label: "Câmeras & Áudio",
    icon: Camera,
    description: "Configurações RTSP, zonas, BirdNET e áudio",
  },
  {
    id: "integrations",
    label: "Integrações & Alertas",
    icon: Shield,
    description: "Telegram, Webhooks, regras preditivas e alertas",
  },
];

export function SettingsTabs({ onHistoryCleared }: { onHistoryCleared: (cutoff: string | null, failedIds: string[]) => void }) {
  const [activeTab, setActiveTab] = useState<SettingsTabId>("general");

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      {/* Navegação lateral (desktop) / horizontal (mobile) */}
      <nav
        aria-label="Abas de configurações"
        className="flex shrink-0 gap-2 overflow-x-auto rounded-xl border border-dark-700 bg-dark-800 p-2 lg:w-64 lg:flex-col lg:overflow-visible"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition-all duration-200",
                active
                  ? "bg-emerald-500/15 text-emerald-300 shadow-[0_0_0_1px_rgba(16,185,129,0.3)]"
                  : "text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <span className="block truncate">{tab.label}</span>
                <span className="block truncate text-[10px] font-normal text-[var(--color-text-muted)]">
                  {tab.description}
                </span>
              </div>
            </button>
          );
        })}
      </nav>

      {/* Conteúdo da aba ativa com transição suave */}
      <div className="min-w-0 flex-1">
        {activeTab === "general" ? (
          <div className="animate-fade-in space-y-6">
            <EnvSettings onHistoryCleared={onHistoryCleared} />
          </div>
        ) : null}
        {activeTab === "ai" ? (
          <div className="animate-fade-in space-y-6">
            <CalibrationPanel />
            <ActiveLearningPanel />
          </div>
        ) : null}
        {activeTab === "cameras" ? (
          <div className="animate-fade-in space-y-6">
            <EnvSettings onHistoryCleared={onHistoryCleared} />
          </div>
        ) : null}
        {activeTab === "integrations" ? (
          <div className="animate-fade-in space-y-6">
            <SmartAlertsPanel />
            <EnvSettings onHistoryCleared={onHistoryCleared} />
          </div>
        ) : null}
      </div>
    </div>
  );
}