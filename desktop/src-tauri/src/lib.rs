use std::{
    ffi::OsString,
    io::{Read, Write},
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use tauri::{menu::MenuBuilder, tray::TrayIconBuilder, Emitter, Manager, WindowEvent};
use tauri_plugin_dialog::DialogExt;

#[cfg(windows)]
mod windows_native;

const CONTROL_PORT: u16 = 49_731;
const CONTROL_TIMEOUT: Duration = Duration::from_secs(2);
const RESOURCE_LOAD_TIMEOUT: Duration = Duration::from_secs(120);
const CONTROL_PROTOCOL_VERSION: u32 = 4;
const MAX_REQUEST_BYTES: usize = 65_536;
const MAX_RESPONSE_BYTES: usize = 1_048_576;
const BACKEND_START_POLL: Duration = Duration::from_millis(250);
const BACKEND_STOP_ATTEMPTS: usize = 12;
const BACKEND_SLOW_START_SECONDS: u64 = 45;
const BACKEND_START_TIMEOUT: Duration = Duration::from_secs(120);
const BACKEND_KILL_TIMEOUT: Duration = Duration::from_secs(5);
const SIDECAR_BINARY_NAME: &str = "local-dictation-backend";
const MAIN_WINDOW_LABEL: &str = "main";
const BUBBLE_WINDOW_LABEL: &str = "bubble";
const QUICK_POPOVER_WINDOW_LABEL: &str = "quick-popover";
const WINDOW_SAFE_MARGIN: i32 = 16;
const POPOVER_TAIL_SAFE_MARGIN: i32 = 16;

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
    tail_x: f64,
}

#[derive(Debug, PartialEq, Eq)]
enum BackendLaunchStrategy {
    Sidecar,
    PythonFallback,
    MissingRequiredSidecar,
}

#[derive(Debug)]
struct ManagedBackendChild {
    #[cfg(windows)]
    tree: windows_native::ManagedTree,
    #[cfg(not(windows))]
    process: Mutex<std::process::Child>,
}

impl ManagedBackendChild {
    fn running(&self) -> Result<bool, String> {
        #[cfg(windows)]
        {
            self.tree.active_processes().map(|count| count > 0)
        }
        #[cfg(not(windows))]
        {
            self.process
                .lock()
                .map_err(|error| error.to_string())?
                .try_wait()
                .map(|exit| exit.is_none())
                .map_err(|error| error.to_string())
        }
    }

    fn exit_description(&self) -> String {
        #[cfg(windows)]
        {
            self.tree.exit_description().unwrap_or_else(|error| error)
        }
        #[cfg(not(windows))]
        {
            "process exited".to_string()
        }
    }

    fn terminate(&self) -> Result<(), String> {
        #[cfg(windows)]
        {
            self.tree.terminate()
        }
        #[cfg(not(windows))]
        {
            self.process
                .lock()
                .map_err(|error| error.to_string())?
                .kill()
                .map_err(|error| error.to_string())
        }
    }
}

#[cfg(not(windows))]
impl Drop for ManagedBackendChild {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    launch_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    loading: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    recording_ready: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    error: Option<String>,
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum LifecycleOperation {
    Start,
    Stop,
    Restart,
    Quit,
}

#[derive(Clone, Debug, Default)]
struct BackendManager {
    child: Option<Arc<ManagedBackendChild>>,
    launch_id: Option<String>,
    last_error: Option<String>,
    launch_kind: Option<String>,
    started_at: Option<Instant>,
    reached_health: bool,
    operation: Option<LifecycleOperation>,
    quitting: bool,
}

impl BackendManager {
    fn owned(&self) -> bool {
        self.child.is_some()
    }

    fn matches_health(&self, health: &BackendHealth) -> bool {
        self.owned()
            && launch_identity_matches(self.launch_id.as_deref(), health.launch_id.as_deref())
    }

    fn clear_launch(&mut self) {
        self.child = None;
        self.launch_id = None;
        self.launch_kind = None;
        self.started_at = None;
        self.reached_health = false;
    }
}

fn launch_identity_matches(expected: Option<&str>, observed: Option<&str>) -> bool {
    expected.is_some_and(|expected| !expected.is_empty() && Some(expected) == observed)
}

#[derive(Debug)]
struct BridgeError {
    message: String,
    unavailable: bool,
}

impl BridgeError {
    fn failure(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            unavailable: false,
        }
    }
}

#[tauri::command]
async fn bridge_call(request: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || bridge_call_blocking(request))
        .await
        .map_err(|error| error.to_string())?
}

fn bridge_call_blocking(request: String) -> Result<String, String> {
    let timeout = request_timeout(&request)?;
    bridge_request_at(control_address(), &request, timeout).map_err(|error| error.message)
}

fn control_address() -> SocketAddr {
    SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), CONTROL_PORT)
}

fn request_timeout(request: &str) -> Result<Duration, String> {
    if request.len() > MAX_REQUEST_BYTES || request.contains(['\r', '\n']) {
        return Err("Local bridge request exceeds its limit or contains a newline.".to_string());
    }
    let envelope: serde_json::Value = serde_json::from_str(request)
        .map_err(|error| format!("Local bridge request is invalid JSON: {error}"))?;
    match envelope.get("cmd").and_then(serde_json::Value::as_str) {
        Some("set-settings" | "retry-resources") => Ok(RESOURCE_LOAD_TIMEOUT),
        Some(_) => Ok(CONTROL_TIMEOUT),
        None => Err("Local bridge request requires a string command.".to_string()),
    }
}

fn bridge_request_at(
    address: SocketAddr,
    request: &str,
    timeout: Duration,
) -> Result<String, BridgeError> {
    if request.len() > MAX_REQUEST_BYTES {
        return Err(BridgeError::failure(
            "Local bridge request exceeds 65536 bytes.",
        ));
    }
    let deadline = Instant::now() + timeout;
    let mut stream =
        TcpStream::connect_timeout(&address, CONTROL_TIMEOUT.min(timeout)).map_err(|error| {
            BridgeError {
                // Windows can time out before reporting refusal on a closed
                // loopback port. A timeout after connection stays unhealthy.
                unavailable: matches!(
                    error.kind(),
                    std::io::ErrorKind::ConnectionRefused | std::io::ErrorKind::TimedOut
                ),
                message: format!("Could not connect to local bridge: {error}"),
            }
        })?;
    let mut outgoing = request.as_bytes().to_vec();
    outgoing.push(b'\n');
    let mut written = 0;
    let write_deadline = deadline.min(Instant::now() + CONTROL_TIMEOUT);
    while written < outgoing.len() {
        let remaining = write_deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(BridgeError::failure(
                "Local bridge write deadline exceeded.",
            ));
        }
        stream
            .set_write_timeout(Some(remaining))
            .map_err(|error| BridgeError::failure(error.to_string()))?;
        let count = stream
            .write(&outgoing[written..])
            .map_err(|error| BridgeError::failure(format!("Local bridge write failed: {error}")))?;
        if count == 0 {
            return Err(BridgeError::failure(
                "Local bridge closed during request write.",
            ));
        }
        written += count;
    }

    let mut response = Vec::new();
    let mut buffer = [0; 8192];
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(BridgeError::failure(
                "Local bridge response deadline exceeded.",
            ));
        }
        stream
            .set_read_timeout(Some(remaining))
            .map_err(|error| BridgeError::failure(error.to_string()))?;
        let count = stream
            .read(&mut buffer)
            .map_err(|error| BridgeError::failure(format!("Local bridge read failed: {error}")))?;
        if count == 0 {
            return Err(BridgeError::failure(
                "Local bridge closed before a complete response.",
            ));
        }
        let end = buffer[..count].iter().position(|byte| *byte == b'\n');
        let used = end.unwrap_or(count);
        if response.len() + used > MAX_RESPONSE_BYTES {
            return Err(BridgeError::failure(
                "Local bridge response exceeds 1048576 bytes.",
            ));
        }
        response.extend_from_slice(&buffer[..used]);
        if end.is_some() {
            let text = String::from_utf8(response).map_err(|error| {
                BridgeError::failure(format!("Local bridge response is not UTF-8: {error}"))
            })?;
            let text = text.trim().to_string();
            if text.is_empty() {
                return Err(BridgeError::failure(
                    "Local bridge returned an empty response.",
                ));
            }
            return Ok(text);
        }
    }
}

fn health_from_bridge() -> Result<BackendHealth, BridgeError> {
    let request = serde_json::json!({ "cmd": "health", "args": {} }).to_string();
    let response = bridge_request_at(control_address(), &request, CONTROL_TIMEOUT)?;
    parse_backend_health(&response)
}

fn parse_backend_health(response: &str) -> Result<BackendHealth, BridgeError> {
    let response: BridgeResponse<BackendHealth> =
        serde_json::from_str(response).map_err(|error| {
            BridgeError::failure(format!("Local bridge returned invalid JSON: {error}"))
        })?;
    if !response.ok {
        return Err(BridgeError::failure(
            response
                .error
                .unwrap_or_else(|| "Health request failed.".to_string()),
        ));
    }
    let health = response
        .data
        .ok_or_else(|| BridgeError::failure("Health response contains no data."))?;
    if health.protocol_version != CONTROL_PROTOCOL_VERSION {
        return Err(BridgeError::failure(format!(
            "Backend protocol {} is incompatible with this app (expected {}). Restart the matching backend.",
            health.protocol_version, CONTROL_PROTOCOL_VERSION
        )));
    }
    Ok(health)
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

fn runtime_data_root() -> PathBuf {
    std::env::var_os("LOCAL_DICTATION_DATA_DIR")
        .filter(|path| !path.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(r"C:\local-dictation"))
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
    runtime_data_root()
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

fn default_bubble_position(work_area: WorkArea, size: WindowSize, margin: i32) -> WindowPoint {
    WindowPoint::new(
        work_area.right() - size.width - margin,
        work_area.bottom() - size.height - margin,
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

fn saved_bubble_position_is_usable(point: WindowPoint) -> bool {
    if point.x == 0 && point.y == 0 {
        return false;
    }
    !(point.x <= -30_000 && point.y <= -30_000)
}

fn resolve_bubble_position(
    saved: Option<WindowPoint>,
    work_area: WorkArea,
    window_size: WindowSize,
    margin: i32,
) -> WindowPoint {
    match saved {
        Some(point) if saved_bubble_position_is_usable(point) => {
            clamp_window_position(point, work_area, window_size, margin)
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
    scale_factor: f64,
) -> PopoverPlacement {
    let bubble_center_x = bubble_position.x + bubble_size.width / 2;
    let gap = (12.0 * scale_factor).round() as i32;
    let above_bubble_y = bubble_position.y - popover_size.height - gap;
    let below_bubble_y = bubble_position.y + bubble_size.height + gap;
    let preferred_y = if above_bubble_y >= work_area.y + margin {
        above_bubble_y
    } else {
        below_bubble_y
    };
    let preferred_x = bubble_center_x - popover_size.width + (36.0 * scale_factor).round() as i32;
    let position = clamp_window_position(
        WindowPoint::new(preferred_x, preferred_y),
        work_area,
        popover_size,
        margin,
    );
    let tail_margin = (POPOVER_TAIL_SAFE_MARGIN as f64 * scale_factor).round() as i32;
    let tail_x = clamp_i32(
        bubble_center_x - position.x,
        tail_margin,
        popover_size.width - tail_margin,
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

fn select_work_area(point: WindowPoint, areas: &[WorkArea], fallback: WorkArea) -> WorkArea {
    if let Some(area) = areas.iter().find(|area| {
        point.x >= area.x && point.x < area.right() && point.y >= area.y && point.y < area.bottom()
    }) {
        return *area;
    }
    areas
        .iter()
        .copied()
        .min_by_key(|area| {
            let x = point.x.clamp(area.x, area.right());
            let y = point.y.clamp(area.y, area.bottom());
            let dx = i128::from(point.x) - i128::from(x);
            let dy = i128::from(point.y) - i128::from(y);
            dx * dx + dy * dy
        })
        .unwrap_or(fallback)
}

fn work_area_for_point(window: &tauri::WebviewWindow, point: WindowPoint) -> WorkArea {
    let areas = window
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .map(work_area_from_monitor)
        .collect::<Vec<_>>();
    select_work_area(point, &areas, work_area_for_window(window))
}

fn physical_window_size(window: &tauri::WebviewWindow) -> Result<WindowSize, String> {
    let size = window.outer_size().map_err(|error| error.to_string())?;
    Ok(WindowSize::new(size.width as i32, size.height as i32))
}

fn set_window_visibility(window: &tauri::WebviewWindow, visible: bool) -> Result<(), String> {
    if visible {
        window.show()
    } else {
        window.hide()
    }
    .map_err(|error| error.to_string())?;
    window
        .emit_to(window.label(), "local-dictation:window-visibility", visible)
        .map_err(|error| error.to_string())
}

fn hide_windows(app: &tauri::AppHandle, labels: &[&str]) {
    for label in labels {
        if let Some(window) = app.get_webview_window(label) {
            let _ = set_window_visibility(&window, false);
        }
    }
}

fn show_main_window_with_route(
    app: &tauri::AppHandle,
    route: Option<String>,
) -> Result<(), String> {
    let main = webview_window(app, MAIN_WINDOW_LABEL)?;
    main.unminimize().map_err(|error| error.to_string())?;
    set_window_visibility(&main, true)?;
    let _ = main.set_focus();
    if let Some(route) = route {
        app.emit_to(MAIN_WINDOW_LABEL, "local-dictation:navigate", route)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn prepare_quit(app: &tauri::AppHandle) -> Result<bool, String> {
    let manager = app.state::<Mutex<BackendManager>>();
    let mut state = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    if state.quitting {
        return Ok(false);
    }
    state.quitting = true;
    drop(state);
    hide_windows(
        app,
        &[
            BUBBLE_WINDOW_LABEL,
            QUICK_POPOVER_WINDOW_LABEL,
            MAIN_WINDOW_LABEL,
        ],
    );
    Ok(true)
}

fn quit_backend_blocking(app: tauri::AppHandle) -> Result<(), String> {
    let manager = app.state::<Mutex<BackendManager>>();
    let deadline = Instant::now() + Duration::from_secs(30);
    while !reserve_operation(&manager, LifecycleOperation::Quit)? {
        if Instant::now() >= deadline {
            let error =
                "The active backend operation did not finish before Quit's deadline.".to_string();
            if let Ok(mut state) = manager.lock() {
                state.last_error = Some(error.clone());
                state.quitting = false;
            }
            return Err(error);
        }
        thread::sleep(Duration::from_millis(50));
    }
    let guard = LifecycleGuard {
        app: app.clone(),
        operation: LifecycleOperation::Quit,
    };
    let result = stop_backend_blocking(&app).map(|_| ());
    drop(guard);
    if let Err(error) = &result {
        if let Ok(mut state) = manager.lock() {
            state.last_error = Some(error.clone());
            state.quitting = false;
        }
    } else {
        app.exit(0);
    }
    result
}

fn quit_app_handle(app: &tauri::AppHandle) -> Result<(), String> {
    if prepare_quit(app)? {
        let app = app.clone();
        tauri::async_runtime::spawn_blocking(move || quit_backend_blocking(app));
    }
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
    vec![
        root.join(r".venv\Scripts\pythonw.exe"),
        root.join(r".venv\Scripts\python.exe"),
    ]
}

fn python_executable() -> Result<PathBuf, String> {
    python_candidates()
        .into_iter()
        .find(|path| path.exists())
        .ok_or_else(|| {
            format!(
                "Could not find Python in {}\\.venv\\Scripts.",
                repo_root().display()
            )
        })
}

fn backend_script() -> Result<PathBuf, String> {
    let root_script = repo_root().join("backend").join("bubble_dictate.py");
    if root_script.exists() {
        return Ok(root_script);
    }

    Err(format!(
        "Backend source not found: {}",
        root_script.display()
    ))
}

fn backend_workdir(script: &Path) -> PathBuf {
    script.parent().map(PathBuf::from).unwrap_or_else(repo_root)
}

fn manager_snapshot(manager: &Mutex<BackendManager>) -> Result<BackendManager, String> {
    manager
        .lock()
        .map(|state| state.clone())
        .map_err(|_| "Backend manager lock poisoned.".to_string())
}

fn reserve_operation(
    manager: &Mutex<BackendManager>,
    operation: LifecycleOperation,
) -> Result<bool, String> {
    let mut state = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    if state.quitting && operation != LifecycleOperation::Quit {
        return Err("Local Dictation is quitting.".to_string());
    }
    if state.operation.is_some() {
        return Ok(false);
    }
    state.operation = Some(operation);
    Ok(true)
}

fn refresh_managed_launch(manager: &Mutex<BackendManager>) -> Result<BackendManager, String> {
    let snapshot = manager_snapshot(manager)?;
    if let Some(child) = snapshot.child.as_ref() {
        match child.running() {
            Ok(false) => {
                let description = child.exit_description();
                let mut state = manager
                    .lock()
                    .map_err(|_| "Backend manager lock poisoned.".to_string())?;
                if state.launch_id == snapshot.launch_id {
                    state.clear_launch();
                    state.last_error = Some(format!(
                        "Backend process exited {}: {description}",
                        if snapshot.reached_health {
                            "after becoming reachable"
                        } else {
                            "before becoming reachable"
                        }
                    ));
                }
            }
            Ok(true) => {}
            Err(error) => {
                let mut state = manager
                    .lock()
                    .map_err(|_| "Backend manager lock poisoned.".to_string())?;
                if state.launch_id == snapshot.launch_id {
                    state.last_error = Some(error);
                }
            }
        }
    }
    manager_snapshot(manager)
}

fn status_ready(health: BackendHealth, manager: &BackendManager) -> BackendStatus {
    let owned = manager.matches_health(&health);
    BackendStatus {
        status: "ready".to_string(),
        owned,
        message: if owned {
            "Local backend reachable."
        } else {
            "Existing local backend reachable."
        }
        .to_string(),
        log_path: log_path(),
        health: Some(health),
        launch_kind: if owned {
            manager.launch_kind.clone()
        } else {
            Some("existing".to_string())
        },
        starting_seconds: None,
        last_error: manager.last_error.clone(),
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
    let operation = manager.operation;
    let stopping = matches!(
        operation,
        Some(LifecycleOperation::Stop | LifecycleOperation::Restart | LifecycleOperation::Quit)
    );
    let timed_out = !stopping
        && manager
            .started_at
            .is_some_and(|started_at| started_at.elapsed() >= BACKEND_START_TIMEOUT);
    let message = if stopping {
        "Stopping the owned backend."
    } else if timed_out {
        "Backend did not become reachable within 120 seconds. Retry restarts the owned launch."
    } else if starting_seconds.unwrap_or_default() >= BACKEND_SLOW_START_SECONDS as f64 {
        "Backend is still starting. Open the log for initialization details."
    } else {
        "Backend starting. The control service is not reachable yet."
    };
    BackendStatus {
        status: if stopping {
            "stopping"
        } else if timed_out {
            "error"
        } else {
            "starting"
        }
        .to_string(),
        owned: manager.owned(),
        message: message.to_string(),
        log_path: log_path(),
        health: None,
        launch_kind: manager.launch_kind.clone(),
        starting_seconds,
        last_error: if timed_out {
            Some(message.to_string())
        } else {
            manager.last_error.clone()
        },
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

fn status_from_health_error(error: &BridgeError) -> BackendStatus {
    if error.unavailable {
        return status_not_running("Backend not running.");
    }
    BackendStatus {
        status: "unhealthy".to_string(),
        owned: false,
        message: format!(
            "A process on the local backend port is not compatible or did not respond: {}",
            error.message
        ),
        log_path: log_path(),
        health: None,
        launch_kind: Some("existing".to_string()),
        starting_seconds: None,
        last_error: Some(error.message.clone()),
    }
}

fn record_health(
    manager: &Mutex<BackendManager>,
    health: &BackendHealth,
) -> Result<BackendManager, String> {
    let mut state = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    if state.matches_health(health) {
        state.reached_health = true;
        state.last_error = None;
    } else if state.owned() {
        state.last_error = Some(
            "A different backend is using the local port. It is not owned by this app session."
                .to_string(),
        );
    }
    Ok(state.clone())
}

fn current_backend_status(manager: &Mutex<BackendManager>) -> Result<BackendStatus, String> {
    let snapshot = refresh_managed_launch(manager)?;
    if snapshot.operation.is_some() {
        return Ok(status_starting(&snapshot));
    }
    match health_from_bridge() {
        Ok(health) => {
            let snapshot = record_health(manager, &health)?;
            Ok(status_ready(health, &snapshot))
        }
        Err(error) if snapshot.owned() && error.unavailable => Ok(status_starting(&snapshot)),
        Err(error) if !error.unavailable => {
            let mut status = status_from_health_error(&error);
            status.owned = snapshot.owned();
            status.launch_kind = snapshot.launch_kind.or(status.launch_kind);
            Ok(status)
        }
        Err(_) => Ok(snapshot
            .last_error
            .map(status_error)
            .unwrap_or_else(|| status_not_running("Backend not running."))),
    }
}

fn sidecar_binary_path() -> Result<PathBuf, String> {
    let source = sidecar_source_binary_path();
    if cfg!(debug_assertions) && source.is_file() {
        return Ok(source);
    }
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let directory = executable
        .parent()
        .ok_or_else(|| "Native executable has no directory.".to_string())?;
    let path = directory.join(format!(
        "{SIDECAR_BINARY_NAME}{}",
        std::env::consts::EXE_SUFFIX
    ));
    if path.is_file() {
        Ok(path)
    } else {
        Err(format!("Backend sidecar not found: {}", path.display()))
    }
}

fn next_launch_id() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!(
        "{}-{timestamp:x}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    )
}

fn spawn_backend(
    app: &tauri::AppHandle,
    launch_id: &str,
) -> Result<(ManagedBackendChild, String), String> {
    let sidecar = sidecar_binary_path();
    let python = python_executable();
    let (executable, args, workdir, launch_kind) = match choose_backend_launch_strategy(
        cfg!(debug_assertions), sidecar.is_ok(), python.is_ok(),
    ) {
        BackendLaunchStrategy::Sidecar => {
            let executable = sidecar?;
            let workdir = executable.parent().map(PathBuf::from).ok_or_else(|| "Backend sidecar has no directory.".to_string())?;
            (executable, backend_sidecar_args().map(OsString::from).to_vec(), workdir, "sidecar")
        }
        BackendLaunchStrategy::PythonFallback => {
            let script = backend_script()?;
            let workdir = backend_workdir(&script);
            (python?, vec![script.into_os_string(), OsString::from("--api")], workdir, "python-fallback")
        }
        BackendLaunchStrategy::MissingRequiredSidecar => return Err(format!(
            "Backend sidecar is required for packaged builds. Build it with npm run build:backend. {}",
            sidecar.err().unwrap_or_default()
        )),
    };
    let owner_pid = std::process::id().to_string();
    let cuda_directory = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?
        .join("cuda")
        .to_string_lossy()
        .to_string();
    let environment = [
        ("LOCAL_DICTATION_LAUNCH_ID", launch_id),
        ("LOCAL_DICTATION_OWNER_PID", owner_pid.as_str()),
        ("LOCAL_DICTATION_CUDA_DIR", cuda_directory.as_str()),
    ];
    #[cfg(windows)]
    let child = ManagedBackendChild {
        tree: windows_native::ManagedTree::spawn(&executable, &args, &workdir, &environment)?,
    };
    #[cfg(not(windows))]
    let child = {
        use std::process::{Command, Stdio};
        let mut command = Command::new(executable);
        command
            .args(args)
            .current_dir(workdir)
            .envs(environment)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        ManagedBackendChild {
            process: Mutex::new(
                command
                    .spawn()
                    .map_err(|error| format!("Failed to start backend: {error}"))?,
            ),
        }
    };
    Ok((child, launch_kind.to_string()))
}

fn wait_for_owned_exit(child: &ManagedBackendChild, timeout: Duration) -> Result<bool, String> {
    let deadline = Instant::now() + timeout;
    loop {
        if !child.running()? {
            return Ok(true);
        }
        if Instant::now() >= deadline {
            return Ok(false);
        }
        thread::sleep(BACKEND_START_POLL.min(deadline.saturating_duration_since(Instant::now())));
    }
}

fn stop_managed_launch(
    manager: &Mutex<BackendManager>,
    snapshot: &BackendManager,
    health: Option<&BackendHealth>,
) -> Result<(), String> {
    let Some(child) = snapshot.child.as_ref() else {
        return Ok(());
    };
    if health.is_some_and(|health| snapshot.matches_health(health)) {
        let request = serde_json::json!({ "cmd": "shutdown-owned-backend", "args": { "launch_id": snapshot.launch_id } }).to_string();
        // Receiver validation is essential if another process has since taken the port.
        let _ = bridge_call_blocking(request);
    }
    if !wait_for_owned_exit(child, BACKEND_START_POLL * BACKEND_STOP_ATTEMPTS as u32)? {
        child.terminate()?;
        if !wait_for_owned_exit(child, BACKEND_KILL_TIMEOUT)? {
            return Err(
                "Owned backend tree did not exit after termination. Restart was not started."
                    .to_string(),
            );
        }
    }
    let mut state = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    if state.launch_id == snapshot.launch_id {
        state.clear_launch();
        state.last_error = None;
    }
    Ok(())
}

fn start_backend_blocking(app: &tauri::AppHandle) -> Result<BackendStatus, String> {
    let manager = app.state::<Mutex<BackendManager>>();
    let snapshot = refresh_managed_launch(&manager)?;
    match health_from_bridge() {
        Ok(health) => {
            let snapshot = record_health(&manager, &health)?;
            return Ok(status_ready(health, &snapshot));
        }
        Err(error) if !error.unavailable => return Ok(status_from_health_error(&error)),
        Err(_) if snapshot.owned() => {
            if !snapshot
                .started_at
                .is_some_and(|at| at.elapsed() >= BACKEND_START_TIMEOUT)
            {
                return Ok(status_starting(&snapshot));
            }
            stop_managed_launch(&manager, &snapshot, None)?;
        }
        Err(_) => {}
    }
    let launch_id = next_launch_id();
    let (child, launch_kind) = spawn_backend(app, &launch_id)?;
    let mut state = manager
        .lock()
        .map_err(|_| "Backend manager lock poisoned.".to_string())?;
    state.child = Some(Arc::new(child));
    state.launch_id = Some(launch_id);
    state.launch_kind = Some(launch_kind);
    state.started_at = Some(Instant::now());
    state.last_error = None;
    state.reached_health = false;
    Ok(status_starting(&state))
}

fn stop_backend_blocking(app: &tauri::AppHandle) -> Result<BackendStatus, String> {
    let manager = app.state::<Mutex<BackendManager>>();
    let snapshot = refresh_managed_launch(&manager)?;
    let health = health_from_bridge();
    stop_managed_launch(&manager, &snapshot, health.as_ref().ok())?;
    match health {
        Ok(health) if !snapshot.matches_health(&health) => {
            let mut status = status_ready(health, &BackendManager::default());
            status.message =
                "Existing backend was left running because this app did not launch it.".to_string();
            Ok(status)
        }
        Err(error) if !error.unavailable && !snapshot.owned() => {
            Ok(status_from_health_error(&error))
        }
        _ => Ok(status_not_running("Owned backend stopped.")),
    }
}

struct LifecycleGuard {
    app: tauri::AppHandle,
    operation: LifecycleOperation,
}

impl Drop for LifecycleGuard {
    fn drop(&mut self) {
        let manager = self.app.state::<Mutex<BackendManager>>();
        if let Ok(mut state) = manager.lock() {
            if state.operation == Some(self.operation) {
                state.operation = None;
            }
        };
    }
}

async fn run_lifecycle(
    app: tauri::AppHandle,
    operation: LifecycleOperation,
) -> Result<BackendStatus, String> {
    let manager = app.state::<Mutex<BackendManager>>();
    if !reserve_operation(&manager, operation)? {
        return Ok(status_starting(&manager_snapshot(&manager)?));
    }
    let guard = LifecycleGuard {
        app: app.clone(),
        operation,
    };
    let app_for_worker = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let _guard = guard;
        let result = match operation {
            LifecycleOperation::Start => start_backend_blocking(&app_for_worker),
            LifecycleOperation::Stop | LifecycleOperation::Quit => {
                stop_backend_blocking(&app_for_worker)
            }
            LifecycleOperation::Restart => stop_backend_blocking(&app_for_worker)
                .and_then(|_| start_backend_blocking(&app_for_worker)),
        };
        if let Err(error) = &result {
            let manager = app_for_worker.state::<Mutex<BackendManager>>();
            if let Ok(mut state) = manager.lock() {
                state.last_error = Some(error.clone());
            };
        }
        result
    })
    .await
    .map_err(|error| format!("Backend lifecycle task failed: {error}"))?;
    result
}

#[tauri::command]
async fn backend_health() -> Result<BackendHealth, String> {
    tauri::async_runtime::spawn_blocking(|| health_from_bridge().map_err(|error| error.message))
        .await
        .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn backend_status(app: tauri::AppHandle) -> Result<BackendStatus, String> {
    tauri::async_runtime::spawn_blocking(move || {
        current_backend_status(&app.state::<Mutex<BackendManager>>())
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn backend_start(app: tauri::AppHandle) -> Result<BackendStatus, String> {
    run_lifecycle(app, LifecycleOperation::Start).await
}

#[tauri::command]
async fn backend_stop(app: tauri::AppHandle) -> Result<BackendStatus, String> {
    run_lifecycle(app, LifecycleOperation::Stop).await
}

#[tauri::command]
async fn backend_restart(app: tauri::AppHandle) -> Result<BackendStatus, String> {
    run_lifecycle(app, LifecycleOperation::Restart).await
}
fn webview_window(app: &tauri::AppHandle, label: &str) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window(label)
        .ok_or_else(|| format!("Window not found: {label}"))
}

#[tauri::command]
fn bubble_show(app: tauri::AppHandle, x: Option<i32>, y: Option<i32>) -> Result<(), String> {
    let bubble = webview_window(&app, BUBBLE_WINDOW_LABEL)?;
    let saved = match (x, y) {
        (Some(x), Some(y)) => Some(WindowPoint::new(x, y)),
        _ => bubble
            .outer_position()
            .ok()
            .map(|position| WindowPoint::new(position.x, position.y)),
    };
    let area = saved
        .filter(|point| saved_bubble_position_is_usable(*point))
        .map(|point| work_area_for_point(&bubble, point))
        .unwrap_or_else(|| work_area_for_window(&bubble));
    let position = resolve_bubble_position(
        saved,
        area,
        physical_window_size(&bubble)?,
        WINDOW_SAFE_MARGIN,
    );
    bubble
        .set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(
            position.x, position.y,
        )))
        .map_err(|error| error.to_string())?;
    set_window_visibility(&bubble, true)
}

#[tauri::command]
fn bubble_hide(app: tauri::AppHandle) -> Result<(), String> {
    set_window_visibility(&webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?, false)?;
    set_window_visibility(&webview_window(&app, BUBBLE_WINDOW_LABEL)?, false)
}

fn position_quick_popover(app: &tauri::AppHandle) -> Result<(), String> {
    let bubble = webview_window(app, BUBBLE_WINDOW_LABEL)?;
    let popover = webview_window(app, QUICK_POPOVER_WINDOW_LABEL)?;
    let position = bubble.outer_position().map_err(|error| error.to_string())?;
    let position = WindowPoint::new(position.x, position.y);
    let scale = popover.scale_factor().map_err(|error| error.to_string())?;
    let placement = place_popover_for_bubble(
        position,
        physical_window_size(&bubble)?,
        physical_window_size(&popover)?,
        work_area_for_point(&bubble, position),
        WINDOW_SAFE_MARGIN,
        scale,
    );
    let current = popover
        .outer_position()
        .map_err(|error| error.to_string())?;
    if current.x != placement.position.x || current.y != placement.position.y {
        popover
            .set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(
                placement.position.x,
                placement.position.y,
            )))
            .map_err(|error| error.to_string())?;
    }
    app.emit_to(
        QUICK_POPOVER_WINDOW_LABEL,
        "local-dictation:popover-placement",
        PopoverPlacementEvent {
            tail_x: placement.tail_x as f64 / scale,
        },
    )
    .map_err(|error| error.to_string())
}

#[tauri::command]
fn quick_popover_show(app: tauri::AppHandle) -> Result<(), String> {
    position_quick_popover(&app)?;
    set_window_visibility(&webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?, true)
}

#[tauri::command]
fn quick_popover_hide(app: tauri::AppHandle) -> Result<(), String> {
    set_window_visibility(&webview_window(&app, QUICK_POPOVER_WINDOW_LABEL)?, false)
}

#[tauri::command]
fn current_window_visible(window: tauri::WebviewWindow) -> Result<bool, String> {
    Ok(window.is_visible().map_err(|error| error.to_string())?
        && !window.is_minimized().map_err(|error| error.to_string())?)
}

#[tauri::command]
async fn pick_export_folder(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
) -> Result<Option<String>, String> {
    if window.label() != MAIN_WINDOW_LABEL {
        return Err("Choose the export folder from the main Settings window.".to_string());
    }
    let (sender, mut receiver) = tauri::async_runtime::channel(1);
    app.dialog()
        .file()
        .set_parent(&window)
        .set_title("Choose export folder")
        .pick_folder(move |selection| {
            let _ = sender.try_send(selection);
        });
    let selection = receiver
        .recv()
        .await
        .ok_or_else(|| "Export folder picker closed unexpectedly.".to_string())?;
    selection
        .map(|path| {
            path.into_path()
                .map(|path| path.to_string_lossy().into_owned())
                .map_err(|error| error.to_string())
        })
        .transpose()
}

#[cfg(windows)]
fn guard_utility_window(window: &tauri::WebviewWindow) -> Result<(), String> {
    let hwnd = window.hwnd().map_err(|error| error.to_string())?;
    windows_native::guard_utility_window(hwnd.0 as _)
}

fn refresh_utility_geometry(window: &tauri::Window) {
    let app = window.app_handle();
    if window.label() == BUBBLE_WINDOW_LABEL {
        if let Some(bubble) = app.get_webview_window(BUBBLE_WINDOW_LABEL) {
            if let (Ok(position), Ok(size)) =
                (bubble.outer_position(), physical_window_size(&bubble))
            {
                let point = WindowPoint::new(position.x, position.y);
                let clamped = clamp_window_position(
                    point,
                    work_area_for_point(&bubble, point),
                    size,
                    WINDOW_SAFE_MARGIN,
                );
                if clamped != point {
                    let _ = bubble.set_position(tauri::Position::Physical(
                        tauri::PhysicalPosition::new(clamped.x, clamped.y),
                    ));
                }
            }
        }
    }
    if app
        .get_webview_window(QUICK_POPOVER_WINDOW_LABEL)
        .is_some_and(|popover| popover.is_visible().unwrap_or(false))
    {
        let _ = position_quick_popover(app);
    }
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
async fn app_quit(app: tauri::AppHandle) -> Result<(), String> {
    if prepare_quit(&app)? {
        tauri::async_runtime::spawn_blocking(move || quit_backend_blocking(app))
            .await
            .map_err(|error| error.to_string())??;
    }
    Ok(())
}
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(BackendManager::default()))
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            let _ = show_main_window_with_route(app, None);
        }))
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            #[cfg(windows)]
            {
                let main = webview_window(app.handle(), MAIN_WINDOW_LABEL)?;
                windows_native::mark_app_window(main.hwnd()?.0 as _)?;
                for label in [BUBBLE_WINDOW_LABEL, QUICK_POPOVER_WINDOW_LABEL] {
                    guard_utility_window(&webview_window(app.handle(), label)?)?;
                }
                // Windows can apply its default minimum width during creation,
                // before Tao's configured size constraints are active.
                webview_window(app.handle(), BUBBLE_WINDOW_LABEL)?
                    .set_size(tauri::LogicalSize::new(56.0, 56.0))?;
            }
            setup_tray(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            let label = window.label();
            if matches!(
                label,
                MAIN_WINDOW_LABEL | BUBBLE_WINDOW_LABEL | QUICK_POPOVER_WINDOW_LABEL
            ) {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    if label == BUBBLE_WINDOW_LABEL {
                        let _ = bubble_hide(window.app_handle().clone());
                    } else if let Some(webview) = window.app_handle().get_webview_window(label) {
                        let _ = set_window_visibility(&webview, false);
                    }
                }
            }
            if matches!(label, BUBBLE_WINDOW_LABEL | QUICK_POPOVER_WINDOW_LABEL)
                && matches!(
                    event,
                    WindowEvent::Moved(_)
                        | WindowEvent::Resized(_)
                        | WindowEvent::ScaleFactorChanged { .. }
                )
            {
                refresh_utility_geometry(window);
            }
            if label == MAIN_WINDOW_LABEL && matches!(event, WindowEvent::Resized(_)) {
                let visible =
                    window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(false);
                let _ = window.emit_to(label, "local-dictation:window-visibility", visible);
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
            current_window_visible,
            pick_export_folder,
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
    use std::{collections::HashSet, net::TcpListener, sync::Barrier};

    fn health_response(protocol_version: u32, launch_id: Option<&str>) -> String {
        serde_json::json!({ "ok": true, "data": {
            "version": "0.1.0", "pid": 42, "status": "idle", "protocol_version": protocol_version,
            "backend_owner": "api", "launch_id": launch_id, "model": "small", "language": "auto",
            "device": "cpu", "uptime_seconds": 1.0
        }})
        .to_string()
    }

    fn response_server(
        response: impl FnOnce(TcpStream) + Send + 'static,
    ) -> (SocketAddr, thread::JoinHandle<()>) {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let worker = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            let mut byte = [0];
            while socket.read(&mut byte).unwrap_or(0) > 0 && byte[0] != b'\n' {}
            response(socket);
        });
        (address, worker)
    }

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
        assert_eq!(backend_sidecar_args(), ["--api"]);
    }

    #[test]
    fn simultaneous_lifecycle_requests_reserve_exactly_one_worker() {
        let manager = Arc::new(Mutex::new(BackendManager::default()));
        let barrier = Arc::new(Barrier::new(8));
        let workers = (0..8)
            .map(|_| {
                let manager = Arc::clone(&manager);
                let barrier = Arc::clone(&barrier);
                thread::spawn(move || {
                    barrier.wait();
                    reserve_operation(&manager, LifecycleOperation::Start).unwrap()
                })
            })
            .collect::<Vec<_>>();
        let winners = workers
            .into_iter()
            .map(|worker| usize::from(worker.join().unwrap()))
            .sum::<usize>();
        assert_eq!(winners, 1);
        assert!(!reserve_operation(&manager, LifecycleOperation::Stop).unwrap());
        assert!(!reserve_operation(&manager, LifecycleOperation::Restart).unwrap());
    }

    #[test]
    fn quitting_rejects_new_lifecycle_work() {
        let manager = Mutex::new(BackendManager {
            quitting: true,
            ..BackendManager::default()
        });
        assert!(reserve_operation(&manager, LifecycleOperation::Start).is_err());
        assert!(reserve_operation(&manager, LifecycleOperation::Quit).unwrap());
    }

    #[test]
    fn launch_identifiers_are_unique_within_a_session() {
        let identifiers = (0..100).map(|_| next_launch_id()).collect::<HashSet<_>>();
        assert_eq!(identifiers.len(), 100);
        assert!(identifiers.iter().all(|identifier| !identifier.is_empty()));
    }

    #[test]
    fn ownership_requires_a_nonempty_matching_launch_not_a_parent_pid() {
        assert!(launch_identity_matches(
            Some("owned-launch"),
            Some("owned-launch")
        ));
        assert!(!launch_identity_matches(
            Some("owned-launch"),
            Some("independent-launch")
        ));
        assert!(!launch_identity_matches(Some("owned-launch"), None));
        assert!(!launch_identity_matches(None, None));
        assert!(!launch_identity_matches(Some(""), Some("")));
    }

    #[test]
    fn health_preserves_scalar_owner_and_optional_launch_identity() {
        let mut response: serde_json::Value =
            serde_json::from_str(&health_response(4, None)).unwrap();
        response["data"]
            .as_object_mut()
            .unwrap()
            .remove("launch_id");
        let health = parse_backend_health(&response.to_string()).unwrap();
        assert_eq!(health.backend_owner, "api");
        assert_eq!(health.launch_id, None);
        let health = parse_backend_health(&health_response(4, Some("this-launch"))).unwrap();
        assert_eq!(health.launch_id.as_deref(), Some("this-launch"));
        let mut response: serde_json::Value =
            serde_json::from_str(&health_response(4, Some("this-launch"))).unwrap();
        response["data"]["loading"] = serde_json::json!(true);
        response["data"]["recording_ready"] = serde_json::json!(false);
        response["data"]["error"] = serde_json::json!("No local model available");
        let health = parse_backend_health(&response.to_string()).unwrap();
        let forwarded = serde_json::to_value(health).unwrap();
        assert_eq!(forwarded["loading"], true);
        assert_eq!(forwarded["recording_ready"], false);
        assert_eq!(forwarded["error"], "No local model available");
    }

    #[test]
    fn incompatible_protocol_and_malformed_health_remain_unhealthy() {
        let error = parse_backend_health(&health_response(3, Some("old-launch"))).unwrap_err();
        assert!(!error.unavailable);
        assert!(error.message.contains("expected 4"));
        assert_eq!(status_from_health_error(&error).status, "unhealthy");
        let error = parse_backend_health("legacy text").unwrap_err();
        assert_eq!(status_from_health_error(&error).status, "unhealthy");
    }

    #[test]
    fn slow_and_failed_start_statuses_are_finite_and_keep_metadata() {
        let mut manager = BackendManager {
            launch_kind: Some("sidecar".to_string()),
            started_at: Some(Instant::now() - Duration::from_secs(46)),
            ..BackendManager::default()
        };
        let status = status_starting(&manager);
        assert_eq!(status.status, "starting");
        assert_eq!(status.launch_kind.as_deref(), Some("sidecar"));
        manager.started_at = Some(Instant::now() - Duration::from_secs(121));
        let status = status_starting(&manager);
        assert_eq!(status.status, "error");
        assert!(status
            .last_error
            .as_deref()
            .unwrap()
            .contains("120 seconds"));
        manager.operation = Some(LifecycleOperation::Stop);
        assert_eq!(status_starting(&manager).status, "stopping");
    }

    #[test]
    fn missing_loopback_endpoint_allows_backend_startup() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);
        let error = bridge_request_at(address, r#"{"cmd":"health"}"#, CONTROL_TIMEOUT).unwrap_err();
        assert!(
            error.unavailable,
            "Missing loopback endpoint was classified as an incompatible process: {error:?}"
        );
    }

    #[test]
    fn only_resource_commands_have_a_long_response_deadline() {
        assert_eq!(
            request_timeout(r#"{"cmd":"health","args":{}}"#).unwrap(),
            CONTROL_TIMEOUT
        );
        assert_eq!(
            request_timeout(r#"{"cmd":"set-settings","args":{}}"#).unwrap(),
            RESOURCE_LOAD_TIMEOUT
        );
        assert_eq!(
            request_timeout(r#"{"cmd":"retry-resources","args":{}}"#).unwrap(),
            RESOURCE_LOAD_TIMEOUT
        );
        assert!(request_timeout(r#"{"cmd":[]}"#).is_err());
        assert!(request_timeout(&"x".repeat(MAX_REQUEST_BYTES + 1)).is_err());
        assert!(request_timeout("{}\n{}").is_err());
    }

    #[test]
    fn tcp_bridge_bounds_large_and_truncated_responses() {
        let (address, worker) = response_server(|mut socket| {
            let _ = socket.write_all(&vec![b'x'; MAX_RESPONSE_BYTES + 1]);
        });
        let error = bridge_request_at(address, "{}", CONTROL_TIMEOUT).unwrap_err();
        assert!(error.message.contains("exceeds 1048576"));
        worker.join().unwrap();
        let (address, worker) = response_server(|mut socket| {
            let _ = socket.write_all(b"{\"ok\":true}");
        });
        let error = bridge_request_at(address, "{}", CONTROL_TIMEOUT).unwrap_err();
        assert!(error.message.contains("complete response"));
        worker.join().unwrap();
    }

    #[test]
    fn tcp_bridge_uses_a_total_deadline_despite_slow_partial_reads() {
        let (address, worker) = response_server(|mut socket| {
            for _ in 0..8 {
                if socket.write_all(b"x").is_err() {
                    break;
                }
                thread::sleep(Duration::from_millis(40));
            }
        });
        let started = Instant::now();
        let error = bridge_request_at(address, "{}", Duration::from_millis(100)).unwrap_err();
        assert!(
            !error.unavailable,
            "A connected but unresponsive process must not be treated as absent"
        );
        assert!(started.elapsed() < Duration::from_millis(500));
        worker.join().unwrap();
    }

    #[test]
    fn tcp_bridge_accepts_one_utf8_line_and_rejects_invalid_encoding() {
        let (address, worker) = response_server(|mut socket| {
            socket.write_all(b"{\"ok\":true}\n").unwrap();
        });
        assert_eq!(
            bridge_request_at(address, "{}", CONTROL_TIMEOUT).unwrap(),
            "{\"ok\":true}"
        );
        worker.join().unwrap();
        let (address, worker) = response_server(|mut socket| {
            socket.write_all(&[0xff, b'\n']).unwrap();
        });
        assert!(bridge_request_at(address, "{}", CONTROL_TIMEOUT)
            .unwrap_err()
            .message
            .contains("UTF-8"));
        worker.join().unwrap();
    }

    #[test]
    fn bubble_position_defaults_and_rejects_hidden_api_root() {
        let area = WorkArea::new(0, 0, 1920, 1080);
        let size = WindowSize::new(56, 56);
        for point in [
            None,
            Some(WindowPoint::new(0, 0)),
            Some(WindowPoint::new(-32000, -32000)),
        ] {
            assert_eq!(
                resolve_bubble_position(point, area, size, 16),
                WindowPoint::new(1848, 1008)
            );
        }
    }

    #[test]
    fn bubble_placement_retains_a_secondary_monitor_and_clamps_a_removed_monitor() {
        let primary = WorkArea::new(0, 0, 1920, 1040);
        let secondary = WorkArea::new(-2560, -200, 2560, 1400);
        let saved = WindowPoint::new(-1500, 400);
        let area = select_work_area(saved, &[primary, secondary], primary);
        assert_eq!(area, secondary);
        assert_eq!(
            resolve_bubble_position(Some(saved), area, WindowSize::new(84, 84), 16),
            saved
        );
        let area = select_work_area(saved, &[primary], primary);
        assert_eq!(
            resolve_bubble_position(Some(saved), area, WindowSize::new(112, 112), 16),
            WindowPoint::new(16, 400)
        );
    }

    #[test]
    fn shared_monitor_edges_and_extreme_saved_points_do_not_pick_the_wrong_area() {
        let primary = WorkArea::new(0, 0, 1920, 1040);
        let secondary = WorkArea::new(-2560, 0, 2560, 1400);
        assert_eq!(
            select_work_area(WindowPoint::new(0, 200), &[secondary, primary], secondary),
            primary
        );
        assert_eq!(
            select_work_area(
                WindowPoint::new(i32::MAX, i32::MAX),
                &[secondary, primary],
                secondary
            ),
            primary
        );
    }

    #[test]
    fn physical_sizes_are_used_for_scaled_screen_bounds() {
        let area = WorkArea::new(100, 50, 1200, 800);
        assert_eq!(
            resolve_bubble_position(
                Some(WindowPoint::new(5000, 4000)),
                area,
                WindowSize::new(112, 112),
                16
            ),
            WindowPoint::new(1172, 722)
        );
        assert_eq!(
            resolve_bubble_position(
                Some(WindowPoint::new(-400, 10)),
                area,
                WindowSize::new(112, 112),
                16
            ),
            WindowPoint::new(116, 66)
        );
    }

    #[test]
    fn popover_placement_stays_visible_and_tail_converts_to_css_pixels() {
        let area = WorkArea::new(0, 0, 3840, 2120);
        for bubble in [WindowPoint::new(8, 1800), WindowPoint::new(3700, 1800)] {
            let placement = place_popover_for_bubble(
                bubble,
                WindowSize::new(112, 112),
                WindowSize::new(820, 600),
                area,
                16,
                2.0,
            );
            assert!(placement.position.x >= 16);
            assert!(placement.position.x + 820 <= area.right() - 16);
            let css_tail = placement.tail_x as f64 / 2.0;
            assert!((16.0..=394.0).contains(&css_tail));
        }
    }
}
