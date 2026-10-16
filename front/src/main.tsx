import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/App";
import { OfflineAnalysisProvider } from "@/context/OfflineAnalysisContext";
import "@/styles/globals.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Elemento #root não encontrado");
}

createRoot(rootElement).render(
  <StrictMode>
    {/* O provedor fica acima das abas para que o progresso das análises de
        vídeo sobreviva à navegação e a recarregamentos de tela. */}
    <OfflineAnalysisProvider>
      <App />
    </OfflineAnalysisProvider>
  </StrictMode>,
);
