import base64
import os
import json
import xml.etree.ElementTree as tree
from datetime import datetime, timezone, timedelta

import requests

# https://source.chromium.org/chromium/chromium/src/+/main:chrome/installer/util/additional_parameters.cc;drc=406947a0f1e0e6b596d387b6b14156f369e8c55d;l=206
info = {
    "win_stable_x86": {
        "os": '''arch="x86"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="x86-stable"''',
    },
    "win_stable_x64": {
        "os": '''arch="x64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="x64-stable"''',
    },
    "win_stable_arm64": {
        "os": '''arch="arm64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="arm64-stable"''',
    },
    "win_beta_x86": {
        "os": '''arch="x86"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="1.1-beta-arch_x86"''',
    },
    "win_beta_x64": {
        "os": '''arch="x64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="1.1-beta-arch_x64"''',
    },
    "win_beta_arm64": {
        "os": '''arch="arm64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="1.1-beta-arch_arm64"''',
    },
    "win_dev_x86": {
        "os": '''arch="x86"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="2.0-dev-arch_x86"''',
    },
    "win_dev_x64": {
        "os": '''arch="x64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="2.0-dev-arch_x64"''',
    },
    "win_dev_arm64": {
        "os": '''arch="arm64"''',
        "app": '''appid="{8A69D345-D564-463C-AFF1-A69D9E530F96}" ap="2.0-dev-arch_arm64"''',
    },
    "win_canary_x86": {
        "os": '''arch="x86"''',
        "app": '''appid="{4EA16AC7-FD5A-47C3-875B-DBF4A2008C20}" ap="x86-canary"''',
    },
    "win_canary_x64": {
        "os": '''arch="x64"''',
        "app": '''appid="{4EA16AC7-FD5A-47C3-875B-DBF4A2008C20}" ap="x64-canary"''',
    },
    "win_canary_arm64": {
        "os": '''arch="arm64"''',
        "app": '''appid="{4EA16AC7-FD5A-47C3-875B-DBF4A2008C20}" ap="arm64-canary"''',
    },
}

update_url = "https://tools.google.com/service/update2"

session = requests.Session()


def post(os: str, app: str) -> str:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <request protocol="3.0" updater="Omaha" updaterversion="1.3.36.372" shell_version="1.3.36.352" ismachine="0" sessionid="{11111111-1111-1111-1111-111111111111}" installsource="taggedmi" requestid="{11111111-1111-1111-1111-111111111111}" dedup="cr" domainjoined="0">
    <hw physmemory="16" sse="1" sse2="1" sse3="1" ssse3="1" sse41="1" sse42="1" avx="1"/>
    <os platform="win" version="10.0.26100.1742" {os}/>
    <app version="" {app}>
    <updatecheck/>
    <data name="install" index="empty"/>
    </app>
    </request>"""
    r = session.post(update_url, data=xml)
    r.raise_for_status()
    return r.text


def decode(text):
    root = tree.fromstring(text)

    manifest_node = root.find(".//manifest")
    if manifest_node is None:
        print("Error: manifest_node is None")
        return

    manifest_version = manifest_node.get("version")

    package_node = root.find(".//package")
    package_name = package_node.get("name")
    package_size = int(package_node.get("size"))
    package_sha1 = base64.b64decode(package_node.get("hash")).hex()
    package_sha256 = package_node.get("hash_sha256")

    url_nodes = root.findall(".//url")
    url_prefixes = [node.get("codebase") + package_name for node in url_nodes]

    return {
        "version": manifest_version,
        "size": package_size,
        "sha1": package_sha1,
        "sha256": package_sha256,
        "urls": url_prefixes,
    }


def version_tuple(v):
    return tuple(map(int, v.split(".")))


def load_json(file_path="data.json"):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, ValueError):
        return {}


def fetch(info, results):
    for k, v in info.items():
        res = post(**v)
        data = decode(res)
        if data is None:
            print(f"Error: No data returned for {k}")
            continue
        if version_tuple(data["version"]) < version_tuple(
            results.get(k, {}).get("version", "0.0.0.0")
        ):
            print("ignore", k, data["version"])
            continue
        results[k] = data


suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]


def humansize(nbytes):
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.0
        i += 1
    f = ("%.2f" % nbytes).rstrip("0").rstrip(".")
    return f"{f} {suffixes[i]}"


def save_md(results, file_path="readme.md"):
    def format_channel_arch(name):
        parts = name.split("_")
        return parts[0], parts[1], parts[2]  # platform, channel, arch

    channels = {}
    for name, info in results.items():
        platform, channel, arch = format_channel_arch(name)
        if channel not in channels:
            channels[channel] = {}
        channels[channel][arch] = {
            "name": name,
            "version": info["version"],
            "size": humansize(info["size"]),
            "sha256": info["sha256"],
            "url": next(
                (url for url in info["urls"] if url.startswith("https://dl.")),
                info["urls"][0] if info["urls"] else "N/A",
            ),
        }

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Google Chrome 离线安装包（请使用 7-Zip 解压）\n")
        f.write("稳定版存档：https://github.com/Bush2021/chrome_installer/releases\n\n")

        channel_order = ["stable", "beta", "dev", "canary"]
        channel_names = {
            "stable": "Stable",
            "beta": "Beta",
            "dev": "Dev",
            "canary": "Canary",
        }

        f.write("## 目录\n\n")
        for channel in channel_order:
            if channel in channels:
                channel_name = channel_names.get(channel, channel.title())
                f.write(f"- [{channel_name}](#{channel})\n")
        f.write("\n")

        for channel in channel_order:
            if channel not in channels:
                continue

            channel_name = channel_names.get(channel, channel.title())
            f.write(f"## {channel_name}\n\n")

            f.write("| 架构 | 版本号 | 文件大小 | SHA256 校验 | 下载链接 |\n")
            f.write("|------|--------|----------|-------------|----------|\n")

            arch_order = ["x86", "x64", "arm64"]
            arch_names = {"x86": "x86", "x64": "x64", "arm64": "ARM64"}

            for arch in arch_order:
                if arch in channels[channel]:
                    info = channels[channel][arch]
                    sha256_short = (
                        info["sha256"][:16] + "..."
                        if len(info["sha256"]) > 16
                        else info["sha256"]
                    )
                    arch_display = arch_names.get(arch, arch.upper())

                    f.write(
                        f"| **{arch_display}** | `{info['version']}` | {info['size']} | `{sha256_short}` | [下载]({info['url']}) |\n"
                    )

            f.write("\n")


def save_json(results, file_path="data.json"):
    with open(file_path, "w") as f:
        json.dump(results, f, indent=4)


def main():
    results = load_json()
    fetch(info, results)
    save_md(results)
    save_json(results)


if __name__ == "__main__":
    main()
