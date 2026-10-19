import { useEffect, useState } from "react";
import { AudioLines, Film, Images, Sparkles, Squirrel } from "lucide-react";
import type { BirdSpecies, BirdVisit } from "@/types";
import { GalleryGrid } from "@/components/gallery/GalleryGrid";
import { RareMomentsGallery } from "@/components/gallery/RareMomentsGallery";
import { TimelapseGallery } from "@/components/gallery/TimelapseGallery";
import { AudioDetectionPanel } from "@/components/audio/AudioDetectionPanel";
import { cn } from "@/utils/cn";

type Props = {
  visits: BirdVisit[];
  species: BirdSpecies[];
  loading?: boolean;
  onVisitDeleted: (visitId: string) => void;
  onVisitUpdated: () => void;
  /** Visita que deve abrir automaticamente no player (atalho do painel). */
  focusVisitId?: string | null;
  /** Avisa o painel que o foco já foi consumido. */
  onFocusHandled?: () => void;
};

type GalleryView = "captures" | "rare" | "guests" | "timelapses" | "audio";

/**
 * Aba Galeria com visões distintas e separadas: as **capturas de imagem/vídeo**
 * das visitas, os **Convidados do Jardim** (visitantes especiais), os **resumos
 * do dia** (time-lapses) e a **galeria de áudios** (cantos do BirdNET). A
 * alternância fica em um controle segmentado.
 */
export function GalleryPanel({
  visits,
  species,
  loading,
  onVisitDeleted,
  onVisitUpdated,
  focusVisitId,
  onFocusHandled,
}: Props) {
  const [view, setView] = useState<GalleryView>("captures");

  // Um atalho do painel sempre abre na visão de capturas.
  useEffect(() => {
    if (focusVisitId) setView("captures");
  }, [focusVisitId]);

  return (
    <section className="space-y-4">
      <div
        role="tablist"
        aria-label="Visões da galeria"
        className="inline-flex flex-wrap gap-1 rounded-lg border border-dark-700 bg-dark-800 p-1"
      >
        <TabButton
          active={view === "captures"}
          icon={Images}
          label="Fotos e Vídeos"
          onClick={() => setView("captures")}
        />
        <TabButton
          active={view === "rare"}
          icon={Sparkles}
          label="Momentos Raros"
          onClick={() => setView("rare")}
        />
        <TabButton
          active={view === "audio"}
          icon={AudioLines}
          label="Áudios"
          onClick={() => setView("audio")}
        />
        <TabButton
          active={view === "guests"}
          icon={Squirrel}
          label="Convidados do Jardim"
          onClick={() => setView("guests")}
        />
        <TabButton
          active={view === "timelapses"}
          icon={Film}
          label="Resumos do Dia (Time-Lapse)"
          onClick={() => setView("timelapses")}
        />
      </div>

      {view === "captures" ? (
        <GalleryGrid
          visits={visits}
          species={species}
          loading={loading}
          onVisitDeleted={onVisitDeleted}
          onVisitUpdated={onVisitUpdated}
          focusVisitId={focusVisitId}
          onFocusHandled={onFocusHandled}
        />
      ) : view === "rare" ? (
        <RareMomentsGallery />
      ) : view === "guests" ? (
        <GalleryGrid
          visits={visits.filter((v) => v.visitor_kind !== "bird")}
          species={species}
          loading={loading}
          onVisitDeleted={onVisitDeleted}
          onVisitUpdated={onVisitUpdated}
          focusVisitId={focusVisitId}
          onFocusHandled={onFocusHandled}
        />
      ) : view === "audio" ? (
        <AudioDetectionPanel species={species} />
      ) : (
        <TimelapseGallery />
      )}
    </section>
  );
}

function TabButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: typeof Images;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
        active
          ? "bg-emerald-500/15 text-emerald-400"
          : "text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}
