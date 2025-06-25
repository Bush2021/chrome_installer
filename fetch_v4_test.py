import json
import gzip
import requests
from datetime import datetime
import base64


class OmahaV4Client:
    """Omaha v4 协议客户端 - 仅供测试使用"""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://update.googleapis.com/service/update2/json"
        self.headers = {
            "Cache-Control": "no-cache",
            "Connection": "Keep-Alive",
            "Pragma": "no-cache",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "GoogleUpdater 138.0.7194.0",
            "X-Goog-Update-AppId": "{8a69d345-d564-463c-aff1-a69d9e530f96}",
            "X-Goog-Update-Interactivity": "fg",
            "X-Goog-Update-Updater": "updater-138.0.7194.0",
        }

    def build_request_payload(
        self,
        arch="x64",
        channel="stable",
        appid="{8a69d345-d564-463c-aff1-a69d9e530f96}",
    ):
        arch_mapping = {
            "x86": {"arch": "x86", "ap": "x86-stable", "nacl_arch": "x86-32"},
            "x64": {"arch": "x64", "ap": "x64-stable", "nacl_arch": "x86-64"},
            "arm64": {"arch": "arm64", "ap": "arm64-stable", "nacl_arch": "arm64"},
        }
        channel_mapping = {
            "stable": "stable",
            "beta": "1.1-beta",
            "dev": "2.0-dev",
            "canary": "canary",
        }

        arch_info = arch_mapping.get(arch, arch_mapping["x64"])
        channel_prefix = channel_mapping.get(channel, "stable")
        if channel == "stable":
            ap_field = arch_info["ap"]
        else:
            ap_field = f"{channel_prefix}-arch_{arch}"
        payload = {
            "request": {
                "@os": "win",
                "@updater": "updater",
                "acceptformat": "crx3,download,puff,run,xz,zucc",
                "apps": [
                    {
                        "ap": ap_field,
                        "appid": appid,
                        "data": [{"index": "empty", "name": "install"}],
                        "enabled": True,
                        "iid": "{2A9FDDBC-A63B-2276-9FD2-CD64FB64059B}",
                        "installdate": -1,
                        "installsource": "taggedmi",
                        "updatecheck": {"sameversionupdate": True},
                        "version": "0.0.0.0",
                    }
                ],
                "arch": arch_info["arch"],
                "dedup": "cr",
                "domainjoined": False,
                "hw": {
                    "avx": True,
                    "sse": True,
                    "sse2": True,
                    "sse3": True,
                    "sse41": True,
                    "sse42": True,
                    "ssse3": True,
                },
                "ismachine": True,
                "nacl_arch": arch_info["nacl_arch"],
                "os": {
                    "arch": "x86_64" if arch != "x86" else "x86",
                    "platform": "Windows",
                    "version": "10.0.19044.5737",
                },
                "prodversion": "138.0.7194.0",
                "protocol": "4.0",
                "updaterversion": "138.0.7194.0",
                "wow64": arch == "x64",
            }
        }

        return payload

    def make_request(
        self,
        arch="x64",
        channel="stable",
        appid="{8a69d345-d564-463c-aff1-a69d9e530f96}",
    ):
        payload = self.build_request_payload(arch, channel, appid)

        response = self.session.post(self.base_url, headers=self.headers, json=payload)

        response.raise_for_status()
        return response

    def decode_response(self, response):
        content = response.content
        try:
            if response.headers.get("content-encoding") == "gzip":
                content = gzip.decompress(content)
        except gzip.BadGzipFile:
            # Use the original content if decompression fails
            pass
        text = content.decode("utf-8")

        # https://chromium.googlesource.com/chromium/src/+/refs/tags/138.0.7204.50/docs/updater/protocol_4.md#Safe-JSON-Prefixes
        if text.startswith(")]}'\n"):
            text = text[5:]

        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            print(f"响应内容前500字符: {text[:500]}...")
            print(f"响应头: {dict(response.headers)}")
            return None

    def extract_download_urls(self, response_data):
        download_info = []

        if not response_data or "response" not in response_data:
            return download_info

        apps = response_data["response"].get("apps", [])

        for app in apps:
            updatecheck = app.get("updatecheck", {})
            if updatecheck.get("status") != "ok":
                continue
            version = updatecheck.get("nextversion", "unknown")
            pipelines = updatecheck.get("pipelines", [])

            for pipeline in pipelines:
                pipeline_id = pipeline.get("pipeline_id", "")
                operations = pipeline.get("operations", [])
                for operation in operations:
                    if operation.get("type") == "download":
                        size = operation.get("size", 0)
                        sha256 = operation.get("out", {}).get("sha256", "")
                        urls = [
                            url_obj.get("url", "")
                            for url_obj in operation.get("urls", [])
                        ]

                        download_info.append(
                            {
                                "version": version,
                                "pipeline_id": pipeline_id,
                                "size": size,
                                "sha256": sha256,
                                "urls": urls,
                                "type": "download",
                            }
                        )

        return download_info

    def get_chrome_update_info(
        self,
        arch="x64",
        channel="stable",
        appid="{8a69d345-d564-463c-aff1-a69d9e530f96}",
    ):
        try:
            print(f"正在请求 {channel} {arch} 的更新信息...")
            response = self.make_request(arch, channel, appid)
            response_data = self.decode_response(response)

            if response_data is None:
                return None
            download_info = self.extract_download_urls(response_data)

            return {
                "arch": arch,
                "channel": channel,
                "appid": appid,
                "raw_response": response_data,
                "download_info": download_info,
            }

        except Exception as e:
            print(f"请求失败: {e}")
            return None


def test_v4_protocol():
    """测试 v4 协议"""
    client = OmahaV4Client()
    test_configs = [
        {"arch": "x64", "channel": "stable"},
        {"arch": "x86", "channel": "stable"},
        {"arch": "arm64", "channel": "stable"},
    ]

    results = {}

    for config in test_configs:
        key = f"win_{config['channel']}_{config['arch']}"
        print(f"\n=== 测试 {key} ===")

        result = client.get_chrome_update_info(
            arch=config["arch"], channel=config["channel"]
        )

        if result:
            results[key] = result
            download_info = result["download_info"]
            if download_info:
                for i, info in enumerate(download_info):
                    print(f"  下载选项 {i+1}:")
                    print(f"    版本: {info['version']}")
                    print(f"    大小: {info['size']} bytes")
                    print(f"    SHA256: {info['sha256']}")
                    print(f"    链接数量: {len(info['urls'])}")
                    if info["urls"]:
                        print(f"    链接: {info['urls'][1]}")
            else:
                print("  未找到下载信息")
        else:
            print(f"  {key} 请求失败")

    return results


def save_v4_response(response_data, filename="response_v4.json"):
    if response_data:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        print(f"v4 响应已保存到 {filename}")


def compare_v3_v4_results():
    print("\n=== v3 vs v4 比较 ===")

    # 读取 v3 结果
    try:
        with open("data.json", "r") as f:
            v3_data = json.load(f)
    except FileNotFoundError:
        print("未找到 v3 数据文件 data.json")
        return
    client = OmahaV4Client()
    v4_result = client.get_chrome_update_info(arch="x64", channel="stable")

    if v4_result and v4_result["download_info"]:
        v4_info = v4_result["download_info"][1]
        v3_info = v3_data.get("win_stable_x64", {})

        print(f"v3 版本: {v3_info.get('version', 'unknown')}")
        print(f"v4 版本: {v4_info.get('version', 'unknown')}")
        print(f"v3 大小: {v3_info.get('size', 0)} bytes")
        print(f"v4 大小: {v4_info.get('size', 0)} bytes")
        print(f"版本一致: {v3_info.get('version') == v4_info.get('version')}")


if __name__ == "__main__":
    print("=== Omaha v4 协议测试 ===")
    results = test_v4_protocol()
    if results:
        first_result = next(iter(results.values()))
        save_v4_response(first_result["raw_response"])
    compare_v3_v4_results()

    print("\n测试完成！")
