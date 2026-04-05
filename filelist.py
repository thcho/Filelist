#!/usr/bin/env python3
"""특정 폴더에 있는 파일들의 버전, 크기, 만든 날짜를 텍스트로 출력하는 프로그램."""

import argparse
import os
import platform
import struct
import sys
from datetime import datetime


def format_size(size_bytes: int) -> str:
    """파일 크기를 사람이 읽기 쉬운 형식으로 변환."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def get_creation_date(filepath: str) -> str:
    """파일의 만든 날짜를 반환. Windows는 ctime, 그 외는 가능한 birth time 사용."""
    stat = os.stat(filepath)
    if platform.system() == "Windows":
        timestamp = stat.st_ctime
    else:
        # Linux/macOS: st_birthtime이 있으면 사용, 없으면 st_mtime 사용
        timestamp = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _get_version_win32(filepath: str) -> str | None:
    """Windows API(version.dll)를 사용하여 파일 버전을 추출."""
    import ctypes
    from ctypes import wintypes

    version_dll = ctypes.windll.version
    kernel32 = ctypes.windll.kernel32

    # GetFileVersionInfoSizeW
    size = version_dll.GetFileVersionInfoSizeW(filepath, None)
    if not size:
        return None

    # GetFileVersionInfoW
    buf = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(filepath, 0, size, buf):
        return None

    # VerQueryValueW - VS_FIXEDFILEINFO 구조체 가져오기
    pval = ctypes.c_void_p()
    ulen = wintypes.UINT()
    if not version_dll.VerQueryValueW(buf, "\\", ctypes.byref(pval), ctypes.byref(ulen)):
        return None

    if ulen.value == 0:
        return None

    # VS_FIXEDFILEINFO 구조체에서 버전 읽기
    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
        ]

    info = ctypes.cast(pval, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    if info.dwSignature != 0xFEEF04BD:
        return None

    major = (info.dwFileVersionMS >> 16) & 0xFFFF
    minor = info.dwFileVersionMS & 0xFFFF
    build = (info.dwFileVersionLS >> 16) & 0xFFFF
    patch = info.dwFileVersionLS & 0xFFFF
    return f"{major}.{minor}.{build}.{patch}"


def _get_version_binary(filepath: str) -> str | None:
    """PE 파일에서 VS_FIXEDFILEINFO 시그니처를 직접 검색하여 버전 추출 (비Windows 폴백)."""
    try:
        with open(filepath, "rb") as f:
            # MZ 헤더 확인
            if f.read(2) != b"MZ":
                return None
            # 파일 전체를 읽어서 시그니처 검색 (최대 10MB)
            f.seek(0)
            data = f.read(10 * 1024 * 1024)

        sig = struct.pack("<I", 0xFEEF04BD)
        idx = data.find(sig)
        if idx == -1:
            return None

        fixed = data[idx : idx + 52]
        if len(fixed) < 52:
            return None

        # dwStrucVersion 검증 (보통 0x00010000)
        struc_ver = struct.unpack("<I", fixed[4:8])[0]
        if struc_ver == 0:
            return None

        file_ver_ms = struct.unpack("<I", fixed[8:12])[0]
        file_ver_ls = struct.unpack("<I", fixed[12:16])[0]
        major = (file_ver_ms >> 16) & 0xFFFF
        minor = file_ver_ms & 0xFFFF
        build = (file_ver_ls >> 16) & 0xFFFF
        patch = file_ver_ls & 0xFFFF
        return f"{major}.{minor}.{build}.{patch}"
    except Exception:
        return None


def get_file_version(filepath: str) -> str:
    """파일의 버전 정보를 반환."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in (".exe", ".dll", ".sys", ".ocx", ".drv"):
        return "N/A"

    # Windows: version.dll API 사용 (가장 정확)
    if platform.system() == "Windows":
        try:
            version = _get_version_win32(filepath)
            if version:
                return version
        except Exception:
            pass

    # 폴백: 바이너리에서 시그니처 직접 검색
    version = _get_version_binary(filepath)
    if version:
        return version

    return "N/A"


def list_files(folder: str, recursive: bool = False, output_file: str | None = None):
    """폴더 내 파일 목록과 메타데이터를 출력."""
    if not os.path.isdir(folder):
        print(f"오류: '{folder}'는 존재하지 않거나 폴더가 아닙니다.", file=sys.stderr)
        sys.exit(1)

    folder = os.path.abspath(folder)
    files = []

    if recursive:
        for root, _, filenames in os.walk(folder):
            for name in filenames:
                files.append(os.path.join(root, name))
    else:
        for entry in os.scandir(folder):
            if entry.is_file():
                files.append(entry.path)

    files.sort()

    # 컬럼 헤더
    header = f"{'파일명':<40} {'버전':<20} {'크기':>12} {'만든 날짜':<20}"
    separator = "-" * len(header)

    lines = []
    lines.append(f"폴더: {folder}")
    lines.append(f"파일 수: {len(files)}")
    lines.append("")
    lines.append(header)
    lines.append(separator)

    for filepath in files:
        try:
            name = os.path.relpath(filepath, folder)
            version = get_file_version(filepath)
            size = format_size(os.path.getsize(filepath))
            created = get_creation_date(filepath)
            lines.append(f"{name:<40} {version:<20} {size:>12} {created:<20}")
        except OSError as e:
            lines.append(f"{name:<40} {'오류':<20} {'':>12} {str(e):<20}")

    lines.append(separator)
    output = "\n".join(lines)

    print(output)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"\n결과가 '{output_file}'에 저장되었습니다.")


def main():
    # Windows 콘솔 인코딩 문제 방지
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="특정 폴더에 있는 파일들의 버전, 크기, 만든 날짜를 텍스트로 출력합니다."
    )
    parser.add_argument("folder", help="검색할 폴더 경로")
    parser.add_argument("-r", "--recursive", action="store_true", help="하위 폴더도 포함")
    parser.add_argument("-o", "--output", help="결과를 저장할 텍스트 파일 경로")

    args = parser.parse_args()
    list_files(args.folder, args.recursive, args.output)


if __name__ == "__main__":
    main()
