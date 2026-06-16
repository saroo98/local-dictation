use std::{
    io::{BufRead, BufReader, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const CONTROL_HOST: &str = "127.0.0.1";
const CONTROL_PORT: u16 = 49_731;
const CONTROL_TIMEOUT: Duration = Duration::from_secs(2);
const BACKEND_START_POLL: Duration = Duration::from_millis(250);
const BACKEND_START_ATTEMPTS: usize = 8;
const BACKEND_STOP_ATTEMPTS: usize = 12;
const SIDECAR_BINARY_NAME: &str = "local-dictation-backend";

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
}

#[derive(Debug, Default)]
struct BackendManager {
    child: Option<ManagedBackendChild>,
    last_error: Option<String>,
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
                    }
                    Ok(None) => {}
                    Err(error) => {
                        self.last_error =
                            Some(format!("Could not inspect backend process: {error}"));
                        self.child = None;
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

    Err("Could not find bubble_dictate.py in the migration worktree or C:\\local-dictation.".to_string())
}

fn backend_workdir(script: &Path) -> PathBuf {
    script
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(repo_root)
}

fn status_ready(health: BackendHealth, owned: bool) -> BackendStatus {
    BackendStatus {
        status: "ready".to_string(),
        owned,
        message: "Local backend ready.".to_string(),
        log_path: log_path(),
        health: Some(health),
    }
}

fn status_not_running(message: impl Into<String>) -> BackendStatus {
    BackendStatus {
        status: "not_running".to_string(),
        owned: false,
        message: message.into(),
        log_path: log_path(),
        health: None,
    }
}

fn status_starting(manager: &BackendManager) -> BackendStatus {
    BackendStatus {
        status: "starting".to_string(),
        owned: manager.owned(),
        message: "Backend starting. The speech model may still be loading.".to_string(),
        log_path: log_path(),
        health: None,
    }
}

fn status_error(message: impl Into<String>) -> BackendStatus {
    BackendStatus {
        status: "error".to_string(),
        owned: false,
        message: message.into(),
        log_path: log_path(),
        health: None,
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
        };
    }

    status_not_running("Backend not running.")
}

fn current_backend_status(manager: &mut BackendManager) -> BackendStatus {
    match health_from_bridge() {
        Ok(health) => {
            manager.last_error = None;
            return status_ready(health, manager.owned());
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

fn spawn_backend(app: &tauri::AppHandle) -> Result<ManagedBackendChild, String> {
    let debug_build = cfg!(debug_assertions);
    let sidecar_available = !debug_build || sidecar_source_binary_path().exists();
    let python_available = python_executable().is_ok();

    match choose_backend_launch_strategy(debug_build, sidecar_available, python_available) {
        BackendLaunchStrategy::Sidecar => spawn_sidecar_backend(app),
        BackendLaunchStrategy::PythonFallback => spawn_backend_process(),
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
fn backend_status(manager: tauri::State<'_, Mutex<BackendManager>>) -> Result<BackendStatus, String> {
    let mut manager = lock_manager(&manager)?;
    Ok(current_backend_status(&mut manager))
}

#[tauri::command]
fn backend_start(
    app: tauri::AppHandle,
    manager: tauri::State<'_, Mutex<BackendManager>>,
) -> Result<BackendStatus, String> {
    let mut manager = lock_manager(&manager)?;

    if let Ok(health) = health_from_bridge() {
        return Ok(status_ready(health, manager.owned()));
    }
    if let Err(error) = health_from_bridge() {
        let unhealthy = status_from_health_error(&error);
        if unhealthy.status == "unhealthy" {
            return Ok(unhealthy);
        }
    }

    manager.refresh_child();
    if !manager.owned() {
        manager.child = Some(spawn_backend(&app)?);
        manager.last_error = None;
    }

    for _ in 0..BACKEND_START_ATTEMPTS {
        thread::sleep(BACKEND_START_POLL);
        if let Ok(health) = health_from_bridge() {
            return Ok(status_ready(health, manager.owned()));
        }
        manager.refresh_child();
        if !manager.owned() {
            break;
        }
    }

    Ok(current_backend_status(&mut manager))
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
fn backend_restart(
    app: tauri::AppHandle,
    manager: tauri::State<'_, Mutex<BackendManager>>,
) -> Result<BackendStatus, String> {
    {
        let mut manager = lock_manager(&manager)?;
        if manager.owned() {
            let _ = bridge_json_call::<serde_json::Value>("shutdown-backend");
            for _ in 0..BACKEND_STOP_ATTEMPTS {
                thread::sleep(BACKEND_START_POLL);
                manager.refresh_child();
                if !manager.owned() {
                    break;
                }
            }
            manager.take_and_kill_child();
        }
    }

    backend_start(app, manager)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(BackendManager::default()))
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            bridge_call,
            backend_health,
            backend_status,
            backend_start,
            backend_stop,
            backend_restart
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
        let status = status_from_health_error("Local bridge returned invalid JSON: expected value at line 1 column 1");

        assert_eq!(status.status, "unhealthy");
        assert!(!status.owned);
        assert!(status.message.contains("legacy Python backend"));
    }
}
