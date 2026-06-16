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

const CONTROL_HOST: &str = "127.0.0.1";
const CONTROL_PORT: u16 = 49_731;
const CONTROL_TIMEOUT: Duration = Duration::from_secs(2);
const BACKEND_START_POLL: Duration = Duration::from_millis(250);
const BACKEND_START_ATTEMPTS: usize = 8;
const BACKEND_STOP_ATTEMPTS: usize = 12;

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
    child: Option<Child>,
    last_error: Option<String>,
}

impl BackendManager {
    fn owned(&self) -> bool {
        self.child.is_some()
    }

    fn refresh_child(&mut self) {
        let Some(child) = self.child.as_mut() else {
            return;
        };

        match child.try_wait() {
            Ok(Some(status)) => {
                self.last_error = Some(format!("Backend process exited before it became healthy: {status}"));
                self.child = None;
            }
            Ok(None) => {}
            Err(error) => {
                self.last_error = Some(format!("Could not inspect backend process: {error}"));
                self.child = None;
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

fn current_backend_status(manager: &mut BackendManager) -> BackendStatus {
    if let Ok(health) = health_from_bridge() {
        manager.last_error = None;
        return status_ready(health, manager.owned());
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

fn spawn_backend_process() -> Result<Child, String> {
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
        .map_err(|error| format!("Failed to start Python backend: {error}"))
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
fn backend_start(manager: tauri::State<'_, Mutex<BackendManager>>) -> Result<BackendStatus, String> {
    let mut manager = lock_manager(&manager)?;

    if let Ok(health) = health_from_bridge() {
        return Ok(status_ready(health, manager.owned()));
    }

    manager.refresh_child();
    if !manager.owned() {
        manager.child = Some(spawn_backend_process()?);
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

    if let Some(child) = manager.child.as_mut() {
        let _ = child.kill();
    }
    manager.child = None;

    Ok(status_not_running("Backend stopped."))
}

#[tauri::command]
fn backend_restart(manager: tauri::State<'_, Mutex<BackendManager>>) -> Result<BackendStatus, String> {
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
            if let Some(child) = manager.child.as_mut() {
                let _ = child.kill();
            }
            manager.child = None;
        }
    }

    backend_start(manager)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(BackendManager::default()))
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
