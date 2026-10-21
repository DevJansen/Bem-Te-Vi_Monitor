// Bem-Te-Vi Monitor — casca desktop (Tauri) do painel web.
//
// A janela carrega a interface do Bem-Te-Vi Monitor (mesma do navegador) e
// conversa com o **Bem-Te-Vi Core**, o backend FastAPI local (127.0.0.1:8000).

/// Inicializa a janela do Bem-Te-Vi Monitor.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Bem-Te-Vi Monitor");
}
