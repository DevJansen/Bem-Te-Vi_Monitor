/**
 * Utilitários para o ciclo de vida das transmissões MJPEG (vídeo ao vivo).
 */

/**
 * Aborta uma transmissão MJPEG em andamento em uma tag `<img>`.
 *
 * Um stream MJPEG mantém a conexão HTTP aberta enquanto a imagem existir. Ao
 * desmontar o painel ou fechar o editor, é preciso encerrar essa conexão na
 * hora — caso contrário ela fica "pendurada" e, como o navegador limita o
 * número de conexões por origem, as próximas requisições ficam presas até o
 * usuário dar um F5.
 *
 * Definir `src` como string vazia faz o navegador cancelar o carregamento sem
 * disparar uma nova requisição (um `src` vazio é ignorado pela especificação).
 */
export function abortMjpegStream(img: HTMLImageElement | null): void {
  if (!img) return;
  try {
    img.src = "";
  } catch {
    /* ignora eventuais falhas ao abortar a conexão */
  }
}
