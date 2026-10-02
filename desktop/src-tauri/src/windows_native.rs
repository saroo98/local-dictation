use std::{
    collections::BTreeMap,
    ffi::{OsStr, OsString},
    mem::{size_of, zeroed},
    os::windows::{
        ffi::OsStrExt,
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
    },
    path::Path,
    ptr::{null, null_mut},
};

use windows_sys::Win32::{
    Foundation::{HWND, LPARAM, LRESULT, WPARAM},
    System::{
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JobObjectBasicAccountingInformation,
            JobObjectExtendedLimitInformation, QueryInformationJobObject, SetInformationJobObject,
            TerminateJobObject, JOBOBJECT_BASIC_ACCOUNTING_INFORMATION,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        },
        Threading::{
            CreateProcessW, GetCurrentThreadId, GetExitCodeProcess, ResumeThread, TerminateProcess,
            WaitForSingleObject, CREATE_NO_WINDOW, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT,
            PROCESS_INFORMATION, STARTUPINFOW,
        },
    },
    UI::{
        Shell::{DefSubclassProc, RemoveWindowSubclass, SetWindowSubclass},
        WindowsAndMessaging::{
            EnumChildWindows, GetWindowThreadProcessId, RemovePropW, SetPropW, MA_NOACTIVATE,
            WM_MOUSEACTIVATE, WM_NCDESTROY, WM_PARENTNOTIFY,
        },
    },
};

/// The job is assigned while the initial thread is suspended, before a frozen
/// backend can create its worker. Closing the last job handle also owns cleanup
/// if the native shell exits unexpectedly.
#[derive(Debug)]
pub(crate) struct ManagedTree {
    job: OwnedHandle,
    process: OwnedHandle,
}

fn last_error(context: &str) -> String {
    format!("{context}: {}", std::io::Error::last_os_error())
}

fn wide(value: &OsStr) -> Result<Vec<u16>, String> {
    let mut encoded: Vec<u16> = value.encode_wide().collect();
    if encoded.contains(&0) {
        return Err("Backend launch argument contains a null character.".to_string());
    }
    encoded.push(0);
    Ok(encoded)
}

// Windows CRT argument quoting, including quotes and trailing backslashes.
fn quote_argument(value: &OsStr) -> Result<Vec<u16>, String> {
    let value = wide(value)?;
    let mut result = vec![b'"' as u16];
    let mut slashes = 0;
    for &unit in &value[..value.len() - 1] {
        if unit == b'\\' as u16 {
            slashes += 1;
            continue;
        }
        result.extend(std::iter::repeat_n(
            b'\\' as u16,
            slashes * if unit == b'"' as u16 { 2 } else { 1 },
        ));
        slashes = 0;
        if unit == b'"' as u16 {
            result.push(b'\\' as u16);
        }
        result.push(unit);
    }
    result.extend(std::iter::repeat_n(b'\\' as u16, slashes * 2));
    result.push(b'"' as u16);
    Ok(result)
}

fn environment_block(overrides: &[(&str, &str)]) -> Result<Vec<u16>, String> {
    let mut variables: BTreeMap<String, (OsString, OsString)> = std::env::vars_os()
        .map(|(key, value)| (key.to_string_lossy().to_uppercase(), (key, value)))
        .collect();
    for &(key, value) in overrides {
        variables.insert(
            key.to_uppercase(),
            (OsString::from(key), OsString::from(value)),
        );
    }
    let mut block = Vec::new();
    for (_, (key, value)) in variables {
        let mut entry = key;
        entry.push("=");
        entry.push(value);
        block.extend(wide(&entry)?);
    }
    block.push(0);
    Ok(block)
}

impl ManagedTree {
    pub(crate) fn spawn(
        executable: &Path,
        args: &[OsString],
        workdir: &Path,
        environment: &[(&str, &str)],
    ) -> Result<Self, String> {
        let application = wide(executable.as_os_str())?;
        let directory = wide(workdir.as_os_str())?;
        let mut command_line = quote_argument(executable.as_os_str())?;
        for arg in args {
            command_line.push(b' ' as u16);
            command_line.extend(quote_argument(arg)?);
        }
        command_line.push(0);
        let environment = environment_block(environment)?;

        // Each handle is owned exactly once; the job has neither breakaway flag.
        unsafe {
            let job = CreateJobObjectW(null(), null());
            if job.is_null() {
                return Err(last_error("Could not create backend job"));
            }
            let job = OwnedHandle::from_raw_handle(job);
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job.as_raw_handle(),
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            ) == 0
            {
                return Err(last_error("Could not configure backend job"));
            }

            let mut startup: STARTUPINFOW = zeroed();
            startup.cb = size_of::<STARTUPINFOW>() as u32;
            let mut information: PROCESS_INFORMATION = zeroed();
            if CreateProcessW(
                application.as_ptr(),
                command_line.as_mut_ptr(),
                null(),
                null(),
                0,
                CREATE_NO_WINDOW | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT,
                environment.as_ptr() as *const _,
                directory.as_ptr(),
                &startup,
                &mut information,
            ) == 0
            {
                return Err(last_error("Could not start backend process"));
            }
            let process = OwnedHandle::from_raw_handle(information.hProcess);
            let thread = OwnedHandle::from_raw_handle(information.hThread);
            if AssignProcessToJobObject(job.as_raw_handle(), process.as_raw_handle()) == 0 {
                let error = last_error("Could not assign suspended backend to its job");
                // This is still our suspended process, so it cannot have descendants.
                TerminateProcess(process.as_raw_handle(), 1);
                WaitForSingleObject(process.as_raw_handle(), 5_000);
                return Err(error);
            }
            if ResumeThread(thread.as_raw_handle()) == u32::MAX {
                let error = last_error("Could not resume backend process");
                TerminateJobObject(job.as_raw_handle(), 1);
                WaitForSingleObject(process.as_raw_handle(), 5_000);
                return Err(error);
            }
            Ok(Self { job, process })
        }
    }

    pub(crate) fn active_processes(&self) -> Result<u32, String> {
        unsafe {
            let mut accounting: JOBOBJECT_BASIC_ACCOUNTING_INFORMATION = zeroed();
            if QueryInformationJobObject(
                self.job.as_raw_handle(),
                JobObjectBasicAccountingInformation,
                &mut accounting as *mut _ as *mut _,
                size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                null_mut(),
            ) == 0
            {
                return Err(last_error("Could not inspect backend job"));
            }
            Ok(accounting.ActiveProcesses)
        }
    }

    pub(crate) fn exit_description(&self) -> Result<String, String> {
        unsafe {
            let mut code = 0;
            if GetExitCodeProcess(self.process.as_raw_handle(), &mut code) == 0 {
                return Err(last_error("Could not inspect backend exit code"));
            }
            Ok(format!("exit code {code}"))
        }
    }

    pub(crate) fn terminate(&self) -> Result<(), String> {
        if unsafe { TerminateJobObject(self.job.as_raw_handle(), 1) } == 0 {
            return Err(last_error("Could not terminate owned backend job"));
        }
        Ok(())
    }
}

const UTILITY_SUBCLASS_ID: usize = 0x4C44;
const APP_MARKER_SUBCLASS_ID: usize = 0x4C45;
const APP_WINDOW_MARKER: windows_sys::core::PCWSTR =
    windows_sys::core::w!("LocalDictationNativeWindow");

unsafe extern "system" fn app_marker_proc(
    hwnd: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
    _id: usize,
    _data: usize,
) -> LRESULT {
    if message == WM_NCDESTROY {
        RemovePropW(hwnd, APP_WINDOW_MARKER);
        RemoveWindowSubclass(hwnd, Some(app_marker_proc), APP_MARKER_SUBCLASS_ID);
    }
    DefSubclassProc(hwnd, message, wparam, lparam)
}

/// Identifies our UI to an independently started backend, without granting it
/// ownership of the shell or backend process. The tag is removed on destruction.
pub(crate) fn mark_app_window(hwnd: HWND) -> Result<(), String> {
    unsafe {
        if GetWindowThreadProcessId(hwnd, null_mut()) != GetCurrentThreadId() {
            return Err("App window marker must run on the window's UI thread.".to_string());
        }
        if SetPropW(hwnd, APP_WINDOW_MARKER, 1usize as _) == 0 {
            return Err(last_error("Could not mark app window"));
        }
        if SetWindowSubclass(hwnd, Some(app_marker_proc), APP_MARKER_SUBCLASS_ID, 0) == 0 {
            let error = last_error("Could not manage app window marker");
            RemovePropW(hwnd, APP_WINDOW_MARKER);
            return Err(error);
        }
    }
    Ok(())
}

unsafe extern "system" fn utility_window_proc(
    hwnd: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
    _id: usize,
    _data: usize,
) -> LRESULT {
    if message == WM_MOUSEACTIVATE {
        // Keep the pointer event while preserving the external editor's activation.
        return MA_NOACTIVATE as LRESULT;
    }
    if message == WM_PARENTNOTIFY {
        EnumChildWindows(hwnd, Some(install_child_guard), 0);
    }
    if message == WM_NCDESTROY {
        RemoveWindowSubclass(hwnd, Some(utility_window_proc), UTILITY_SUBCLASS_ID);
    }
    DefSubclassProc(hwnd, message, wparam, lparam)
}

unsafe extern "system" fn install_child_guard(hwnd: HWND, _data: LPARAM) -> i32 {
    // The helper must run on the owning UI thread, never a WebView renderer thread.
    if GetWindowThreadProcessId(hwnd, null_mut()) == GetCurrentThreadId() {
        SetWindowSubclass(hwnd, Some(utility_window_proc), UTILITY_SUBCLASS_ID, 0);
    }
    1
}

/// Called on Tauri's UI thread, after the WebView is created and before show.
pub(crate) fn guard_utility_window(hwnd: HWND) -> Result<(), String> {
    mark_app_window(hwnd)?;
    unsafe {
        if GetWindowThreadProcessId(hwnd, null_mut()) != GetCurrentThreadId() {
            return Err("Utility activation guard must run on the window's UI thread.".to_string());
        }
        if SetWindowSubclass(hwnd, Some(utility_window_proc), UTILITY_SUBCLASS_ID, 0) == 0 {
            return Err(last_error("Could not protect utility window activation"));
        }
        EnumChildWindows(hwnd, Some(install_child_guard), 0);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        process::Command,
        thread,
        time::{Duration, Instant},
    };

    #[test]
    fn windows_argument_quoting_preserves_spaces_quotes_and_backslashes() {
        let quoted = quote_argument(OsStr::new("a b\\\"c\\")).unwrap();
        assert_eq!(String::from_utf16(&quoted).unwrap(), "\"a b\\\\\\\"c\\\\\"");
        assert!(quote_argument(OsStr::new("bad\0argument")).is_err());
    }

    #[test]
    fn activation_guard_covers_real_native_parent_and_child_windows() {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            CreateWindowExW, DestroyWindow, GetPropW, SendMessageW, WS_CHILD, WS_EX_NOACTIVATE,
            WS_POPUP,
        };
        let class = wide(OsStr::new("STATIC")).unwrap();
        unsafe {
            let parent = CreateWindowExW(
                WS_EX_NOACTIVATE,
                class.as_ptr(),
                null(),
                WS_POPUP,
                0,
                0,
                56,
                56,
                null_mut(),
                null_mut(),
                null_mut(),
                null(),
            );
            assert!(!parent.is_null());
            let child = CreateWindowExW(
                0,
                class.as_ptr(),
                null(),
                WS_CHILD,
                0,
                0,
                56,
                56,
                parent,
                null_mut(),
                null_mut(),
                null(),
            );
            assert!(!child.is_null());
            guard_utility_window(parent).unwrap();
            let marker = wide(OsStr::new("LocalDictationNativeWindow")).unwrap();
            assert_eq!(GetPropW(parent, marker.as_ptr()) as usize, 1);
            assert_eq!(
                SendMessageW(parent, WM_MOUSEACTIVATE, parent as usize, 0),
                MA_NOACTIVATE as isize
            );
            assert_eq!(
                SendMessageW(child, WM_MOUSEACTIVATE, parent as usize, 0),
                MA_NOACTIVATE as isize
            );
            assert_ne!(DestroyWindow(parent), 0);
        }
    }

    #[test]
    fn job_tracks_worker_after_parent_exit_and_terminates_only_its_tree() {
        let executable = std::env::current_exe().unwrap();
        let workdir = executable.parent().unwrap();
        let args = [
            OsString::from("--exact"),
            OsString::from("windows_native::tests::controlled_process_fixture"),
            OsString::from("--ignored"),
        ];
        let tree = ManagedTree::spawn(
            &executable,
            &args,
            workdir,
            &[("LOCAL_DICTATION_TEST_PROCESS", "parent")],
        )
        .unwrap();
        let independent = ManagedTree::spawn(
            &executable,
            &args,
            workdir,
            &[("LOCAL_DICTATION_TEST_PROCESS", "worker")],
        )
        .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if tree.exit_description().unwrap() != "exit code 259" {
                break;
            }
            assert!(Instant::now() < deadline, "controlled parent did not exit");
            thread::sleep(Duration::from_millis(20));
        }
        assert!(
            tree.active_processes().unwrap() > 0,
            "worker escaped its job"
        );
        tree.terminate().unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        while tree.active_processes().unwrap() != 0 {
            assert!(
                Instant::now() < deadline,
                "owned worker survived termination"
            );
            thread::sleep(Duration::from_millis(20));
        }
        assert!(independent.active_processes().unwrap() > 0);
    }

    #[test]
    #[ignore = "controlled subprocess fixture; invoked by the managed-job test"]
    fn controlled_process_fixture() {
        match std::env::var("LOCAL_DICTATION_TEST_PROCESS").as_deref() {
            Ok("parent") => {
                let mut child = Command::new(std::env::current_exe().unwrap());
                child
                    .args([
                        "--exact",
                        "windows_native::tests::controlled_process_fixture",
                        "--ignored",
                    ])
                    .env("LOCAL_DICTATION_TEST_PROCESS", "worker");
                use std::os::windows::process::CommandExt;
                child.creation_flags(CREATE_NO_WINDOW).spawn().unwrap();
                thread::sleep(Duration::from_millis(100));
            }
            Ok("worker") => thread::sleep(Duration::from_secs(20)),
            _ => panic!("fixture must be launched by the managed-job test"),
        }
    }
}
