import {
  Bird,
  BookOpen,
  ChartNoAxesCombined,
  Camera,
  Images,
  LayoutDashboard,
  Settings,
  ShieldCheck,
} from "lucide-react";
import type { AppTab } from "@/types";
import { cn } from "@/utils/cn";

type Props = {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
};

const NAV: Array<{ id: AppTab; label: string; icon: typeof LayoutDashboard }> = [
  { id: "dashboard", label: "Painel", icon: LayoutDashboard },
  { id: "cameras", label: "Câmeras", icon: Camera },
  { id: "gallery", label: "Galeria", icon: Images },
  { id: "species", label: "Minhas Aves", icon: BookOpen },
  {
    id: "analytics",
    label: "Estatísticas & Conquistas",
    icon: ChartNoAxesCombined,
  },
  { id: "settings", label: "Configurações", icon: Settings },
];

export function Sidebar({ activeTab, onTabChange }: Props) {
  return (
    <>
      {/* Desktop */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-dark-700 bg-dark-800 md:flex">
        <BrandBlock />
        <nav className="flex flex-1 flex-col gap-1 px-3" aria-label="Navegação principal">
          {NAV.map((item) => (
            <NavButton
              key={item.id}
              {...item}
              active={activeTab === item.id}
              onClick={() => onTabChange(item.id)}
            />
          ))}
        </nav>
        <LocalBadge />
      </aside>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-40 border-b border-dark-700 bg-dark-800 md:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <BrandBlock compact />
          <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
            100% Local
          </span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2" aria-label="Navegação">
          {NAV.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onTabChange(id)}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium",
                  active
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "text-[var(--color-text-muted)]",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            );
          })}
        </nav>
      </div>
    </>
  );
}

function BrandBlock({ compact = false }: { compact?: boolean }) {
  return (
    <div className={cn("flex items-center gap-3", compact ? "" : "px-5 py-6")}>
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
        <Bird className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div>
        <p className="font-display text-base font-bold tracking-tight text-[var(--color-text-primary)]">
          Bem-Ti-Vi
        </p>
        {!compact ? (
          <p className="text-xs text-[var(--color-text-muted)]">Monitoramento local</p>
        ) : null}
      </div>
    </div>
  );
}

function NavButton({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  id: AppTab;
  label: string;
  icon: typeof LayoutDashboard;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition",
        active
          ? "bg-emerald-500/15 text-emerald-400"
          : "text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
      {label}
    </button>
  );
}

function LocalBadge() {
  return (
    <div className="px-4 pb-5">
      <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        <div>
          <p className="text-xs font-semibold text-emerald-400">100% Local & Seguro</p>
          <p className="mt-1 text-[11px] leading-snug text-[var(--color-text-muted)]">
            Vídeo, IA e banco permanecem nesta máquina. Sem nuvem.
          </p>
        </div>
      </div>
    </div>
  );
}
