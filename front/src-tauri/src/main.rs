// Binário do Bem-Te-Vi Monitor.
//
// Em release, o binário roda sem janela de console no Windows.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    bem_te_vi_monitor_lib::run();
}
