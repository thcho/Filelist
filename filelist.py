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


def get_file_version_pe(filepath: str) -> str | None:
    """PE 파일(exe, dll)에서 파일 버전 정보를 추출 (순수 Python, 외부 라이브러리 불필요)."""
    try:
        with open(filepath, "rb") as f:
            # MZ 헤더 확인
            if f.read(2) != b"MZ":
                return None
            f.seek(0x3C)
            pe_offset = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_offset)
            if f.read(4) != b"PE\x00\x00":
                return None

            # COFF 헤더
            f.read(2)  # Machine
            num_sections = struct.unpack("<H", f.read(2))[0]
            f.read(12)  # TimeDateStamp, PointerToSymbolTable, NumberOfSymbols
            size_of_optional = struct.unpack("<H", f.read(2))[0]
            f.read(2)  # Characteristics

            if size_of_optional == 0:
                return None

            optional_start = f.tell()
            magic = struct.unpack("<H", f.read(2))[0]
            is_pe32_plus = magic == 0x20B

            # Resource directory RVA 가져오기
            if is_pe32_plus:
                f.seek(optional_start + 136)
            else:
                f.seek(optional_start + 120)
            resource_rva = struct.unpack("<I", f.read(4))[0]
            f.read(4)  # resource size

            if resource_rva == 0:
                return None

            # 섹션 헤더에서 .rsrc 찾기
            f.seek(optional_start + size_of_optional)
            rsrc_offset = None
            for _ in range(num_sections):
                section_data = f.read(40)
                name = section_data[:8].rstrip(b"\x00")
                virtual_addr = struct.unpack("<I", section_data[12:16])[0]
                raw_size = struct.unpack("<I", section_data[16:20])[0]
                raw_offset = struct.unpack("<I", section_data[20:24])[0]
                if virtual_addr <= resource_rva < virtual_addr + raw_size:
                    rsrc_offset = raw_offset + (resource_rva - virtual_addr)
                    rsrc_base_rva = virtual_addr
                    rsrc_base_raw = raw_offset
                    break

            if rsrc_offset is None:
                return None

            # VS_VERSION_INFO를 리소스에서 찾기
            def rva_to_raw(rva):
                return rsrc_base_raw + (rva - rsrc_base_rva)

            # RT_VERSION (16) 리소스 탐색
            f.seek(rsrc_offset + 12)
            num_named = struct.unpack("<H", f.read(2))[0]
            num_id = struct.unpack("<H", f.read(2))[0]

            version_entry_offset = None
            for _ in range(num_named + num_id):
                entry_id = struct.unpack("<I", f.read(4))[0]
                entry_offset = struct.unpack("<I", f.read(4))[0]
                if entry_id == 16:  # RT_VERSION
                    version_entry_offset = entry_offset & 0x7FFFFFFF
                    break

            if version_entry_offset is None:
                return None

            # 두 번째 레벨
            f.seek(rsrc_offset + version_entry_offset + 12)
            num_named = struct.unpack("<H", f.read(2))[0]
            num_id = struct.unpack("<H", f.read(2))[0]
            if num_named + num_id == 0:
                return None
            f.read(4)  # skip ID
            entry_offset = struct.unpack("<I", f.read(4))[0]

            # 세 번째 레벨
            level3_offset = entry_offset & 0x7FFFFFFF
            f.seek(rsrc_offset + level3_offset + 12)
            num_named = struct.unpack("<H", f.read(2))[0]
            num_id = struct.unpack("<H", f.read(2))[0]
            if num_named + num_id == 0:
                return None
            f.read(4)  # skip ID
            data_entry_offset = struct.unpack("<I", f.read(4))[0]

            # 데이터 엔트리 (최상위 비트가 0이면 리프 노드)
            if data_entry_offset & 0x80000000:
                return None
            f.seek(rsrc_offset + data_entry_offset)
            data_rva = struct.unpack("<I", f.read(4))[0]
            data_size = struct.unpack("<I", f.read(4))[0]

            # VS_VERSIONINFO 데이터 읽기
            raw_pos = rva_to_raw(data_rva)
            f.seek(raw_pos)
            version_data = f.read(min(data_size, 4096))

            # VS_FIXEDFILEINFO 시그니처(0xFEEF04BD) 찾기
            sig = struct.pack("<I", 0xFEEF04BD)
            idx = version_data.find(sig)
            if idx == -1:
                return None

            fixed = version_data[idx : idx + 52]
            if len(fixed) < 52:
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
    if ext in (".exe", ".dll", ".sys", ".ocx", ".drv"):
        version = get_file_version_pe(filepath)
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
