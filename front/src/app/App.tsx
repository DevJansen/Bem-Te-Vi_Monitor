import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { KPIBoard } from "@/components/dashboard/KPIBoard";
import { AnomalyAlertsPanel } from "@/components/dashboard/AnomalyAlertsPanel";
import { AiCorePanel } from "@/components/dashboard/AiCorePanel";
import { CameraWall } from "@/components/dashboard/CameraWall";
import { AiStreamLog } from "@/components/dashboard/AiStreamLog";
import { LiveStreamView } from "@/components/dashboard/LiveStreamView";
import { WeatherWidget } from "@/components/dashboard/WeatherWidget";
import { VisitsChart } from "@/components/dashboard/VisitsChart";
import { SpeciesRanking } from "@/components/dashboard/SpeciesRanking";
import { TodayVisitsPanel } from "@/components/dashboard/TodayVisitsPanel";
import { CameraGrid } from "@/components/cameras/CameraGrid";
import { AddCameraModal } from "@/components/cameras/AddCameraModal";
import { ZoneEditorModal } from "@/components/cameras/ZoneEditorModal";
import { RoiEditorModal } from "@/components/cameras/RoiEditorModal";
import { OfflineAnalysisScreen } from "@/components/offline/OfflineAnalysisScreen";
import { OfflineProgressDock } from "@/components/offline/OfflineProgressDock";
import { useOfflineAnalysis } from "@/context/OfflineAnalysisContext";
import { GalleryPanel } from "@/components/gallery/GalleryPanel";
import { EnvSettings } from "@/components/settings/EnvSettings";
import { CalibrationPanel } from "@/components/settings/CalibrationPanel";
import { SpeciesCatalog } from "@/components/species/SpeciesCatalog";
import { AudioDetectionPanel } from "@/components/audio/AudioDetectionPanel";
import { usePolling } from "@/hooks/usePolling";
import {
  createCamera,
  deleteCamera,
  fetchApiHealth,
  fetchMetrics,
  getErrorMessage,
  listCameras,
  listSpecies,
  listVisits,
  updateCamera,
} from "@/services/api";
import type {
  AiStatus,
  AppTab,
  Camera,
  CameraCreatePayload,
} from "@/types";

const AnalyticsDashboard = lazy(() =>
  import("@/components/dashboard/AnalyticsDashboard").then((module) => ({
    default: module.AnalyticsDashboard,
  })),
);

const TAB_META: Record<AppTab, { title: string; subtitle: string }> = {
  dashboard: {
    title: "Painel",
    subtitle: "Visão geral do monitoramento local de avifauna",
  },
  cameras: {
    title: "Central de Câmeras",
    subtitle: "Fontes locais e externas (RTSP, HLS, HTTP, WebRTC) com credenciais criptografadas",
  },
  gallery: {
    title: "Galeria",
    subtitle: "Capturas, clipes, áudios e exportação CSV",
  },
  audio: {
    title: "Detecção Sonora",
    subtitle: "Cantos identificados pelo BirdNET — ouça, identifique e consulte a IA",
  },
  species: {
    title: "Minhas Aves",
    subtitle: "Seu catálogo local de espécies da região",
  },
  analytics: {
    title: "Estatísticas & Conquistas",
    subtitle: "Seus hábitos de observação e o álbum de espécies",
  },
  settings: {
    title: "Configurações",
    subtitle: "Integrações, variáveis de ambiente e parâmetros da IA",
  },
};

export function App() {
  const [tab, setTab] = useState<AppTab>("dashboard");
  const [modalOpen, setModalOpen] = useState(false);
  const [zoneCamera, setZoneCamera] = useState<Camera | null>(null);
  const [roiCamera, setRoiCamera] = useState<Camera | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deletedVisitIds, setDeletedVisitIds] = useState<Set<string>>(new Set());
  // Visita que deve abrir automaticamente na Galeria (atalho do deep-dive).
  const [galleryFocusVisitId, setGalleryFocusVisitId] = useState<string | null>(
    null,
  );

  const [metricsGarden, setMetricsGarden] = useState<string | null>(null);
  const metricsGardenRef = useRef<string | null>(null);
  metricsGardenRef.current = metricsGarden;
  const metricsQuery = usePolling(
    () => fetchMetrics(metricsGardenRef.current ?? undefined),
    8_000,
  );
  const camerasQuery = usePolling(listCameras, 5_000);
  const visitsQuery = usePolling(() => listVisits({ limit: 200 }), 10_000);
  const speciesQuery = usePolling(listSpecies, 60_000);
  const healthQuery = usePolling(fetchApiHealth, 12_000);

  // Conclusões de análise offline (para atualizar Galeria e indicadores).
  const { successes } = useOfflineAnalysis();
  const handledSuccessRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const fresh = successes.filter(
      (job) => !handledSuccessRef.current.has(job.id),
    );
    if (fresh.length === 0) return;
    fresh.forEach((job) => handledSuccessRef.current.add(job.id));
    // Atualiza a Galeria e os indicadores assim que um vídeo termina, sem
    // trocar de aba: o usuário decide quando abrir a Galeria.
    void Promise.all([visitsQuery.refresh(), metricsQuery.refresh()]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [successes]);

  const aiStatus: AiStatus = useMemo(() => {
    if (healthQuery.loading && !healthQuery.data) return "loading";
    if (healthQuery.error || !healthQuery.data) return "offline";
    const cams = camerasQuery.data ?? [];
    const hasError = cams.some((c) => c.is_active && c.status === "error");
    if (hasError) return "degraded";
    return "online";
  }, [healthQuery, camerasQuery.data]);

  const refreshAll = async () => {
    await Promise.all([
      metricsQuery.refresh(),
      camerasQuery.refresh(),
      visitsQuery.refresh(),
      speciesQuery.refresh(),
      healthQuery.refresh(),
    ]);
  };

  const handleCreate = async (payload: CameraCreatePayload) => {
    try {
      await createCamera(payload);
      await camerasQuery.refresh();
      await metricsQuery.refresh();
    } catch (err) {
      throw new Error(getErrorMessage(err, "Falha ao criar câmera"));
    }
  };

  const handleToggle = async (camera: Camera, enabled: boolean) => {
    setActionError(null);
    try {
      await updateCamera(camera.id, { enabled });
      await camerasQuery.refresh();
      await metricsQuery.refresh();
    } catch (err) {
      setActionError(getErrorMessage(err, "Falha ao atualizar câmera"));
    }
  };

  const handleCameraUpdated = (updated: Camera) => {
    camerasQuery.setData((current: Camera[] | null) =>
      current
        ? current.map((c: Camera) => (c.id === updated.id ? updated : c))
        : [updated],
    );
    void Promise.all([camerasQuery.refresh(), metricsQuery.refresh()]);
  };

  const handleDelete = async (camera: Camera) => {
    const ok = window.confirm(`Remover a câmera "${camera.name}"?`);
    if (!ok) return;
    setActionError(null);
    try {
      await deleteCamera(camera.id);
      await camerasQuery.refresh();
      await metricsQuery.refresh();
    } catch (err) {
      setActionError(getErrorMessage(err, "Falha ao remover câmera"));
    }
  };

  const handleVisitDeleted = (visitId: string) => {
    setDeletedVisitIds((current) => new Set(current).add(visitId));
    void Promise.all([visitsQuery.refresh(), metricsQuery.refresh()]);
  };

  // Atalho "ver clipe na Galeria": troca de aba e abre o clipe da visita.
  const handleOpenVisitInGallery = useCallback((visitId: string) => {
    setGalleryFocusVisitId(visitId);
    setTab("gallery");
  }, []);

  const handleGalleryFocusHandled = useCallback(
    () => setGalleryFocusVisitId(null),
    [],
  );

  const handleHistoryCleared = (cutoff: string | null, failedIds: string[]) => {
    const failedSet = new Set(failedIds);
    const removedIds = (visitsQuery.data ?? [])
      .filter((visit) =>
        cutoff === null
          ? !failedSet.has(visit.id)
          : !failedSet.has(visit.id) &&
            new Date(visit.detected_at).getTime() < new Date(cutoff).getTime(),
      )
      .map((visit) => visit.id);
    setDeletedVisitIds((current) => new Set([...current, ...removedIds]));
    void Promise.all([visitsQuery.refresh(), metricsQuery.refresh()]);
  };

  const meta = TAB_META[tab];

  return (
    <div className="min-h-screen bg-dark-900 text-[var(--color-text-primary)]">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-50"
        style={{
          background:
            "radial-gradient(ellipse 70% 40% at 80% -10%, rgba(16,185,129,0.12), transparent), linear-gradient(180deg, #111816 0%, #0a0f0d 45%)",
        }}
      />

      <Sidebar activeTab={tab} onTabChange={setTab} />

      <div className="relative pt-[6.5rem] md:pl-60 md:pt-0">
        <Header
          title={meta.title}
          subtitle={meta.subtitle}
          metrics={metricsQuery.data}
          aiStatus={aiStatus}
          onRefresh={() => void refreshAll()}
          refreshing={metricsQuery.loading || camerasQuery.loading}
        />

        <main className="px-4 py-5 md:px-6 md:py-6">
          {actionError ? (
            <p className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {actionError}
            </p>
          ) : null}

          {tab === "dashboard" ? (
            <div className="space-y-4">
              <AiCorePanel />
              <CameraWall
                cameras={camerasQuery.data ?? []}
                onCameraUpdated={handleCameraUpdated}
              />
              <WeatherWidget cameras={camerasQuery.data ?? []} />
              <AnomalyAlertsPanel />
              <div className="mb-3 flex items-center gap-2">
                <label className="text-xs text-[var(--color-text-muted)]">Jardim:</label>
                <select
                  value={metricsGarden ?? ""}
                  onChange={(e) => {
                    const val = e.target.value === "" ? null : e.target.value;
                    metricsGardenRef.current = val;
                    setMetricsGarden(val);
                    void metricsQuery.refresh();
                  }}
                  className="rounded-md border border-dark-700 bg-dark-900/60 px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
                >
                  <option value="">Todos os jardins</option>
                  {(camerasQuery.data ?? []).map((cam) => (
                    <option key={cam.id} value={cam.id}>
                      {cam.location_label || cam.name || "Jardim sem nome"}
                    </option>
                  ))}
                </select>
              </div>
              <KPIBoard metrics={metricsQuery.data} loading={metricsQuery.loading} />
              <div className="grid gap-4 xl:grid-cols-3">
                <div className="xl:col-span-2">
                  <LiveStreamView
                    cameras={camerasQuery.data ?? []}
                    onEditZones={setZoneCamera}
                    onEditRoi={setRoiCamera}
                    onDelete={(cam) => void handleDelete(cam)}
                    onCameraUpdated={handleCameraUpdated}
                  />
                </div>
                <div className="space-y-4">
                  <SpeciesRanking
                    metrics={metricsQuery.data}
                    species={speciesQuery.data ?? []}
                    limit={5}
                    subtitle="Top 5 espécies mais frequentes"
                  />
                  <AiStreamLog />
                </div>
              </div>
              <TodayVisitsPanel
                species={speciesQuery.data ?? []}
                onOpenInGallery={handleOpenVisitInGallery}
              />
              <VisitsChart metrics={metricsQuery.data} />
            </div>
          ) : null}

          {tab === "cameras" ? (
            <div>
              <OfflineAnalysisScreen
                cameras={camerasQuery.data ?? []}
                onOpenGallery={() => setTab("gallery")}
              />
              <CameraGrid
                cameras={camerasQuery.data ?? []}
                loading={camerasQuery.loading}
                onAdd={() => setModalOpen(true)}
                onToggle={(cam, enabled) => void handleToggle(cam, enabled)}
                onDelete={(cam) => void handleDelete(cam)}
                onEditZones={setZoneCamera}
                onEditRoi={setRoiCamera}
              />
            </div>
          ) : null}

          {tab === "gallery" ? (
            <div className="space-y-4">
              <GalleryPanel
                visits={(visitsQuery.data ?? []).filter(
                  (visit) => !deletedVisitIds.has(visit.id),
                )}
                species={speciesQuery.data ?? []}
                loading={visitsQuery.loading}
                onVisitDeleted={handleVisitDeleted}
                onVisitUpdated={() => void visitsQuery.refresh()}
                focusVisitId={galleryFocusVisitId}
                onFocusHandled={handleGalleryFocusHandled}
              />
            </div>
          ) : null}

          {tab === "audio" ? (
            <AudioDetectionPanel species={speciesQuery.data ?? []} />
          ) : null}

          {tab === "species" ? (
            <SpeciesCatalog
              species={speciesQuery.data ?? []}
              loading={speciesQuery.loading}
              error={speciesQuery.error}
              onCatalogChanged={() => void speciesQuery.refresh()}
            />
          ) : null}

          {tab === "analytics" ? (
            <Suspense
              fallback={
                <p className="rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
                  Carregando módulo de estatísticas…
                </p>
              }
            >
              <AnalyticsDashboard />
            </Suspense>
          ) : null}

          {tab === "settings" ? (
            <div className="space-y-6">
              <CalibrationPanel />
              <EnvSettings onHistoryCleared={handleHistoryCleared} />
            </div>
          ) : null}
        </main>
      </div>

      <AddCameraModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreate}
      />
      <ZoneEditorModal
        camera={zoneCamera}
        onClose={() => setZoneCamera(null)}
        onSaved={() => void camerasQuery.refresh()}
      />
      <RoiEditorModal
        camera={roiCamera}
        onClose={() => setRoiCamera(null)}
        onSaved={() => void camerasQuery.refresh()}
      />

      <OfflineProgressDock onOpenGallery={() => setTab("gallery")} />
    </div>
  );
}
