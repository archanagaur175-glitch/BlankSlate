use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::Mutex as StdMutex;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;

const RECONNECT_DELAY_SECS: u64 = 2;

/// Process-local state shared between the daemon session task and commands.
#[derive(Default)]
struct WsState {
    tx: tokio::sync::Mutex<Option<mpsc::UnboundedSender<String>>>,
    status: StdMutex<ConStatus>,
    daemon_child: StdMutex<Option<std::process::Child>>,
    ollama_child: StdMutex<Option<std::process::Child>>,
}

#[derive(Serialize, Clone)]
struct ConStatus {
    connected: bool,
    detail: String,
}

impl Default for ConStatus {
    fn default() -> Self {
        Self {
            connected: false,
            detail: "starting…".into(),
        }
    }
}

/// Contents of `%LOCALAPPDATA%\BlankSlate\ipc.json` emitted by the daemon.
#[derive(Deserialize)]
struct IpcInfo {
    #[serde(default)]
    url: String,
    #[serde(default)]
    host: String,
    #[serde(default)]
    port: u16,
    #[serde(default)]
    version: String,
}

fn ipc_info_path() -> PathBuf {
    let base = dirs::data_local_dir().unwrap_or_else(std::env::temp_dir);
    base.join("BlankSlate").join("ipc.json")
}

fn read_ipc_info() -> Option<IpcInfo> {
    let text = std::fs::read_to_string(ipc_info_path()).ok()?;
    serde_json::from_str(&text).ok()
}

fn set_status(app: &AppHandle, ws: &State<'_, WsState>, connected: bool, detail: String) {
    let mut current = ws.status.lock().unwrap();
    if current.connected == connected && current.detail == detail {
        return;
    }
    current.connected = connected;
    current.detail = detail.clone();
    let _ = app.emit("daemon_status", current.clone());
}

async fn daemon_loop(app: AppHandle) {
    loop {
        let ws = app.state::<WsState>();
        match read_ipc_info() {
            Some(info) => match run_session(&app, &ws, &info).await {
                Ok(()) => set_status(&app, &ws, false, "disconnected".into()),
                Err(err) => {
                    log::warn!("daemon session failed: {err}");
                    set_status(&app, &ws, false, handle_error(&err));
                }
            },
            None => {
                set_status(&app, &ws, false, "daemon not running (no ipc.json)".into());
            }
        }
        tokio::time::sleep(Duration::from_secs(RECONNECT_DELAY_SECS)).await;
    }
}

fn handle_error(err: &str) -> String {
    if err.to_lowercase().contains("refused") || err.to_lowercase().contains("connect") {
        "daemon unreachable (retrying…)".into()
    } else if err.to_lowercase().contains("token") || err.to_lowercase().contains("4001") {
        "token rejected — restart the daemon".into()
    } else {
        format!("connection error: {err}")
    }
}

async fn run_session(
    app: &AppHandle,
    ws: &State<'_, WsState>,
    info: &IpcInfo,
) -> Result<(), String> {
    if info.url.is_empty() || !info.url.starts_with("ws://") {
        return Err("no valid ws:// endpoint in ipc.json".into());
    }
    let (stream, _) = tokio_tungstenite::connect_async(&info.url)
        .await
        .map_err(|e| e.to_string())?;
    log::info!("connected to daemon at {}:{}", info.host, info.port);
    set_status(app, ws, true, format!("daemon v{}", info.version));

    let (mut sink, mut stream) = stream.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<String>();
    *ws.tx.lock().await = Some(tx);

    loop {
        tokio::select! {
            incoming = stream.next() => {
                match incoming {
                    Some(Ok(Message::Text(text))) => {
                        let _ = app.emit("daemon_event", text);
                    }
                    // The Python websockets server sends Ping frames to keep the
                    // connection alive; we must answer with a Pong or it closes
                    // the socket. Breaking on Ping here was the bug that dropped
                    // the connection every ~20s and triggered a reconnect loop.
                    Some(Ok(Message::Ping(p))) => {
                        if sink.send(Message::Pong(p)).await.is_err() {
                            break;
                        }
                    }
                    Some(Ok(Message::Pong(_))) => {}
                    Some(Ok(Message::Close(_))) => break,
                    Some(Ok(_)) => {}
                    Some(Err(_)) | None => break,
                }
            }
            outgoing = rx.recv() => {
                match outgoing {
                    Some(payload) => {
                        if sink.send(Message::Text(payload.into())).await.is_err() {
                            break;
                        }
                    }
                    None => break,
                }
            }
        }
    }

    *ws.tx.lock().await = None;
    log::info!("daemon connection closed");
    Ok(())
}

#[tauri::command]
async fn send_message(ws: State<'_, WsState>, payload: String) -> Result<(), String> {
    let lock = ws.tx.lock().await;
    let tx = lock
        .as_ref()
        .ok_or_else(|| "daemon not connected".to_string())?;
    tx.send(payload).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_daemon_status(ws: State<'_, WsState>) -> ConStatus {
    ws.status.lock().unwrap().clone()
}

#[cfg(target_os = "windows")]
fn apply_vibrancy(window: &tauri::WebviewWindow) {
    use window_vibrancy::{apply_acrylic, apply_mica};

    // Mica prefers a window whose background is near-opaque; fall back to
    // acrylic (translucent blur) when the window is transparent.
    let _ = apply_mica(window, None).or_else(|_| apply_acrylic(window, Some((16, 18, 28, 120))));
}

#[cfg(target_os = "macos")]
fn apply_vibrancy(window: &tauri::WebviewWindow) {
    use window_vibrancy::NSVisualEffectMaterial;

    let _ = window_vibrancy::apply_vibrancy(
        window,
        NSVisualEffectMaterial::HudWindow,
        None,
        Some(20.0),
    );
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    use tauri::menu::{Menu, MenuItem};
    use tauri::tray::TrayIconBuilder;

    let show = MenuItem::with_id(app, "show", "Show BlankSlate", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit BlankSlate", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    let mut builder = TrayIconBuilder::new()
        .menu(&menu)
        .show_menu_on_left_click(true)
        .tooltip("BlankSlate");
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .build(app)?;
    Ok(())
}

fn init_logging() {
    let _ = env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .try_init();
}

/// If the installer bundled Ollama under `resources/ollama/`, start its server
/// so the assistant works with zero manual setup. If Ollama is already running
/// (e.g. a system install) or no bundle exists, we just connect to it.
fn launch_ollama(app: &tauri::App) {
    let res = match app.path().resource_dir() {
        Ok(dir) => dir,
        Err(_) => return,
    };
    let path = res.join("ollama").join("ollama.exe");
    if !path.exists() {
        log::info!("no bundled ollama at {:?}; expecting system ollama", path);
        return;
    }
    if ollama_up() {
        log::info!("ollama already running; using existing instance");
        return;
    }
    match std::process::Command::new(&path)
        .arg("serve")
        .env("OLLAMA_HOST", "127.0.0.1:11434")
        .spawn()
    {
        Ok(child) => {
            log::info!("launched bundled ollama from {:?}", path);
            *app.state::<WsState>().ollama_child.lock().unwrap() = Some(child);
        }
        Err(err) => log::warn!("failed to launch bundled ollama: {err}"),
    }
}

fn ollama_up() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:11434".parse().unwrap(),
        Duration::from_millis(300),
    )
    .is_ok()
}

/// When the installer bundles a frozen daemon under `resources/daemon/`, launch
/// it so the HUD is fully self-contained. If no bundled binary exists we assume
/// an external daemon is already running and connect to it instead.
fn launch_bundled_daemon(app: &tauri::App) {
    let res = match app.path().resource_dir() {
        Ok(dir) => dir,
        Err(_) => return,
    };
    let exe = if cfg!(windows) { "blankslate.exe" } else { "blankslate" };
    let path = res.join("daemon").join(exe);
    if !path.exists() {
        log::info!("no bundled daemon at {:?}; expecting external daemon", path);
        return;
    }
    match std::process::Command::new(&path).spawn() {
        Ok(child) => {
            log::info!("launched bundled daemon from {:?}", path);
            *app.state::<WsState>().daemon_child.lock().unwrap() = Some(child);
        }
        Err(err) => log::warn!("failed to launch bundled daemon: {err}"),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_logging();
    let app = tauri::Builder::default()
        .manage(WsState::default())
        .invoke_handler(tauri::generate_handler![send_message, get_daemon_status])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let win = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        // "Close" hides to the tray rather than exiting.
                        api.prevent_close();
                        let _ = win.hide();
                    }
                });

                #[cfg(any(target_os = "windows", target_os = "macos"))]
                apply_vibrancy(&window);
            }

            build_tray(app)?;
            launch_ollama(app);
            launch_bundled_daemon(app);

            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                daemon_loop(handle).await;
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building BlankSlate HUD");

    app.run(|_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            if let Some(mut child) = _handle.state::<WsState>().daemon_child.lock().unwrap().take() {
                let _ = child.kill();
            }
            if let Some(mut child) = _handle.state::<WsState>().ollama_child.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    });
}
