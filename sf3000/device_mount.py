from __future__ import annotations

import json
import os
import re
import shutil
import string
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sf3000.models import MountCandidate


def decode_subprocess_output(data: bytes) -> str:
    if not data:
        return ""

    if b"\x00" in data[:8] or data.count(b"\x00") > max(4, len(data) // 10):
        try:
            return (
                data.decode("utf-16le", errors="ignore")
                .replace("\ufeff", "")
                .replace("\x00", "")
                .strip()
            )
        except Exception:
            pass

    for encoding in ("utf-8", "mbcs", "cp1252"):
        try:
            return data.decode(encoding).replace("\x00", "").strip()
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore").replace("\x00", "").strip()


def run_captured_command(args: Sequence[str], timeout: int = 120) -> Tuple[int, str, str]:
    completed = subprocess.run(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return (
        completed.returncode,
        decode_subprocess_output(completed.stdout),
        decode_subprocess_output(completed.stderr),
    )


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell_json(script: str, timeout: int = 120):
    code, stdout, stderr = run_captured_command(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )
    if code != 0:
        raise OSError(stderr or stdout or "PowerShell command failed.")
    if not stdout:
        return {}
    return json.loads(stdout)


def ensure_list(value) -> List[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_drive_letter(value) -> str:
    text = str(value or "").strip().strip(":").strip("\\/").upper()
    return text if len(text) == 1 and text in string.ascii_uppercase else ""


def extract_drive_letter(path_text: str) -> str:
    match = re.match(r"^\s*([a-zA-Z]):", path_text or "")
    return normalize_drive_letter(match.group(1)) if match else ""


def extract_mount_signature(path_text: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(
        r"sf3000-disk(?P<disk>\d+)(?:-part(?P<part>\d+))?",
        path_text or "",
        re.IGNORECASE,
    )
    if not match:
        return None, None
    disk_number = int(match.group("disk"))
    partition_raw = match.group("part")
    return disk_number, int(partition_raw) if partition_raw else None


def is_wsl_path(path_text: str) -> bool:
    text = (path_text or "").strip().casefold()
    return text.startswith("\\\\wsl$\\") or text.startswith("\\\\wsl.localhost\\")


def list_wsl_distros() -> List[str]:
    try:
        names = sorted(name for name in os.listdir(r"\\wsl$") if name)
        if names:
            return names
    except OSError:
        pass

    try:
        code, stdout, _stderr = run_captured_command(["wsl.exe", "-l", "-q"], timeout=30)
    except Exception:
        return []
    if code != 0:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def wake_wsl_backend():
    try:
        subprocess.run(
            ["wsl.exe", "-e", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except Exception:
        pass


def clean_command_output(text: str) -> str:
    cleaned = (text or "").replace("\ufeff", "").replace("\x00", "")
    lines = [line.strip() for line in cleaned.splitlines()]
    filtered = [line for line in lines if line]
    return "\n".join(filtered).strip()


def build_wsl_unc_paths(distro_name: str, mount_name: str) -> List[Path]:
    raw_paths = [
        Path(fr"\\wsl$\{distro_name}\mnt\wsl\{mount_name}"),
        Path(fr"\\wsl.localhost\{distro_name}\mnt\wsl\{mount_name}"),
    ]
    result: List[Path] = []
    seen = set()
    for path in raw_paths:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def build_wsl_unc_path(distro_name: str, mount_name: str) -> Path:
    return build_wsl_unc_paths(distro_name, mount_name)[0]


def format_wsl_command_failure(
    action_label: str,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
) -> str:
    stdout = clean_command_output(stdout)
    stderr = clean_command_output(stderr)
    details = []
    for value in (stderr, stdout):
        if value and value not in {"0", "-1"} and value not in details:
            details.append(value)
    combined = "\n".join(details).strip()
    combined_cf = combined.casefold()

    if "operation was canceled by the user" in combined_cf or exit_code == 1223:
        return "The Windows elevation prompt was canceled."

    if "access is denied" in combined_cf or "e_accessdenied" in combined_cf:
        return (
            f"Windows blocked WSL while trying to {action_label}.\n\n"
            "Approve the UAC prompt and make sure no other app is locking the SD card."
        )

    if "invalid command line argument" in combined_cf or "e_invalidarg" in combined_cf:
        return (
            f"WSL rejected the mount command while trying to {action_label}.\n\n"
            "This usually means the local WSL disk-mount feature is missing an option the app tried to use."
        )

    if "there are no installed distributions" in combined_cf or "no installed distributions" in combined_cf:
        return "WSL is installed, but no Linux distribution is available to attach the disk."

    if combined:
        return combined

    if exit_code == -1:
        return (
            f"WSL returned exit code -1 while trying to {action_label}.\n\n"
            "Windows did not provide a detailed reason. This commonly happens when the UAC prompt is dismissed, "
            "the SD card is already locked by another process, or WSL refuses the disk attach."
        )

    if exit_code != 0:
        return f"WSL could not {action_label}. Exit code: {exit_code}."

    return f"WSL could not {action_label}."


def is_windows_readable_filesystem_hint(filesystem: str = "", partition_type: str = "") -> bool:
    fs = str(filesystem or "").strip().casefold()
    part = str(partition_type or "").strip().casefold()

    if fs in {"fat", "fat12", "fat16", "fat32", "exfat", "ntfs"}:
        return True

    readable_tokens = ("fat", "ntfs", "exfat", "ifs")
    return any(token in part for token in readable_tokens)


def get_drive_volume_state(path_text: str) -> Optional[Dict[str, object]]:
    drive_letter = extract_drive_letter(path_text)
    if not drive_letter:
        return None

    script = (
        "$vol = Get-Volume -DriveLetter "
        + ps_quote(drive_letter)
        + " -ErrorAction SilentlyContinue; "
        + "if ($null -eq $vol) { return } "
        + "$vol | Select-Object DriveLetter,FileSystem,FileSystemLabel,DriveType,Size,HealthStatus "
        + "| ConvertTo-Json -Compress"
    )
    try:
        data = run_powershell_json(script, timeout=30)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def drive_needs_wsl_mount(path_text: str) -> bool:
    info = get_drive_volume_state(path_text)
    if not info:
        return False
    filesystem = str(info.get("FileSystem") or "").strip().upper()
    size = int(info.get("Size") or 0)
    return filesystem in ("", "RAW") or size <= 0


def discover_mount_candidates(preferred_path: str = "") -> List[MountCandidate]:
    script = r"""
$ErrorActionPreference = 'Stop'
[ordered]@{
  disks = @(Get-Disk | Select-Object Number,FriendlyName,BusType,PartitionStyle,OperationalStatus,Size,IsBoot,IsSystem,Path,SerialNumber)
  partitions = @(Get-Partition | Select-Object DiskNumber,PartitionNumber,Type,GptType,MbrType,DriveLetter,Size,AccessPaths)
  volumes = @(Get-Volume | Select-Object DriveLetter,FileSystem,FileSystemLabel,DriveType,HealthStatus,Size,SizeRemaining,Path)
  physical = @(Get-CimInstance Win32_DiskDrive | Select-Object DeviceID,Index,Model,InterfaceType,Size,MediaType)
} | ConvertTo-Json -Compress -Depth 5
"""
    snapshot = run_powershell_json(script, timeout=180)
    disks = {int(item["Number"]): item for item in ensure_list(snapshot.get("disks")) if item}
    partitions = ensure_list(snapshot.get("partitions"))
    volumes = {}
    for item in ensure_list(snapshot.get("volumes")):
        if not item:
            continue
        drive_key = normalize_drive_letter(item.get("DriveLetter"))
        if drive_key:
            volumes[drive_key] = item
    physical = {int(item["Index"]): item for item in ensure_list(snapshot.get("physical")) if item}

    preferred_drive = extract_drive_letter(preferred_path)
    preferred_disk, preferred_partition = extract_mount_signature(preferred_path)
    candidates: List[MountCandidate] = []

    for part in partitions:
        if not part:
            continue

        disk_number = int(part.get("DiskNumber", -1))
        partition_number = int(part.get("PartitionNumber", 0))
        disk = disks.get(disk_number, {})
        physical_disk = physical.get(disk_number, {})
        if not disk or not partition_number:
            continue
        if disk.get("IsBoot") or disk.get("IsSystem"):
            continue

        size = int(part.get("Size") or 0)
        if size < 256 * 1024 * 1024:
            continue

        drive_letter = normalize_drive_letter(part.get("DriveLetter"))
        volume = volumes.get(drive_letter, {})
        filesystem = str(volume.get("FileSystem") or "").strip().upper()
        partition_type = str(part.get("Type") or part.get("MbrType") or "").strip()
        drive_type = str(volume.get("DriveType") or "").strip()
        bus_type = str(disk.get("BusType") or "").strip()
        media_type = str(physical_disk.get("MediaType") or "").strip().casefold()
        is_offline = bool(disk.get("IsOffline"))
        is_read_only = bool(disk.get("IsReadOnly"))
        looks_external = (
            bus_type.upper() in {"USB", "SD", "MMC"}
            or drive_type.casefold() == "removable"
            or "removable" in media_type
            or "external" in media_type
        )
        looks_unreadable = filesystem in ("", "RAW")
        windows_recoverable = (
            (is_offline or not drive_letter)
            and is_windows_readable_filesystem_hint(filesystem, partition_type)
        )

        if (
            not looks_unreadable
            and not is_offline
            and preferred_disk != disk_number
            and not (preferred_drive and drive_letter == preferred_drive)
        ):
            continue

        score = 0
        if preferred_drive and drive_letter == preferred_drive:
            score += 120
        if preferred_disk == disk_number:
            score += 140
            if preferred_partition == partition_number:
                score += 80
        if looks_unreadable:
            score += 80
        if is_offline:
            score += 60
        if looks_external:
            score += 40
        if not drive_letter:
            score += 10
        if windows_recoverable:
            score += 45
        if size >= 1024 * 1024 * 1024:
            score += 5

        friendly_name = str(disk.get("FriendlyName") or physical_disk.get("Model") or f"Disk {disk_number}").strip()
        physical_drive = str(physical_disk.get("DeviceID") or fr"\\.\PHYSICALDRIVE{disk_number}")
        mount_name = f"sf3000-disk{disk_number}-part{partition_number}"
        candidates.append(
            MountCandidate(
                disk_number=disk_number,
                partition_number=partition_number,
                physical_drive=physical_drive,
                friendly_name=friendly_name,
                drive_letter=drive_letter,
                filesystem=filesystem,
                size=size,
                bus_type=bus_type or "Unknown",
                mount_name=mount_name,
                partition_type=partition_type,
                is_offline=is_offline,
                is_read_only=is_read_only,
                windows_recoverable=windows_recoverable,
                score=score,
            )
        )

    candidates.sort(key=lambda item: (item.score, item.size), reverse=True)
    return candidates


def choose_auto_mount_candidate(
    candidates: Sequence[MountCandidate],
    preferred_path: str = "",
) -> Optional[MountCandidate]:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    preferred_drive = extract_drive_letter(preferred_path)
    preferred_disk, preferred_partition = extract_mount_signature(preferred_path)

    if preferred_disk is not None and preferred_partition is not None:
        for candidate in candidates:
            if (
                candidate.disk_number == preferred_disk
                and candidate.partition_number == preferred_partition
            ):
                return candidate

    if preferred_drive:
        matching_drive = [candidate for candidate in candidates if candidate.drive_letter == preferred_drive]
        if len(matching_drive) == 1:
            return matching_drive[0]

    if len(candidates) > 1 and candidates[0].score >= candidates[1].score + 45:
        return candidates[0]
    return None


def run_elevated_wsl_command(
    arguments: Sequence[str],
    action_label: str,
    timeout: int = 240,
) -> Tuple[bool, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="sf3000-wsl-"))
    wrapper_path = temp_dir / "run_wsl_command.ps1"
    stdout_path = temp_dir / "stdout.txt"
    stderr_path = temp_dir / "stderr.txt"

    wrapper_script = (
        "param(\n"
        "    [string]$StdoutPath,\n"
        "    [string]$StderrPath\n"
        ")\n"
        "$ErrorActionPreference = 'Stop'\n"
        "$arguments = "
        + ps_quote(json.dumps(list(arguments)))
        + " | ConvertFrom-Json\n"
        "& wsl.exe @arguments 1> $StdoutPath 2> $StderrPath\n"
        "exit $LASTEXITCODE\n"
    )

    try:
        wrapper_path.write_text(wrapper_script, encoding="utf-8")
        command = (
            "$ErrorActionPreference = 'Stop'; "
            f"$proc = Start-Process -FilePath {ps_quote('powershell.exe')} "
            + "-ArgumentList @("
            + ", ".join(
                [
                    ps_quote("-NoProfile"),
                    ps_quote("-NonInteractive"),
                    ps_quote("-ExecutionPolicy"),
                    ps_quote("Bypass"),
                    ps_quote("-File"),
                    ps_quote(str(wrapper_path)),
                    ps_quote(str(stdout_path)),
                    ps_quote(str(stderr_path)),
                ]
            )
            + ") -Verb RunAs -Wait -PassThru; "
            + "Write-Output $proc.ExitCode"
        )
        code, stdout, stderr = run_captured_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while waiting for WSL to {action_label}."
    except Exception as exc:
        return False, str(exc)
    finally:
        elevated_stdout = ""
        elevated_stderr = ""
        try:
            if stdout_path.exists():
                elevated_stdout = decode_subprocess_output(stdout_path.read_bytes())
            if stderr_path.exists():
                elevated_stderr = decode_subprocess_output(stderr_path.read_bytes())
        except Exception:
            pass

    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        exit_code = int(lines[-1]) if lines else 0
    except ValueError:
        exit_code = code

    if code != 0:
        message = format_wsl_command_failure(action_label, code, stdout, stderr)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, message

    if exit_code != 0:
        message = format_wsl_command_failure(action_label, exit_code, elevated_stdout, elevated_stderr)
        if "WSL rejected the mount command" in message and "--type" in arguments:
            retry_arguments = []
            skip_next = False
            for arg in arguments:
                if skip_next:
                    skip_next = False
                    continue
                if arg == "--type":
                    skip_next = True
                    continue
                retry_arguments.append(arg)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return run_elevated_wsl_command(retry_arguments, action_label, timeout=timeout)
        if "WSL rejected the mount command" in message and "--name" in arguments:
            retry_arguments = []
            skip_next = False
            for arg in arguments:
                if skip_next:
                    skip_next = False
                    continue
                if arg == "--name":
                    skip_next = True
                    continue
                retry_arguments.append(arg)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return run_elevated_wsl_command(retry_arguments, action_label, timeout=timeout)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, message

    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, ""


def run_elevated_wsl_mount(candidate: MountCandidate, timeout: int = 240) -> Tuple[bool, str]:
    arguments = [
        "--mount",
        candidate.physical_drive,
        "--partition",
        str(candidate.partition_number),
        "--type",
        "ext4",
        "--name",
        candidate.mount_name,
    ]
    return run_elevated_wsl_command(arguments, "mount the SD card", timeout=timeout)


def run_elevated_wsl_unmount(physical_drive: str, timeout: int = 240) -> Tuple[bool, str]:
    return run_elevated_wsl_command(["--unmount", physical_drive], "unmount the device", timeout=timeout)


def run_elevated_windows_disk_recovery(
    candidate: MountCandidate,
    timeout: int = 240,
) -> Tuple[bool, str, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="sf3000-disk-"))
    wrapper_path = temp_dir / "recover_disk.ps1"
    stdout_path = temp_dir / "stdout.txt"
    stderr_path = temp_dir / "stderr.txt"

    wrapper_script = f"""param(
    [string]$StdoutPath,
    [string]$StderrPath
)
$ErrorActionPreference = 'Stop'
try {{
    $disk = Get-Disk -Number {candidate.disk_number} -ErrorAction Stop
    if ($disk.IsOffline) {{
        Set-Disk -Number {candidate.disk_number} -IsOffline $false -ErrorAction Stop
    }}
    if ($disk.IsReadOnly) {{
        Set-Disk -Number {candidate.disk_number} -IsReadOnly $false -ErrorAction Stop
    }}
    $part = Get-Partition -DiskNumber {candidate.disk_number} -PartitionNumber {candidate.partition_number} -ErrorAction Stop
    if (-not $part.DriveLetter) {{
        Add-PartitionAccessPath -DiskNumber {candidate.disk_number} -PartitionNumber {candidate.partition_number} -AssignDriveLetter -ErrorAction Stop
        $part = Get-Partition -DiskNumber {candidate.disk_number} -PartitionNumber {candidate.partition_number} -ErrorAction Stop
    }}
    if (-not $part.DriveLetter) {{
        throw 'Windows could not assign a drive letter to the SD card.'
    }}
    Set-Content -LiteralPath $StdoutPath -Value $part.DriveLetter -Encoding UTF8
}} catch {{
    Set-Content -LiteralPath $StderrPath -Value $_.Exception.Message -Encoding UTF8
    exit 1
}}
"""

    try:
        wrapper_path.write_text(wrapper_script, encoding="utf-8")
        command = (
            "$ErrorActionPreference = 'Stop'; "
            f"$proc = Start-Process -FilePath {ps_quote('powershell.exe')} "
            + "-ArgumentList @("
            + ", ".join(
                [
                    ps_quote("-NoProfile"),
                    ps_quote("-NonInteractive"),
                    ps_quote("-ExecutionPolicy"),
                    ps_quote("Bypass"),
                    ps_quote("-File"),
                    ps_quote(str(wrapper_path)),
                    ps_quote(str(stdout_path)),
                    ps_quote(str(stderr_path)),
                ]
            )
            + ") -Verb RunAs -Wait -PassThru; "
            + "Write-Output $proc.ExitCode"
        )
        code, stdout, stderr = run_captured_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "", "Timed out while waiting for Windows to recover the SD card."
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "", str(exc)

    drive_letter = ""
    elevated_stdout = ""
    elevated_stderr = ""
    try:
        if stdout_path.exists():
            elevated_stdout = decode_subprocess_output(stdout_path.read_bytes())
            drive_letter = normalize_drive_letter(elevated_stdout)
        if stderr_path.exists():
            elevated_stderr = decode_subprocess_output(stderr_path.read_bytes())
    except Exception:
        pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        exit_code = int(lines[-1]) if lines else 0
    except ValueError:
        exit_code = code

    if code != 0 or exit_code != 0:
        message = clean_command_output(elevated_stderr or stderr or elevated_stdout or stdout)
        if not message:
            if exit_code == 1223:
                message = "The Windows elevation prompt was canceled."
            else:
                message = "Windows could not bring the SD card online automatically."
        return False, "", message

    if not drive_letter:
        try:
            script = (
                "$part = Get-Partition -DiskNumber "
                + str(candidate.disk_number)
                + " -PartitionNumber "
                + str(candidate.partition_number)
                + " -ErrorAction Stop; "
                + "$part | Select-Object DriveLetter | ConvertTo-Json -Compress"
            )
            part_info = run_powershell_json(script, timeout=30)
            drive_letter = normalize_drive_letter((part_info or {}).get("DriveLetter"))
        except Exception:
            drive_letter = ""

    if not drive_letter:
        return False, "", "Windows recovered the disk, but no drive letter was assigned."

    return True, f"{drive_letter}:\\", ""


def eject_drive_letter(drive_letter: str, timeout: int = 60) -> Tuple[bool, str]:
    letter = normalize_drive_letter(drive_letter)
    if not letter:
        return False, "No removable drive letter is available to eject."

    script = f"""
$ErrorActionPreference = 'Stop'
$drive = '{letter}:'
$vol = Get-WmiObject Win32_Volume -Filter "DriveLetter = '$drive'" -ErrorAction SilentlyContinue
if ($vol) {{
    [void]$vol.Dismount($false, $false)
}}
$shell = New-Object -ComObject Shell.Application
$item = $shell.Namespace(17).ParseName($drive)
if ($null -eq $item) {{
    throw "Drive $drive could not be found in the Shell namespace."
}}
$item.InvokeVerb('Eject')
"""
    try:
        code, stdout, stderr = run_captured_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            timeout=timeout,
        )
    except Exception as exc:
        return False, str(exc)
    if code != 0:
        return False, stderr or stdout or f"Could not eject {letter}:."
    return True, ""


def collect_disk_metadata() -> Dict[str, Dict[int, Dict[str, object]]]:
    script = r"""
$ErrorActionPreference = 'Stop'
[ordered]@{
  disks = @(Get-Disk | Select-Object Number,FriendlyName,BusType,PartitionStyle,OperationalStatus,Size,IsBoot,IsSystem,Path,SerialNumber)
  physical = @(Get-CimInstance Win32_DiskDrive | Select-Object DeviceID,Index,Model,InterfaceType,Size,MediaType)
} | ConvertTo-Json -Compress -Depth 4
"""
    snapshot = run_powershell_json(script, timeout=120)
    disks = {int(item["Number"]): item for item in ensure_list(snapshot.get("disks")) if item}
    physical = {int(item["Index"]): item for item in ensure_list(snapshot.get("physical")) if item}
    return {"disks": disks, "physical": physical}
