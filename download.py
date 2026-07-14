import argparse
import hashlib
import json
import os
import requests
import shutil
import subprocess


def version_tuple(v):
    return tuple(map(int, (v.split("."))))


def get_last_version():
    result = subprocess.run(
        ["git", "tag", "--sort=-creatordate"], capture_output=True, text=True
    )
    version = result.stdout.split("\n")[0].strip()
    return version if version else "0.0.0.0"


def check_update(arch_key):
    last_version = get_last_version()
    with open("data.json", "r") as f:
        data = json.load(f)
        latest_version = data[arch_key]["version"]
    github_env = os.getenv("GITHUB_ENV")
    if github_env and os.path.exists(github_env):
        with open(github_env, "a") as env_file:
            env_file.write(f"latest_version={latest_version}\n")
    return version_tuple(last_version) < version_tuple(latest_version)


def get_download_info(arch_key):
    with open("data.json", "r") as f:
        data = json.load(f)
        entry = data[arch_key]
        version = entry["version"]
        urls = entry["urls"]
        download_url = next(
            (u for u in urls if u.startswith("https://") and "google.com" in u),
            urls[0],
        )
        sha256 = entry["sha256"]
    return version, download_url, sha256


def download_for_arch(arch_key):
    if check_update(arch_key):
        print(f"New version detected for {arch_key}, start downloading...")
        version, url, expected_sha256 = get_download_info(arch_key)
        arch_id = arch_key.split("_")[-1]
        filename = f"{arch_id}_{url.split('/')[-1]}"

        if os.path.exists(filename):
            print(f"The file {filename} already exists, skip downloading")
            return
        r = requests.get(url, stream=True)
        r.raise_for_status()
        digest = hashlib.sha256()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    digest.update(chunk)
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256.lower():
            os.remove(filename)
            raise SystemExit(
                f"SHA256 mismatch for {arch_key}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        print(f"Download complete and verified for {arch_key}")
    else:
        print(f"No new version detected for {arch_key}, skip downloading")


def main():
    parser = argparse.ArgumentParser(
        description="Download Chrome installers for different architectures"
    )
    parser.add_argument(
        "--arch",
        nargs="+",
        default=["win_stable_x64"],
        choices=["win_stable_x86", "win_stable_x64", "win_stable_arm64"],
        help="Architecture(s) to download (default: win_stable_x64)",
    )
    args = parser.parse_args()
    for arch in args.arch:
        download_for_arch(arch)
    if os.path.exists("__pycache__"):
        shutil.rmtree("__pycache__")


if __name__ == "__main__":
    main()
