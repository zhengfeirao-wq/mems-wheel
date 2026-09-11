"""Build all six APM32F402 firmware profiles with Arm GNU Toolchain.

Source staging uses an ASCII temporary path so older Windows GNU tools also
work when the delivery directory contains Chinese characters. No flashing.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

APP = Path(__file__).resolve().parents[1]
SDK = APP.parents[1]
PROFILES = {
    "left_fingers12": 1,
    "right_fingers12": 2,
    "left_palm32_long": 3,
    "right_palm32_long": 4,
    "left_palm32_short": 5,
    "right_palm32_short": 6,
}
DRIVERS = [
    "apm32f4xx_dal", "apm32f4xx_dal_cortex", "apm32f4xx_dal_dma",
    "apm32f4xx_dal_dma_ex", "apm32f4xx_dal_flash", "apm32f4xx_dal_flash_ex",
    "apm32f4xx_dal_gpio", "apm32f4xx_dal_pmu", "apm32f4xx_dal_pmu_ex",
    "apm32f4xx_dal_rcm", "apm32f4xx_dal_rcm_ex", "apm32f4xx_dal_spi",
    "apm32f4xx_dal_uart",
]
CONFIG = ["device", "gpio", "nvic", "rcm", "spi", "usart"]


def find_compiler(value: str | None) -> Path:
    candidates = [value, os.environ.get("ARM_GCC"), shutil.which("arm-none-eabi-gcc")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "CodexTactileToolchains/bin/arm-none-eabi-gcc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise SystemExit("Arm GCC not found; pass --cc /path/to/arm-none-eabi-gcc[.exe]")


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(" ".join(command) + "\n" + result.stdout)
    return result.stdout


def source_hash() -> str:
    digest = hashlib.sha256()
    for folder in ("Source", "Include", "Config", "Project/GCC"):
        for path in sorted((APP / folder).rglob("*")):
            if path.is_file() and path.suffix in {".c", ".h", ".ld"}:
                digest.update(path.relative_to(APP).as_posix().encode())
                digest.update(path.read_bytes())
    for name in DRIVERS:
        digest.update(name.encode())
        digest.update((SDK / "Libraries/APM32F4xx_DAL_Driver/Source" / (name + ".c")).read_bytes())
    for folder in ("Libraries/CMSIS/Include", "Libraries/Device/Geehy/APM32F4xx/Include",
                   "Libraries/APM32F4xx_DAL_Driver/Include"):
        for path in sorted((SDK / folder).rglob("*.h")):
            digest.update(path.relative_to(SDK).as_posix().encode())
            digest.update(path.read_bytes())
    digest.update((SDK / "Libraries/Device/Geehy/APM32F4xx/Source/gcc/startup_apm32f402xx.S").read_bytes())
    digest.update(Path(__file__).read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc")
    parser.add_argument("--profile", choices=["all", *PROFILES], default="all")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    compiler = find_compiler(args.cc)
    suffix = ".exe" if compiler.suffix.lower() == ".exe" else ""
    objcopy = compiler.with_name("arm-none-eabi-objcopy" + suffix)
    size_tool = compiler.with_name("arm-none-eabi-size" + suffix)
    version = run([str(compiler), "--version"], APP).splitlines()[0]
    selected = PROFILES if args.profile == "all" else {args.profile: PROFILES[args.profile]}
    manifest: dict[str, object] = {"compiler": version, "source_sha256": source_hash(),
                                   "hardware_tested": False, "profiles": {}}

    with tempfile.TemporaryDirectory(prefix="tactile500_build_") as temporary:
        stage = Path(temporary)
        for folder in ("Source", "Include", "Config", "Project/GCC"):
            shutil.copytree(APP / folder, stage / folder)
        for folder in ("Libraries/CMSIS/Include", "Libraries/Device/Geehy/APM32F4xx/Include",
                       "Libraries/APM32F4xx_DAL_Driver/Include"):
            shutil.copytree(SDK / folder, stage / folder)
        driver_dir = stage / "Libraries/APM32F4xx_DAL_Driver/Source"
        driver_dir.mkdir(parents=True)
        for name in DRIVERS:
            shutil.copyfile(SDK / "Libraries/APM32F4xx_DAL_Driver/Source" / (name + ".c"),
                            driver_dir / (name + ".c"))
        startup = SDK / "Libraries/Device/Geehy/APM32F4xx/Source/gcc/startup_apm32f402xx.S"
        shutil.copyfile(startup, stage / "startup_apm32f402xx.S")

        sources = [p.relative_to(stage).as_posix() for p in sorted((stage / "Source").glob("*.c"))]
        sources += [f"Config/Source/apm32f4xx_{name}_cfg.c" for name in CONFIG]
        sources += [f"Libraries/APM32F4xx_DAL_Driver/Source/{name}.c" for name in DRIVERS]
        sources += ["startup_apm32f402xx.S"]
        flags = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard",
                 "-O2", "-g3", "-ffunction-sections", "-fdata-sections", "-fno-common",
                 "-fstack-usage", "-DUSE_DAL_DRIVER", "-DAPM32F402xx", "-DHSE_VALUE=16000000U",
                 "-DHSI_VALUE=8000000U"]
        includes = ["Include", "Config/Include", "Libraries/CMSIS/Include",
                    "Libraries/Device/Geehy/APM32F4xx/Include",
                    "Libraries/APM32F4xx_DAL_Driver/Include"]
        flags += ["-I" + path for path in includes]

        for name, profile in selected.items():
            output = stage / "objects" / name
            output.mkdir(parents=True)
            objects = [f"objects/{name}/{Path(source).stem}.o" for source in sources]

            def compile_one(pair: tuple[str, str]) -> str:
                source, obj = pair
                warnings = ["-std=c99", "-Wall", "-Wextra"] if source.endswith(".c") else []
                if source.startswith(("Source/tactile_", "Source/main.c", "Config/")):
                    warnings.append("-Werror")
                return run([str(compiler), *flags, *warnings, f"-DTACTILE_PROFILE={profile}",
                            "-c", source, "-o", obj], stage)

            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                compile_logs = list(pool.map(compile_one, zip(sources, objects)))
            stem = f"Tactile500_{name}"
            elf = f"objects/{name}/{stem}.elf"
            map_file = f"objects/{name}/{stem}.map"
            link_log = run([str(compiler), *flags, *objects, "--specs=nano.specs", "--specs=nosys.specs",
                            "-TProject/GCC/apm32f402rb_flash.ld", "-Wl,--gc-sections",
                            "-Wl,--print-memory-usage", "-Wl,-Map=" + map_file, "-o", elf], stage)
            run([str(objcopy), "-O", "ihex", elf, f"objects/{name}/{stem}.hex"], stage)
            run([str(objcopy), "-O", "binary", elf, f"objects/{name}/{stem}.bin"], stage)
            size = run([str(size_tool), elf], stage)
            destination = APP / "build/gcc" / name
            destination.mkdir(parents=True, exist_ok=True)
            for extension in (".elf", ".hex", ".bin", ".map"):
                shutil.copyfile(output / (stem + extension), destination / (stem + extension))
            (destination / "build.log").write_text("".join(compile_logs) + link_log + size,
                                                    encoding="utf-8")
            manifest["profiles"][name] = {"profile_id": profile, "size": size.strip(),
                "bin_sha256": hashlib.sha256((destination / (stem + ".bin")).read_bytes()).hexdigest(),
                "hex_sha256": hashlib.sha256((destination / (stem + ".hex")).read_bytes()).hexdigest()}
            print(name + ": " + size.splitlines()[-1].strip(), flush=True)
    (APP / "build/gcc/build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                       encoding="utf-8")
    print("Build complete. Hardware timing and sensor freshness still require bench verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
