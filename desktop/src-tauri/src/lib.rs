use std::{
    io::{BufRead, BufReader, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use tauri::{menu::MenuBuilder, tray::TrayIconBuilder, Emitter, Manager, WindowEvent};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const CONTROL_HOST: &str = "127.0.0.1";
const CONTROL_PORT: u16 = 49_731;
const CONTROL_TIMEOUT: Duration = Duration::from_secs(2);
const BACKEND_START_POLL: Duration = Duration::from_millis(250);
const BACKEND_STOP_ATTEMPTS: usize = 12;
const BACKEND_SLOW_START_SECONDS: u64 = 45;
const SIDECAR_BINARY_NAME: &str = "local-dictation-backend";
const MAIN_WINDOW_LABEL: &str = "main";
const BUBBLE_WINDOW_LABEL: &str = "bubble";
const QUICK_POPOVER_WINDOW_LABEL: &str = "quick-popover";
const BUBBLE_WINDOW_SIZE: i32 = 56;
const QUICK_POPOVER_WIDTH: i32 = 410;
const QUICK_POPOVER_HEIGHT: i32 = 300;
const WINDOW_SAFE_MARGIN: i32 = 16;
const POPOVER_TAIL_SAFE_MARGIN: i32 = 16;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MainWindowCloseAction {
    HideMainWindow,
}

fn main_window_close_action() -> MainWindowCloseAction {
    MainWindowCloseAction::HideMainWindow
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct WindowPoint {
    x: i32,
    y: i32,
}

impl WindowPoint {
    fn new(x: i32, y: i32) -> Self {
        Self { x, y }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct WindowSize {
    width: i32,
    height: i32,
}

impl WindowSize {
    fn new(width: i32, height: i32) -> Self {
        Self { width, height }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct WorkArea {
    x: i32,
    y: i32,
    width: i32,
    height: i32,
}

impl WorkArea {
    fn new(x: i32, y: i32, width: i32, height: i32) -> Self {
        Self {
            x,
            y,
            width,
            height,
        }
    }

    fn right(self) -> i32 {
        self.x + self.width
    }

    fn bottom(self) -> i32 {
        self.y + self.height
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct PopoverPlacement {
    position: WindowPoint,
    tail_x: i32,
}

#[derive(Clone, Debug, Serialize)]
struct PopoverPlacementEvent {
    tail_x: i32,
}

#[derive(Debug, PartialEq, Eq)]
enum BackendLaunchStrategy {
    Sidecar,
    PythonFallback,
    MissingRequiredSidecar,
}

#[derive(Debug)]
enum ManagedBackendChild {
    Python(Child),
    Sidecar(CommandChild),
}

#[derive(Debug, Deserialize)]
struct BridgeResponse<T> {
    ok: bool,
    data: Option<T>,
    error: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct BackendHealth {
    version: String,
    pid: u32,
    status: String,
    protocol_version: u32,
    backend_owner: String,
    model: String,
    language: String,
    device: String,
    uptime_seconds: f64,
}

#[derive(Clone, Debug, Serialize)]
struct BackendStatus {
    status: String,
    owned: bool,
    message: String,
    log_path: String,
    health: Option<BackendHealth>,
    launch_kind: Option<String>,
    starting_seconds: Option<f64>,
    last_error: Option<String>,
}

#[derive(Debug, Default)]
struct BackendManager {
    child: Option<ManagedBackendChild>,
    last_error: Option<String>,
    launch_kind: Option<String>,
    started_at: Option<Instant>,
}

impl BackendManager {
    fn owned(&self) -> bool {
        self.child.is_some()
    }

    fn refresh_child(&mut self) {
        if let Some(child) = self.child.as_mut() {
            match child {
                ManagedBackendChild::Python(child) => match child.try_wait() {
                    Ok(Some(status)) => {
                        self.last_error = Some(format!(
                            "Backend process exited before it became healthy: {status}"
                        ));
                        self.child = None;
                        self.launch_kind = None;
                        self.started_at = None;
                    }
                    Ok(None) => {}
                    Err(error) => {
                        self.last_error =
                            Some(format!("Could not inspect backend process: {error}"));
                        self.child = None;
                        self.launch_kind = None;
                        self.started_at = None;
                    }
                },
                ManagedBackendChild::Sidecar(_) => {}
            }
        }
    }

    fn take_and_kill_child(&mut self) {
        if let Some(child) = self.child.take() {
            match child {
                ManagedBackendChild::Python(mut child) => {
                    let _ = child.kill();
                }
                ManagedBackendChild::Sidecar(child) => {
                    let _ = child.kill();
                }
            }
        }
        self.launch_kind = None;
        self.started_at = None;
    }
}

#[tauri::command]
async fn bridge_call(request: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || bridge_call_blocking(request))
        .await
        .map_err(|error| error.to_string())?
}

fn bridge_call_blocking(request: String) -> Result<String, String> {
    let address = format!("{CONTROL_HOST}:{CONTROL_PORT}");
    let mut stream = TcpStream::connect(address).map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(CONTROL_TIMEOUT))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(CONTROL_TIMEOUT))
        .map_err(|error| error.to_string())?;
    stream
        .write_all(request.as_bytes())
        .and_then(|_| stream.write_all(b"\n"))
        .map_err(|error| error.to_string())?;

    let mut reader = BufReader::new(stream);
    let mut response = String::new();
    reader
        .read_line(&mut response)
        .map_err(|error| error.to_string())?;

    let trimmed = response.trim().to_string();
    if trimmed.is_empty() {
        return Err("Local bridge returned an empty response.".to_string());
    }
    Ok(trimmed)
}

fn bridge_json_call<T>(cmd: &str) -> Result<T, String>
where
    T: for<'de> Deserialize<'de>,
{
    let request = serde_json::json!({ "cmd": cmd, "args": {} }).to_string();
    let response_text = bridge_call_blocking(request)?;
    let response: BridgeResponse<T> = serde_json::from_str(&response_text)
        .map_err(|error| format!("Local bridge returned invalid JSON: {error}"))?;
    if !response.ok {
        return Err(response
            .error
            .unwrap_or_else(|| "Local bridge request failed.".to_string()));
    }
    response
        .data
        .ok_or_else(|| "Local bridge returned no data.".to_string())
}

fn health_from_bridge() -> Result<BackendHealth, String> {
    bridge_json_call("health")
}

fn backend_sidecar_args() -> [&'static str; 1] {
    ["--api"]
}

fn choose_backend_launch_strategy(
    debug_build: bool,
    sidecar_available: bool,
    python_available: bool,
) -> BackendLaunchStrategy {
    if sidecar_available {
        return BackendLaunchStrategy::Sidecar;
    }
    if debug_build && python_available {
        return BackendLaunchStrategy::PythonFallback;
    }
    BackendLaunchStrategy::MissingRequiredSidecar
}

fn repo_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(root) = manifest_dir
        .parent()
        .and_then(|desktop_dir| desktop_dir.parent())
    {
        root.to_path_buf()
    } else {
        manifest_dir
    }
}

fn fallback_root() -> PathBuf {
    PathBuf::from(r"C:\local-dictation")
}

fn sidecar_source_binary_path() -> PathBuf {
    repo_root()
        .join("desktop")
        .join("src-tauri")
        .join("binaries")
        .join(format!(
            "{SIDECAR_BINARY_NAME}-{}.exe",
            option_env!("TAURI_ENV_TARGET_TRIPLE").unwrap_or("x86_64-pc-windows-msvc")
        ))
}

fn log_path() -> String {
    let path = repo_root().join("dictation_debug.log");
    if path.parent().is_some_and(|parent| parent.exists()) {
        return path.to_string_lossy().to_string();
    }
    fallback_root()
        .join("dictation_debug.log")
        .to_string_lossy()
        .to_string()
}

fn clamp_i32(value: i32, minimum: i32, maximum: i32) -> i32 {
    if maximum < minimum {
        return minimum;
    }
    value.clamp(minimum, maximum)
}

fn default_bubble_position(work_area: WorkArea, window_size: i32, margin: i32) -> WindowPoint {
    WindowPoint::new(
        work_area.right() - window_size - margin,
        work_area.bottom() - window_size - margin,
    )
}

fn clamp_window_position(
    point: WindowPoint,
    work_area: WorkArea,
    size: WindowSize,
    margin: i32,
) -> WindowPoint {
    WindowPoint::new(
        clamp_i32(
            point.x,
            work_area.x + margin,
            work_area.right() - size.width - margin,
        ),
        clamp_i32(
            point.y,
            work_area.y + margin,
            work_area.bottom() - size.height - margin,
        ),
    )
}

fn saved_bubble_position_is_usable(
    point: WindowPoint,
    _work_area: WorkArea,
    _window_size: i32,
) -> bool {
    if point.x == 0 && point.y == 0 {
        return false;
    }
    true
}

fn resolve_bubble_position(
    saved: Option<WindowPoint>,
    work_area: WorkArea,
    window_size: i32,
    margin: i32,
) -> WindowPoint {
    match saved {
        Some(point) if saved_bubble_position_is_usable(point, work_area, window_size) => {
            clamp_window_position(
                point,
                work_area,
                WindowSize::new(window_size, window_size),
                margin,
            )
        }
        _ => default_bubble_position(work_area, window_size, margin),
    }
}

fn place_popover_for_bubble(
    bubble_position: WindowPoint,
    bubble_size: WindowSize,
    popover_size: WindowSize,
    work_area: WorkArea,
    margin: i32,
) -> PopoverPlacement {
    let bubble_center_x = bubble_position.x + bubble_size.width / 2;
    let above_bubble_y = bubble_position.y - popover_size.height - 12;
    let below_bubble_y = bubble_position.y + bubble_size.height + 12;
    let preferred_y = if above_bubble_y >= work_area.y + margin {
        above_bubble_y
    } else {
        below_bubble_y
    };
    let preferred_x = bubble_center_x - popover_size.width + 36;
    let position = clamp_window_position(
        WindowPoint::new(preferred_x, preferred_y),
        work_area,
        popover_size,
        margin,
    );
    let tail_x = clamp_i32(
        bubble_center_x - position.x,
        POPOVER_TAIL_SAFE_MARGIN,
        popover_size.width - POPOVER_TAIL_SAFE_MARGIN,
    );

    PopoverPlacement { position, tail_x }
}

fn work_area_from_monitor(monitor: &tauri::Monitor) -> WorkArea {
    let area = monitor.work_area();
    WorkArea::new(
        area.position.x,
        area.position.y,
        area.size.width as i32,
        area.size.height as i32,
    )
}

fn work_area_for_window(window: &tauri::WebviewWindow) -> WorkArea {
    window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten())
        .map(|monitor| work_area_from_monitor(&monitor))
        .unwrap_or_else(|| WorkArea::new(0, 0, 1920, 1080))
}

fn hide_windows(app: &tauri::AppHandle, labels: &[&str]) {
    for label in labels {
        if let Some(window) = app.get_webview_window(label) {
            let _ = window.hide();
        }
    }
}

fn show_main_window_with_route(
    app: &tauri::AppHandle,
    route: Option<String>,
) -> Result<(), String> {
    let main = webview_window(app, MAIN_WINDOW_LABEL)?;
    main.show().map_err(|error| error.to_string())?;
    let _ = main.set_focus();
    if let Some(route) = route {
        app.emit_to(MAIN_WINDOW_LABEL, "local-dictation:navigate", route)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn stop_owned_backend(manager: &Mutex<BackendManager>) -> Result<(), String> {
    let mut manager = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    if manager.owned() {
        let _ = bridge_json_call::<serde_json::Value>("shutdown-backend");
        manager.take_and_kill_child();
    }
    Ok(())
}

fn quit_app_handle(app: &tauri::AppHandle) -> Result<(), String> {
    hide_windows(
        app,
        &[
            BUBBLE_WINDOW_LABEL,
            QUICK_POPOVER_WINDOW_LABEL,
            MAIN_WINDOW_LABEL,
        ],
    );
    let manager = app.state::<Mutex<BackendManager>>();
    stop_owned_backend(&manager)?;
    app.exit(0);
    Ok(())
}

fn setup_tray(app: &tauri::App) -> Result<(), String> {
    let menu = MenuBuilder::new(app)
        .text("show-app", "Show app")
        .text("show-bubble", "Show bubble")
        .text("hide-bubble", "Hide bubble")
        .separator()
        .text("quit", "Quit")
        .build()
        .map_err(|error| error.to_string())?;

    let mut tray = TrayIconBuilder::with_id("local-dictation")
        .tooltip("Local Dictation")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show-app" => {
                let _ = show_main_window_with_route(app, None);
            }
            "show-bubble" => {
                let _ = bubble_show(app.clone(), None, None);
            }
            "hide-bubble" => {
                let _ = bubble_hide(app.clone());
            }
            "quit" => {
                let _ = quit_app_handle(app);
            }
            _ => {}
        });

    if let Some(icon) = app.default_window_icon().cloned() {
        tray = tray.icon(icon);
    }

    tray.build(app).map_err(|error| error.to_string())?;
    Ok(())
}

fn python_candidates() -> Vec<PathBuf> {
    let root = repo_root();
    let fallback = fallback_root();
    vec![
        root.join(r".venv\Scripts\pythonw.exe"),
        fallback.join(r".venv\Scripts\pythonw.exe"),
        root.join(r".venv\Scripts\python.exe"),
        fallback.join(r".venv\Scripts\python.exe"),
    ]
}

fn python_executable() -> Result<PathBuf, String> {
    python_candidates()
        .into_iter()
        .find(|path| path.exists())
        .ok_or_else(|| {
            "Could not find .venv\\Scripts\\pythonw.exe in C:\\local-dictation-tauri or C:\\local-dictation."
                .to_string()
        })
}

fn backend_script() -> Result<PathBuf, String> {
    let root_script = repo_root().join("bubble_dictate.py");
    if root_script.exists() {
        return Ok(root_script);
    }

    let fallback_script = fallback_root().join("bubble_dictate.py");
    if fallback_script.exists() {
        return Ok(fallback_script);
    }

    Err(
        "Could not find bubble_dictate.py in the migration worktree or C:\\local-dictation."
            .to_string(),
    )
}

fn backend_workdir(script: &Path) -> PathBuf {
    script.parent().map(PathBuf::from).unwrap_or_else(repo_root)
}

fn status_ready(health: BackendHealth, owned: bool, launch_kind: Option<String>) -> BackendStatus {
    BackendStatus {
        status: "ready".to_string(),
        owned,
        message: "Local backend ready.".to_string(),
        log_path: log_path(),
        health: Some(health),
        launch_kind: launch_kind
            .or_else(|| Some(if owned { "managed" } else { "existing" }.to_string())),
        starting_seconds: None,
        last_error: None,
    }
}

fn status_not_running(message: impl Into<String>) -> BackendStatus {
    BackendStatus {
        status: "not_running".to_string(),
        owned: false,
        message: message.into(),
        log_path: log_path(),
        health: None,
        launch_kind: None,
        starting_seconds: None,
        last_error: None,
    }
}

fn status_starting(manager: &BackendManager) -> BackendStatus {
    let starting_seconds = manager
        .started_at
        .map(|started_at| started_at.elapsed().as_secs_f64());
    let message = if starting_seconds.unwrap_or_default() >= BACKEND_SLOW_START_SECONDS as f64 {
        "Backend is still loading the speech model. This can be slow on first CUDA start."
    } else {
        "Backend starting. The speech model may still be loading."
    };

    BackendStatus {
        status: "starting".to_string(),
        owned: manager.owned(),
        message: message.to_string(),
        log_path: log_path(),
        health: None,
        launch_kind: manager.launch_kind.clone(),
        starting_seconds,
        last_error: manager.last_error.clone(),
    }
}

fn status_error(message: impl Into<String>) -> BackendStatus {
    let message = message.into();
    BackendStatus {
        status: "error".to_string(),
        owned: false,
        message: message.clone(),
        log_path: log_path(),
        health: None,
        launch_kind: None,
        starting_seconds: None,
        last_error: Some(message),
    }
}

fn status_from_health_error(error: &str) -> BackendStatus {
    if error.contains("Local bridge returned invalid JSON") {
        return BackendStatus {
            status: "unhealthy".to_string(),
            owned: false,
            message: "A legacy Python backend is already using the Local Dictation port, but it does not support the JSON health command. Close the old backend before starting the packaged backend from Tauri.".to_string(),
            log_path: log_path(),
            health: None,
            launch_kind: Some("existing".to_string()),
            starting_seconds: None,
            last_error: Some(error.to_string()),
        };
    }

    status_not_running("Backend not running.")
}

fn current_backend_status(manager: &mut BackendManager) -> BackendStatus {
    match health_from_bridge() {
        Ok(health) => {
            manager.last_error = None;
            return status_ready(
                health,
                manager.owned(),
                if manager.owned() {
                    manager.launch_kind.clone()
                } else {
                    Some("existing".to_string())
                },
            );
        }
        Err(error) => {
            let unhealthy = status_from_health_error(&error);
            if unhealthy.status == "unhealthy" {
                return unhealthy;
            }
        }
    }

    manager.refresh_child();

    if manager.owned() {
        return status_starting(manager);
    }

    if let Some(error) = manager.last_error.clone() {
        return status_error(error);
    }

    status_not_running("Backend not running.")
}

fn spawn_backend_process() -> Result<ManagedBackendChild, String> {
    let python = python_executable()?;
    let script = backend_script()?;
    let workdir = backend_workdir(&script);

    let mut command = Command::new(python);
    command
        .arg(script)
        .arg("--api")
        .current_dir(workdir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
        .spawn()
        .map(ManagedBackendChild::Python)
        .map_err(|error| format!("Failed to start Python backend: {error}"))
}

fn spawn_sidecar_backend(app: &tauri::AppHandle) -> Result<ManagedBackendChild, String> {
    let (_rx, child) = app
        .shell()
        .sidecar(SIDECAR_BINARY_NAME)
        .map_err(|error| format!("Could not prepare backend sidecar: {error}"))?
        .args(backend_sidecar_args())
        .spawn()
        .map_err(|error| format!("Failed to start backend sidecar: {error}"))?;
    Ok(ManagedBackendChild::Sidecar(child))
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<(ManagedBackendChild, String), String> {
    let debug_build = cfg!(debug_assertions);
    let sidecar_available = !debug_build || sidecar_source_binary_path().exists();
    let python_available = python_executable().is_ok();

    match choose_backend_launch_strategy(debug_build, sidecar_available, python_available) {
        BackendLaunchStrategy::Sidecar => {
            spawn_sidecar_backend(app).map(|child| (child, "sidecar".to_string()))
        }
        BackendLaunchStrategy::PythonFallback => {
            spawn_backend_process().map(|child| (child, "python-fallback".to_string()))
        }
        BackendLaunchStrategy::MissingRequiredSidecar => Err(format!(
            "Backend sidecar is required for packaged builds. Build it first with npm run build:backend. Expected source binary: {}",
            sidecar_source_binary_path().to_string_lossy()
        )),
    }
}

fn lock_manager<'a>(
    manager: &'a tauri::State<'_, Mutex<BackendManager>>,
) -> Result<std::sync::MutexGuard<'a, BackendManager>, String> {
    manager
        .lock()
        .map_err(|_| "Backend manager lock is poisoned.".to_string())
}

#[tauri::command]
fn backend_health() -> Result<BackendHealth, String> {
    health_from_bridge()
}

#[tauri::command]
fn backend_status(
    manager: tauri::State<'_, Mutex<BackendManager>>,
) -> Result<BackendStatus, String> {
    let mut manager = lock_manager(&manager)?;
    Ok(current_backend_status(&mut manager))
}

#[tauri::command]
async fn backend_start(app: tauri::AppHandle) -> Result<BackendStatus, String> {
    {
        let manager_state = app.state::<Mutex<BackendManager>>();
        let mut manager = lock_manager(&manager_state)?;

        if let Ok(health) = health_from_bridge() {
            return Ok(status_ready(
                health,
                manager.owned(),
                if manager.owned() {
                    manager.launch_kind.clone()
                } else {
                    Some("existing".to_string())
                },
            ));
        }
        if let Err(error) = health_from_bridge() {
            let unhealthy = status_from_health_error(&error);
            if unhealthy.status == "unhealthy" {
                return Ok(unhealthy);
            }
        }

        manager.refresh_child();
        if manager.owned() {
            return Ok(status_starting(&manager));
        }
    }

    let app_for_spawn = app.clone();
    let spawn_result = tauri::async_runtime::spawn_blocking(move || spawn_backend(&app_for_spawn))
        .await
        .map_err(|error| format!("Backend launcher task failed: {error}"))?;

    let (child, launch_kind) = spawn_result?;
    let manager_state = app.state::<Mutex<BackendManager>>();
    let mut manager = lock_manager(&manager_state)?;
    manager.child = Some(child);
    manager.launch_kind = Some(launch_kind);
    manager.started_at = Some(Instant::now());
    manager.last_error = None;

    Ok(status_starting(&manager))
}

#[tauri::command]
fn backend_stop(manager: tauri::State<'_, Mutex<BackendManager>>) -> Result<BackendStatus, String> {
    let mut manager = lock_manager(&manager)?;

    if !manager.owned() {
        if let Ok(health) = health_from_bridge() {
            return Ok(BackendStatus {
                status: "ready".to_string(),
                owned: false,
                message: "Existing backend is running. It was not started by this Tauri session, so it was left running.".to_string(),
                log_path: log_path(),
                health: Some(health),
                launch_kind: Some("existing".to_string()),
                starting_seconds: None,
                last_error: None,
            });
        }
        return Ok(status_not_running("Backend not running."));
    }

    let _ = bridge_json_call::<serde_json::Value>("shutdown-backend");

    for _ in 0..BACKEND_STOP_ATTEMPTS {
        thread::sleep(BACKEND_START_POLL);
        manager.refresh_child();
        if !manager.owned() {
            return Ok(status_not_running("Backend stopped."));
        }
    }

    manager.take_and_kill_child();

    Ok(status_not_running("Backend stopped."))
}

#[tauri::command]
async fn backend_restart(
    app: tauri::AppHandle,
    manager: tauri::State<'_, Mutex<BackendManager>>,
) -> Result<BackendStatus, String> {
    {
        let mut manager = lock_manager(&manager)?;
        if manager.owned() {
            let _ = bridge_json_call::<serde_json::Value>("shutdown-backend");
            manager.take_and_kill_child();
        }
    }

    backend_start(app).await
}

fn webview_window(app: &tauri::AppHandle, label: &str) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window(label)
        .ok_or_else(|| format!("Window not found: {label}"))
}

#[tauri::command]
fn bubble_show(app: tauri::AppHandle, x: Option<i32>, y: Option<i32>) -> Result<(), String> {
    let bubble = webview_window(&app, BUBBLE_WINDOW_LABEL)?;
    let work_area = work_area_for_window(&bubble);
    let saved = match (x, y) {
        (Some(x), Some(y)) => Some(WindowPoint::new(x, y)),
        _ => None,
    };
    let position =
        resolve_bubble_position(saved, work_area, BUBBLE_WINDOW_SIZE, WINDOW_SAFE_MARGIN);
    bubble
        .set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(
            position.x, position.y,
        )))
        .map_err(|error| error.to_string())?;
    bubble.show().map_err(|error| error.to_string())
}

#[tauri::command]
fn bubble_hide(app: tauri::AppHandle) -> Result<(), String> {
    webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?
        .hide()
        .map_err(|error| error.to_string())?;
    webview_window(&app, BUBBLE_WINDOW_LABEL)?
        .hide()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn quick_popover_show(app: tauri::AppHandle) -> Result<(), String> {
    let bubble = webview_window(&app, BUBBLE_WINDOW_LABEL)?;
    let popover = webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?;
    if let Ok(position) = bubble.outer_position() {
        let placement = place_popover_for_bubble(
            WindowPoint::new(position.x, position.y),
            WindowSize::new(BUBBLE_WINDOW_SIZE, BUBBLE_WINDOW_SIZE),
            WindowSize::new(QUICK_POPOVER_WIDTH, QUICK_POPOVER_HEIGHT),
            work_area_for_window(&bubble),
            WINDOW_SAFE_MARGIN,
        );
        popover
            .set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(
                placement.position.x,
                placement.position.y,
            )))
            .map_err(|error| error.to_string())?;
        app.emit_to(
            QUICK_POPOVER_WINDOW_LABEL,
            "local-dictation:popover-placement",
            PopoverPlacementEvent {
                tail_x: placement.tail_x,
            },
        )
        .map_err(|error| error.to_string())?;
    }
    popover.show().map_err(|error| error.to_string())
}

#[tauri::command]
fn quick_popover_hide(app: tauri::AppHandle) -> Result<(), String> {
    webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?
        .hide()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn main_window_show(app: tauri::AppHandle, route: Option<String>) -> Result<(), String> {
    show_main_window_with_route(&app, route)
}

#[tauri::command]
fn app_hide_to_tray(app: tauri::AppHandle) -> Result<(), String> {
    hide_windows(
        &app,
        &[
            MAIN_WINDOW_LABEL,
            BUBBLE_WINDOW_LABEL,
            QUICK_POPOVER_WINDOW_LABEL,
        ],
    );
    Ok(())
}

#[tauri::command]
fn app_quit(
    app: tauri::AppHandle,
    manager: tauri::State<'_, Mutex<BackendManager>>,
) -> Result<(), String> {
    hide_windows(
        &app,
        &[
            BUBBLE_WINDOW_LABEL,
            QUICK_POPOVER_WINDOW_LABEL,
            MAIN_WINDOW_LABEL,
        ],
    );
    stop_owned_backend(&manager)?;
    app.exit(0);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(BackendManager::default()))
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            let _ = show_main_window_with_route(app, None);
        }))
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == MAIN_WINDOW_LABEL {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    match main_window_close_action() {
                        MainWindowCloseAction::HideMainWindow => {
                            let _ = window.hide();
                        }
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            bridge_call,
            backend_health,
            backend_status,
            backend_start,
            backend_stop,
            backend_restart,
            bubble_show,
            bubble_hide,
            quick_popover_show,
            quick_popover_hide,
            main_window_show,
            app_hide_to_tray,
            app_quit
        ])
        .run(tauri::generate_context!())
        .expect("error while running Local Dictation desktop shell");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_launch_strategy_uses_sidecar_before_python_fallback() {
        assert_eq!(
            choose_backend_launch_strategy(true, true, true),
            BackendLaunchStrategy::Sidecar
        );
        assert_eq!(
            choose_backend_launch_strategy(true, false, true),
            BackendLaunchStrategy::PythonFallback
        );
        assert_eq!(
            choose_backend_launch_strategy(false, false, true),
            BackendLaunchStrategy::MissingRequiredSidecar
        );
    }

    #[test]
    fn sidecar_launch_uses_expected_binary_name_and_api_args() {
        assert_eq!(SIDECAR_BINARY_NAME, "local-dictation-backend");
        assert_eq!(backend_sidecar_args(), ["--api"]);
    }

    #[test]
    fn invalid_json_health_response_is_reported_as_legacy_backend() {
        let status = status_from_health_error(
            "Local bridge returned invalid JSON: expected value at line 1 column 1",
        );

        assert_eq!(status.status, "unhealthy");
        assert!(!status.owned);
        assert!(status.message.contains("legacy Python backend"));
    }

    #[test]
    fn starting_status_reports_launch_metadata_without_waiting_for_health() {
        let mut manager = BackendManager::default();
        manager.launch_kind = Some("python-fallback".to_string());
        manager.started_at = Some(Instant::now() - Duration::from_secs(4));

        let status = status_starting(&manager);

        assert_eq!(status.status, "starting");
        assert_eq!(status.launch_kind.as_deref(), Some("python-fallback"));
        assert!(status.starting_seconds.unwrap_or_default() >= 4.0);
        assert!(status.message.contains("speech model may still be loading"));
    }

    #[test]
    fn slow_starting_status_explains_cuda_model_load() {
        let mut manager = BackendManager::default();
        manager.launch_kind = Some("sidecar".to_string());
        manager.started_at = Some(Instant::now() - Duration::from_secs(46));

        let status = status_starting(&manager);

        assert_eq!(status.launch_kind.as_deref(), Some("sidecar"));
        assert!(status.message.contains("slow on first CUDA start"));
    }

    #[test]
    fn main_window_close_hides_main_window_instead_of_quitting() {
        assert_eq!(
            main_window_close_action(),
            MainWindowCloseAction::HideMainWindow
        );
    }

    #[test]
    fn bubble_position_defaults_near_bottom_right_when_missing_or_zero() {
        let work_area = WorkArea::new(0, 0, 1920, 1080);

        assert_eq!(
            resolve_bubble_position(None, work_area, 56, 16),
            WindowPoint::new(1848, 1008)
        );
        assert_eq!(
            resolve_bubble_position(Some(WindowPoint::new(0, 0)), work_area, 56, 16),
            WindowPoint::new(1848, 1008)
        );
    }

    #[test]
    fn bubble_position_clamps_offscreen_values_inside_work_area() {
        let work_area = WorkArea::new(100, 50, 1200, 800);

        assert_eq!(
            resolve_bubble_position(Some(WindowPoint::new(-400, 10)), work_area, 56, 16),
            WindowPoint::new(116, 66)
        );
        assert_eq!(
            resolve_bubble_position(Some(WindowPoint::new(5000, 4000)), work_area, 56, 16),
            WindowPoint::new(1228, 778)
        );
    }

    #[test]
    fn popover_position_stays_visible_near_left_edge_and_keeps_tail_on_bubble() {
        let work_area = WorkArea::new(0, 0, 1920, 1080);
        let placement = place_popover_for_bubble(
            WindowPoint::new(8, 900),
            WindowSize::new(56, 56),
            WindowSize::new(QUICK_POPOVER_WIDTH, QUICK_POPOVER_HEIGHT),
            work_area,
            16,
        );

        assert_eq!(placement.position.x, 16);
        assert!(placement.position.y >= 0);
        assert!(placement.tail_x >= 16);
        assert!(placement.tail_x <= QUICK_POPOVER_WIDTH - 16);
    }

    #[test]
    fn popover_position_stays_visible_near_right_edge_and_keeps_tail_on_bubble() {
        let work_area = WorkArea::new(0, 0, 1920, 1080);
        let placement = place_popover_for_bubble(
            WindowPoint::new(1850, 900),
            WindowSize::new(56, 56),
            WindowSize::new(QUICK_POPOVER_WIDTH, QUICK_POPOVER_HEIGHT),
            work_area,
            16,
        );

        assert!(placement.position.x + QUICK_POPOVER_WIDTH <= 1904);
        assert!(placement.tail_x >= 16);
        assert!(placement.tail_x <= QUICK_POPOVER_WIDTH - 16);
    }
}
