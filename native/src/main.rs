//! Fixed private-Python package entry; no PATH interpreter or shell.
use anyhow::{Context, Result, ensure};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::{Component, Path, PathBuf};

fn member(root: &Path, name: &str) -> Result<PathBuf> {
    ensure!(
        !name.is_empty() && !name.contains(['\\', ':']),
        "Invalid package path"
    );
    let mut path = root.to_path_buf();
    for component in Path::new(name).components() {
        let Component::Normal(part) = component else {
            anyhow::bail!("Invalid package path")
        };
        path.push(part);
        ensure!(!path.is_symlink(), "Package links are not supported");
    }
    ensure!(path.is_file(), "The Lab package is incomplete");
    Ok(path)
}

fn main() -> Result<()> {
    let exe = std::env::current_exe()?;
    let root = exe.parent().context("Missing package folder")?;
    let metadata = member(root, "lab-package.json")?;
    ensure!(
        metadata.metadata()?.len() < 4 * 1024 * 1024,
        "Invalid package inventory"
    );
    let manifest: Value = serde_json::from_slice(&std::fs::read(metadata)?)?;
    ensure!(
        manifest["schema"] == 1 && manifest["component"] == "agent-experiment-lab",
        "Unsupported Lab package"
    );
    let files = manifest["files"]
        .as_object()
        .context("Missing package inventory")?;
    ensure!(
        !files.is_empty() && files.len() <= 20_000,
        "Invalid package inventory"
    );
    let python = if cfg!(windows) {
        "support/python/python.exe"
    } else {
        "support/python/bin/python3.13"
    };
    ensure!(
        files.contains_key(python) && files.contains_key("support/launch.py"),
        "Missing private interpreter or entrypoint"
    );
    let mut size = 0u64;
    for (name, expected) in files {
        let path = member(root, name)?;
        size += path.metadata()?.len();
        ensure!(
            size <= 1024 * 1024 * 1024,
            "Lab package exceeds its size limit"
        );
        let hash = format!("{:x}", Sha256::digest(std::fs::read(path)?));
        ensure!(
            expected.as_str() == Some(&hash),
            "Lab package checksum mismatch: {name}"
        );
    }
    let mut command = std::process::Command::new(member(root, python)?);
    command
        .args(["-I", "-B", "-X", "utf8"])
        .arg(member(root, "support/launch.py")?)
        .args(std::env::args_os().skip(1));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(windows_sys::Win32::System::Threading::CREATE_SUSPENDED);
    }
    let mut child = command
        .spawn()
        .context("Could not start the private Lab interpreter")?;
    #[cfg(windows)]
    let _job = match WindowsJob::attach(&child) {
        Ok(job) => job,
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    #[cfg(windows)]
    if let Err(error) = resume_suspended(&child) {
        drop(_job);
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    let status = child.wait()?;
    // Normal return closes the job, including any descendant left by an ACP
    // endpoint. A killed parent also releases its non-inherited job handle.
    #[cfg(windows)]
    drop(_job);
    if !status.success() {
        std::process::exit(status.code().unwrap_or(1));
    }
    Ok(())
}

#[cfg(windows)]
struct WindowsJob(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
impl WindowsJob {
    fn attach(child: &std::process::Child) -> Result<Self> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::*;
        let job = Self(unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) });
        ensure!(!job.0.is_null(), "Could not establish Lab process cleanup");
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        ensure!(
            unsafe {
                SetInformationJobObject(
                    job.0,
                    JobObjectExtendedLimitInformation,
                    (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                    std::mem::size_of_val(&limits) as u32,
                )
            } != 0,
            "Could not configure Lab process cleanup"
        );
        ensure!(
            unsafe { AssignProcessToJobObject(job.0, child.as_raw_handle()) } != 0,
            "Could not attach Lab process cleanup"
        );
        Ok(job)
    }
}
#[cfg(windows)]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

// std::process retains the process handle but not the initial thread handle.
// CREATE_SUSPENDED guarantees that no child code runs before job assignment.
#[cfg(windows)]
fn resume_suspended(child: &std::process::Child) -> Result<()> {
    use windows_sys::Win32::{
        Foundation::*,
        System::{Diagnostics::ToolHelp::*, Threading::*},
    };
    let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
    ensure!(
        snapshot != INVALID_HANDLE_VALUE,
        "Could not inspect the suspended Lab process"
    );
    let mut entry: THREADENTRY32 = unsafe { std::mem::zeroed() };
    entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
    let mut found = None;
    let mut available = unsafe { Thread32First(snapshot, &mut entry) } != 0;
    while available {
        if entry.th32OwnerProcessID == child.id() {
            found = Some(entry.th32ThreadID);
            break;
        }
        available = unsafe { Thread32Next(snapshot, &mut entry) } != 0;
    }
    unsafe {
        CloseHandle(snapshot);
    }
    let id = found.context("The suspended Lab process has no initial thread")?;
    let thread = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, id) };
    ensure!(!thread.is_null(), "Could not open the suspended Lab thread");
    let resumed = unsafe { ResumeThread(thread) };
    unsafe {
        CloseHandle(thread);
    }
    ensure!(resumed == 1, "Could not resume the suspended Lab process");
    Ok(())
}
