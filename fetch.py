import base64
import os
import json
import xml.etree.ElementTree as tree
from datetime import datetime, timezone, timedelta
import argparse
from pathlib import Path

import requests
import config

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

update_url = config.FETCH_API_URL

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
        print("错误: manifest_node为空")
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


def load_json(file_path=None):
    """加载JSON文件, 如果文件不存在则返回空字典"""
    if file_path is None:
        file_path = config.FETCH_OUTPUT_JSON_PATH
    
    if not os.path.exists(file_path):
        return {}
    
    try:
        with open(file_path, "r") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, ValueError):
        return {}


def fetch(info, results, api_url=None):
    global update_url
    if api_url:
        update_url = api_url
        
    for k, v in info.items():
        res = post(**v)
        data = decode(res)
        if data is None:
            print(f"错误: {k} 未返回数据")
            continue
        if version_tuple(data["version"]) < version_tuple(
            results.get(k, {}).get("version", "0.0.0.0")
        ):
            print("忽略", k, data["version"])
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


def save_json(results, file_path=None):
    """保存JSON文件, 默认使用配置中的路径"""
    if file_path is None:
        file_path = config.FETCH_OUTPUT_JSON_PATH
    
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
    with open(file_path, "w") as f:
        json.dump(results, f, indent=4)
    
    print(f"已保存JSON数据到 {file_path}")


def filter_info_by_channels_and_platforms(channels, platforms):
    """根据指定的频道和平台过滤info字典"""
    if not channels and not platforms:
        return info
    
    filtered_info = {}
    for key, value in info.items():
        # 解析键名为频道和平台部分
        parts = key.split('_')
        if len(parts) >= 3:
            platform = parts[0]  # win
            channel = parts[1]   # stable/beta/dev/canary
            arch = parts[2]      # x86/x64/arm64
            
            # 检查频道和平台
            channel_match = not channels or channel in channels
            platform_match = not platforms or platform in platforms
            
            if channel_match and platform_match:
                filtered_info[key] = value
    
    return filtered_info


def main():
    # 从配置中获取默认参数
    default_api_url = config.FETCH_API_URL
    default_channels = config.FETCH_CHANNELS
    default_platforms = config.FETCH_PLATFORMS
    default_json_path = config.FETCH_OUTPUT_JSON_PATH
    
    parser = argparse.ArgumentParser(description='获取Chrome版本信息')
    parser.add_argument(
        '--api-url',
        default=default_api_url,
        help=f'API URL (默认: {default_api_url})'
    )
    parser.add_argument(
        '--channels',
        nargs='+',
        default=default_channels,
        choices=['stable', 'beta', 'dev', 'canary'],
        help=f'要获取的频道 (默认: {", ".join(default_channels)})'
    )
    parser.add_argument(
        '--platforms',
        nargs='+',
        default=default_platforms,
        choices=['win', 'mac', 'linux'],
        help=f'要获取的平台 (默认: {", ".join(default_platforms)})'
    )
    parser.add_argument(
        '--json-file',
        default=default_json_path,
        help=f'JSON输出文件 (默认: {default_json_path})'
    )
    parser.add_argument(
        '--no-readme',
        action='store_true',
        help='不生成README.md文件'
    )
    
    args = parser.parse_args()
    
    # 根据频道和平台过滤info字典
    filtered_info = filter_info_by_channels_and_platforms(args.channels, args.platforms)
    
    results = load_json(args.json_file)
    fetch(filtered_info, results, args.api_url)
    save_json(results, args.json_file)
    
    # 生成README.md (通过单独的脚本或函数)
    if not args.no_readme:
        try:
            from gen_markdown import generate_readme
            readme_path = config.GEN_MARKDOWN_OUTPUT_PATH
            generate_readme(results, readme_path)
        except ImportError:
            print("警告: 未找到gen_markdown模块, 跳过README生成")


if __name__ == "__main__":
    main()
