import argparse
import json
import os
import requests
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

def version_tuple(v):
    return tuple(map(int, (v.split("."))))


def get_last_version():
    result = subprocess.run(
        ["git", "tag", "--sort=-creatordate"], capture_output=True, text=True
    )
    version = result.stdout.split("\n")[0].strip()
    return version if version else "0.0.0.0"


def check_update(arch_key, force=False, data_json_path=None):
    if force:
        return True
    last_version = get_last_version()
    if not last_version:  # 如果没有Git标签, 则总是下载
        return True
    
    # 使用指定的data.json路径或从配置获取
    if data_json_path is None:
        data_json_path = config.FETCH_OUTPUT_JSON_PATH
    
    if not os.path.exists(data_json_path):
        print(f"错误: 数据文件 {data_json_path} 不存在, 请先运行fetch.py")
        return False
    
    with open(data_json_path, "r") as f:
        data = json.load(f)
        if arch_key not in data:
            print(f"错误: 在数据文件中找不到架构 {arch_key}")
            return False
        latest_version = data[arch_key]["version"]
    
    github_env = os.getenv("GITHUB_ENV")
    if github_env and os.path.exists(github_env):
        with open(github_env, "a") as env_file:
            env_file.write(f"latest_version={latest_version}\n")
    
    return version_tuple(last_version) < version_tuple(latest_version)


def get_download_info(arch_key, data_json_path=None):
    # 使用指定的data.json路径或从配置获取
    if data_json_path is None:
        data_json_path = config.FETCH_OUTPUT_JSON_PATH
    
    if not os.path.exists(data_json_path):
        print(f"错误: 数据文件 {data_json_path} 不存在, 请先运行fetch.py")
        return None, None
    
    with open(data_json_path, "r") as f:
        data = json.load(f)
        if arch_key not in data:
            print(f"错误: 在数据文件中找不到架构 {arch_key}")
            return None, None
        version = data[arch_key]["version"]
        download_url = data[arch_key]["urls"][3]
    return version, download_url


def create_session():
    """创建一个带有重试机制的会话"""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def download_chunk(session, url, start, end, file, pbar, lock, max_retries=3):
    """下载文件的指定部分"""
    headers = {'Range': f'bytes={start}-{end}'}
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            with lock:
                file.seek(start)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        pbar.update(len(chunk))
            return True
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"\n下载块 {start}-{end} 失败: {str(e)}")
                return False
            time.sleep(1)  # 等待一秒后重试
    return False


def download_for_arch(arch_key, output_dir=None, force=False, num_threads=4, data_json_path=None):
    if check_update(arch_key, force, data_json_path):
        print(f"开始下载 {arch_key}...")
        version, url = get_download_info(arch_key, data_json_path)
        if version is None or url is None:
            return None
            
        arch_id = arch_key.split("_")[-1]
        filename = f"{arch_id}_{url.split('/')[-1]}"
        
        # 如果指定了输出目录, 则使用该目录
        if output_dir:
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
        else:
            filepath = filename

        if os.path.exists(filepath) and not force:
            print(f"文件 {filepath} 已存在, 跳过下载")
            return filepath
        
        # 创建会话
        session = create_session()
        
        try:
            # 获取文件大小
            response = session.head(url)
            file_size = int(response.headers.get('content-length', 0))
            
            # 创建进度条
            pbar = tqdm(total=file_size, unit='B', unit_scale=True, desc=filename)
            
            # 计算每个线程下载的块大小
            chunk_size = file_size // num_threads
            
            # 创建文件并分配空间
            with open(filepath, 'wb') as f:
                f.truncate(file_size)
            
            # 创建线程锁
            lock = threading.Lock()
            
            # 使用线程池下载
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = []
                for i in range(num_threads):
                    start = i * chunk_size
                    end = start + chunk_size - 1 if i < num_threads - 1 else file_size - 1
                    futures.append(
                        executor.submit(download_chunk, session, url, start, end, open(filepath, 'rb+'), pbar, lock)
                    )
                
                # 等待所有线程完成
                success = True
                for future in futures:
                    if not future.result():
                        success = False
                        break
                
                if not success:
                    print("\n下载失败, 请重试")
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return None
            
            pbar.close()
            print(f"下载完成 {arch_key}")
            return filepath
            
        except Exception as e:
            print(f"\n下载失败: {str(e)}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return None
            
    else:
        print(f"没有检测到 {arch_key} 的新版本, 跳过下载")
        return None


def main():
    # 从配置获取默认参数
    default_arch = config.DOWNLOAD_ARCH
    default_output_dir = config.DOWNLOAD_OUTPUT_DIR
    default_force = config.DOWNLOAD_FORCE
    default_threads = config.DOWNLOAD_THREADS
    default_data_json = config.FETCH_OUTPUT_JSON_PATH
    
    parser = argparse.ArgumentParser(
        description="下载不同架构的Chrome安装程序"
    )
    parser.add_argument(
        "--arch",
        nargs="+",
        default=default_arch,
        choices=["win_stable_x86", "win_stable_x64", "win_stable_arm64"],
        help=f"要下载的架构 (默认: {', '.join(default_arch if isinstance(default_arch, list) else [default_arch])})",
    )
    parser.add_argument(
        "--output-dir",
        default=default_output_dir,
        help=f"保存下载文件的目录 (默认: {default_output_dir})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=default_force,
        help="强制下载, 即使文件已存在",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=default_threads,
        help=f"下载线程数 (默认: {default_threads})",
    )
    parser.add_argument(
        "--data-json",
        default=default_data_json,
        help=f"data.json文件路径 (默认: {default_data_json})",
    )
    args = parser.parse_args()
    
    downloaded_files = []
    for arch in args.arch:
        result = download_for_arch(arch, args.output_dir, args.force, args.threads, args.data_json)
        if result:
            downloaded_files.append(result)
    
    if os.path.exists("__pycache__"):
        shutil.rmtree("__pycache__")
    
    return downloaded_files

if __name__ == "__main__":
    main()
