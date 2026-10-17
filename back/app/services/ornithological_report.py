"""Laudo Ornitológico Automatizado em PDF.

Compila um relatório profissional (para biólogos e pesquisadores) com:
sumário executivo, estatísticas de visitas, cruzamento com clima e as melhores
fotos tratadas em alta definição obtidas pelo Alaris Core.

Usa fpdf2 para o PDF e matplotlib para os gráficos embutidos.
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.infra.database.analytics_repository import AnalyticsRepository
from app.infra.database.connection import db_session
from app.infra.database.repository import SQL_SO_AVES, VisitRepository

logger = logging.getLogger(__name__)

_COR_PRIMARIA = (16, 122, 87)
_COR_SECUNDARIA = (34, 197, 94)
_COR_TEXTO = (33, 37, 41)
_COR_CINZA = (108, 117, 125)
_COR_FUNDO = (248, 250, 252)


def _fmt_data(data: str | None) -> str:
    if not data:
        return "—"
    try:
        dt = datetime.fromisoformat(data.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return data


class LaudoOrnithologico:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.analytics = AnalyticsRepository(db_path)
        self.visits = VisitRepository(db_path)

    def gerar(self) -> bytes:
        from fpdf import FPDF

        periodo = self._periodo()
        sumario = self.analytics.summary()
        clima = self.analytics.weather_correlation()
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        fonte = "C:/Windows/Fonts/arial.ttf"
        pdf.add_font("Arial", "", fonte, uni=True)
        pdf.add_font("Arial", "B", "C:/Windows/Fonts/arialbd.ttf", uni=True)
        pdf.add_font("Arial", "I", "C:/Windows/Fonts/ariali.ttf", uni=True)
        pdf.add_page()

        self._cabecalho(pdf, periodo)
        self._sumario_executivo(pdf, sumario, clima)
        self._estatisticas(pdf, sumario)
        self._grafico_horario(pdf)
        self._grafico_clima(pdf, clima)
        self._melhores_fotos(pdf)
        self._rodape(pdf)

        return bytes(pdf.output())

    def _periodo(self) -> dict[str, Any]:
        hoje = datetime.now(timezone.utc).date()
        inicio = hoje - timedelta(days=30)
        return {"inicio": inicio.isoformat(), "fim": hoje.isoformat()}

    def _cabecalho(self, pdf: Any, periodo: dict[str, Any]) -> None:
        pdf.set_fill_color(*_COR_PRIMARIA)
        pdf.rect(0, 0, 210, 32, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 18)
        pdf.set_xy(10, 8)
        pdf.cell(0, 8, "Laudo Ornitológico Bem-Ti-Vi", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Arial", "", 10)
        pdf.cell(
            0,
            6,
            f"Período: {periodo['inicio']} a {periodo['fim']}  |  Gerado em "
            f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(*_COR_TEXTO)
        pdf.ln(4)

    def _sumario_executivo(
        self, pdf: Any, sumario: dict[str, Any], clima: dict[str, Any]
    ) -> None:
        self._titulo_secao(pdf, "1. Sumário Executivo")
        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(*_COR_TEXTO)
        linhas = [
            f"Total de visitas no período: {sumario['total_visits']}",
            f"Visitas nas últimas 24h: {sumario['visits_today']}",
            f"Visitas nos últimos 7 dias: {sumario['visits_last_7_days']}",
            f"Espécie mais frequente: {sumario['most_frequent_species'] or '—'} "
            f"({sumario['most_frequent_species_count']} registros)",
            f"Horário de pico: {sumario['peak_hour'] or '—'}",
            f"Permanência média: {sumario['average_duration_seconds']:.1f} s",
            f"Condições climáticas observadas: {clima['visits_with_weather']} visitas "
            f"com dados de clima",
        ]
        for linha in linhas:
            pdf.multi_cell(0, 6, f"-  {linha}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    def _estatisticas(self, pdf: Any, sumario: dict[str, Any]) -> None:
        self._titulo_secao(pdf, "2. Estatísticas de Visitas")
        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(*_COR_TEXTO)
        pdf.multi_cell(
            0,
            6,
            "As estatísticas abaixo consolidam o período analisado, considerando "
            "apenas aves (Visitantes Especiais como esquilos são contados à parte).",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(2)
        pdf.set_fill_color(*_COR_SECUNDARIA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(90, 7, "Indicador", border=1, fill=True)
        pdf.cell(0, 7, "Valor", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_COR_TEXTO)
        pdf.set_font("Arial", "", 9)
        indicadores = [
            ("Total de visitas", str(sumario["total_visits"])),
            ("Visitas hoje", str(sumario["visits_today"])),
            ("Últimos 7 dias", str(sumario["visits_last_7_days"])),
            ("Espécie mais frequente", sumario["most_frequent_species"] or "—"),
            ("Horário de pico", sumario["peak_hour"] or "—"),
            ("Permanência média (s)", f"{sumario['average_duration_seconds']:.1f}"),
        ]
        for nome, valor in indicadores:
            pdf.cell(90, 6, nome, border=1)
            pdf.cell(0, 6, valor, border=1, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    def _grafico_horario(self, pdf: Any) -> None:
        self._titulo_secao(pdf, "3. Visitas por Horário de Pico")
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            dist = self.analytics.hourly_distribution()
            horas = [int(item["hour"]) for item in dist]
            valores = [item["visits"] for item in dist]

            fig, ax = plt.subplots(figsize=(7, 2.6), dpi=120)
            ax.bar(horas, valores, color="#22c55e", alpha=0.85)
            ax.set_xlabel("Hora do dia")
            ax.set_ylabel("Visitas")
            ax.set_title("Distribuição de visitas por horário (fuso local da câmera)")
            ax.set_xticks(range(0, 24, 2))
            fig.tight_layout()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                fig.savefig(tmp.name, format="png")
                plt.close(fig)
                pdf.image(tmp.name, x=10, w=190)
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except OSError:
                pass
        except Exception:
            logger.exception("Falha ao gerar gráfico de horário")
            pdf.set_font("Arial", "I", 9)
            pdf.cell(0, 6, "Gráfico indisponível.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    def _grafico_clima(self, pdf: Any, clima: dict[str, Any]) -> None:
        self._titulo_secao(pdf, "4. Cruzamento Clima x Visitas")
        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(*_COR_TEXTO)
        if not clima["by_condition"]:
            pdf.multi_cell(
                0, 6, "Sem dados de clima suficientes no período.", new_x="LMARGIN", new_y="NEXT"
            )
            return
        pdf.set_font("Arial", "B", 9)
        pdf.cell(70, 7, "Condição", border=1, fill=True)
        pdf.cell(30, 7, "Visitas", border=1, fill=True)
        pdf.cell(0, 7, "Temp. média (°C)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Arial", "", 9)
        for item in clima["by_condition"][:8]:
            temp = (
                f"{item['avg_temperature']:.1f}"
                if item.get("avg_temperature") is not None
                else "—"
            )
            pdf.cell(70, 6, str(item["condition"]), border=1)
            pdf.cell(30, 6, str(item["visits"]), border=1)
            pdf.cell(0, 6, temp, border=1, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    def _melhores_fotos(self, pdf: Any) -> None:
        self._titulo_secao(pdf, "5. Melhores Fotos Tratadas (Alaris Core)")
        melhores = self._buscar_melhores_fotos(limite=6)
        if not melhores:
            pdf.set_font("Arial", "I", 9)
            pdf.cell(
                0, 6, "Nenhuma foto tratada disponível no período.", new_x="LMARGIN", new_y="NEXT"
            )
            return
        for foto in melhores:
            if pdf.get_y() > 240:
                pdf.add_page()
            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(*_COR_TEXTO)
            pdf.cell(
                0,
                6,
                f"{foto['species']} — {_fmt_data(foto['detected_at'])}",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            try:
                pdf.image(foto["path"], x=10, w=100)
            except Exception:
                logger.warning("Falha ao embutir foto %s", foto["path"])
            pdf.ln(2)

    def _buscar_melhores_fotos(self, limite: int = 6) -> list[dict[str, Any]]:
        fotos: list[dict[str, Any]] = []
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT v.id, v.species, v.detected_at, v.thumbnail_path,
                       v.metadata_json
                FROM visits v
                WHERE {SQL_SO_AVES} AND v.thumbnail_path IS NOT NULL
                ORDER BY v.confidence DESC, v.detected_at DESC
                LIMIT ?
                """,
                (limite * 4,),
            ).fetchall()
        for row in rows:
            metadata = {}
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                pass
            nitidez = metadata.get("best_frame_sharpness") or 0
            fotos.append(
                {
                    "id": row["id"],
                    "species": row["species"],
                    "detected_at": row["detected_at"],
                    "path": self._resolver_caminho(row["thumbnail_path"]),
                    "nitidez": nitidez,
                }
            )
        fotos.sort(key=lambda f: f["nitidez"], reverse=True)
        return fotos[:limite]

    def _resolver_caminho(self, relativo: str | None) -> str | None:
        if not relativo:
            return None
        base = Path(get_settings().app_data_dir) / "captures"
        candidata = base / relativo
        if candidata.exists():
            return str(candidata)
        alternativa = Path(get_settings().app_data_dir).parent / relativo
        return str(alternativa) if alternativa.exists() else None

    def _rodape(self, pdf: Any) -> None:
        pdf.set_y(-15)
        pdf.set_font("Arial", "I", 8)
        pdf.set_text_color(*_COR_CINZA)
        pdf.cell(
            0,
            10,
            "Bem-Ti-Vi - Plataforma de Observação de Aves | Laudo gerado automaticamente",
            align="C",
        )

    def _titulo_secao(self, pdf: Any, titulo: str) -> None:
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(*_COR_PRIMARIA)
        pdf.cell(0, 8, titulo, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*_COR_SECUNDARIA)
        pdf.line(10, pdf.get_y(), 60, pdf.get_y())
        pdf.ln(2)


def gerar_laudo_pdf(db_path: Path) -> bytes:
    return LaudoOrnithologico(db_path).gerar()
