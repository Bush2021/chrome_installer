import os
import platform
import subprocess
import argparse
import shutil
import sys
import glob

import config

def get_arch_from_path(path):
    """从路径中获取架构信息"""
    if "x64_" in path:
        return "x64"
    elif "x86_" in path:
        return "x86"
    elif "arm64_" in path:
        return "arm64"
    return None

def copy_plus_files(chrome_dir, arch):
    """复制plus目录中的文件到chrome目录
    
    Args:
        chrome_dir (str): Chrome目录，第二次解压的目录
        arch (str): 架构，如x64、x86、arm64
    """
    plus_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", arch)
    if not os.path.exists(plus_dir):
        print(f"错误: plus目录 {plus_dir} 不存在")
        return False
    
    # 寻找chrome.exe文件的实际位置
    chrome_exe_path = None
    for root, dirs, files in os.walk(chrome_dir):
        if "chrome.exe" in files:
            chrome_exe_path = root
            break
    
    if not chrome_exe_path:
        print(f"错误: 在 {chrome_dir} 及其子目录中未找到chrome.exe文件")
        return False
    
    print(f"找到chrome.exe位置: {chrome_exe_path}")
    
    try:
        # 复制plus目录中的所有文件到chrome.exe所在目录
        for item in os.listdir(plus_dir):
            src = os.path.join(plus_dir, item)
            dst = os.path.join(chrome_exe_path, item)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                print(f"已复制文件: {item} 到 {chrome_exe_path}")
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"已复制目录: {item} 到 {chrome_exe_path}")
        return True
    except Exception as e:
        print(f"复制文件时出错: {e}")
        return False

def clean_temp_files():
    """清理临时文件"""
    if os.path.exists("__pycache__"):
        shutil.rmtree("__pycache__")
    
    for root, dirs, _ in os.walk("."):
        for dir_name in dirs:
            if dir_name == "__pycache__":
                shutil.rmtree(os.path.join(root, dir_name))

def version_tuple(v):
    """将版本字符串转换为元组, 便于比较"""
    return tuple(map(int, (v.split(".")))) 

def get_7zip_path():
    """获取7-Zip可执行文件路径"""
    # 检查内置的7-Zip
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
    if not os.path.exists(bin_dir):
        os.makedirs(bin_dir)
        print(f"创建bin目录: {bin_dir}")
        print("请将7-Zip可执行文件放入bin目录")
        return None

    system = platform.system().lower()
    if system == "windows":
        seven_zip = os.path.join(bin_dir, "7zr.exe")
    else:  # Linux 或其他 Unix-like 系统
        seven_zip = os.path.join(bin_dir, "7zzs")
        # 确保Linux版本有执行权限
        if os.path.exists(seven_zip):
            os.chmod(seven_zip, 0o755)

    if os.path.exists(seven_zip):
        return seven_zip
    return None

def check_7zip():
    """检查7-Zip是否可用"""
    seven_zip = get_7zip_path()
    if seven_zip:
        try:
            subprocess.run([seven_zip], capture_output=True, text=True)
            return True
        except Exception:
            pass
    
    # 如果内置版本不可用, 尝试系统安装的版本
    try:
        subprocess.run(["7z"], capture_output=True, text=True)
        return True
    except FileNotFoundError:
        return False

def extract_chrome(installer_path, extract_dir=None, force=False):
    """
    Extract Chrome installer to a directory.
    
    Args:
        installer_path (str): Path to the Chrome installer
        extract_dir (str, optional): Directory to extract to. If None, uses the directory of the installer.
        force (bool): Whether to force extraction even if the directory already exists
    
    Returns:
        str or False: 成功时返回解压后的chrome目录路径, 失败时返回False
    """
    if not os.path.exists(installer_path):
        print(f"错误: 安装文件 {installer_path} 不存在")
        return False
    
    # 获取安装程序所在目录
    installer_dir = os.path.dirname(os.path.abspath(installer_path))
    
    # 如果未指定解压目录, 使用安装程序所在目录
    if extract_dir is None:
        extract_dir = installer_dir
    
    # 创建解压目录
    extract_name = os.path.splitext(os.path.basename(installer_path))[0]
    full_extract_dir = os.path.join(extract_dir, extract_name)
    
    # 如果force为True, 则删除已存在的目录
    if os.path.exists(full_extract_dir):
        if force:
            print(f"强制模式: 删除已存在的目录 {full_extract_dir}")
            shutil.rmtree(full_extract_dir)
        else:
            print(f"解压目录 {full_extract_dir} 已存在, 跳过解压")
            chrome_dir = os.path.join(full_extract_dir, "chrome")
            if os.path.exists(chrome_dir):
                return chrome_dir
            return False

    seven_zip = get_7zip_path()
    if not seven_zip and not check_7zip():
        print("错误: 未找到7-Zip")
        print("请将7-Zip可执行文件放入bin目录, 或安装系统版本的7-Zip")
        print("Windows: 将7zr.exe放入bin目录")
        print("Linux: 将7zzs放入bin目录")
        return False
    
    print(f"正在解压 {installer_path}...")
    try:
        # 确保解压目录存在
        os.makedirs(extract_dir, exist_ok=True)
        
        # 第一次解压
        cmd = [seven_zip if seven_zip else "7z", "x", installer_path, f"-o{full_extract_dir}"]
        subprocess.run(cmd, check=True)
        
        # 查找并解压chrome.7z
        chrome_7z = os.path.join(full_extract_dir, "chrome.7z")
        if os.path.exists(chrome_7z):
            chrome_dir = os.path.join(full_extract_dir, "chrome")
            cmd = [seven_zip if seven_zip else "7z", "x", chrome_7z, f"-o{chrome_dir}"]
            subprocess.run(cmd, check=True)
            print(f"Chrome已解压到: {chrome_dir}")
            return chrome_dir
        else:
            print("错误: 未找到chrome.7z文件")
            return False
    except subprocess.CalledProcessError as e:
        print(f"解压失败: {e}")
        return False

def create_archive(source_dir, output_path=None):
    """
    创建7z压缩包
    
    Args:
        source_dir (str): 源目录
        output_path (str, optional): 输出文件路径
    
    Returns:
        bool: 成功返回True, 失败返回False
    """
    if not os.path.exists(source_dir):
        print(f"错误: 目录 {source_dir} 不存在")
        return False

    seven_zip = get_7zip_path()
    if not seven_zip:
        print("错误: 未找到内置的7-Zip")
        return False

    # 如果未指定输出路径, 使用源目录的父目录
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(source_dir),
            f"{os.path.basename(source_dir)}_plus.7z"
        )

    try:
        # 确保目标文件不存在（虽然在process_chrome_plus中已处理，这里为了安全再次检查）
        if os.path.exists(output_path):
            os.remove(output_path)
            
        # 创建全新的7z包（使用a命令而非u命令，确保是新建而非更新）
        cmd = [seven_zip, "a", "-mx=9", output_path, f"{source_dir}/*"]
        subprocess.run(cmd, check=True)
        print(f"打包完成: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        return False
    except Exception as e:
        print(f"打包过程中出错: {e}")
        return False

def process_chrome_plus(installer_path, output_dir=None, force=False, repack=True):
    """
    处理Chrome安装包, 解压, 添加Plus功能, 重新打包
    
    Args:
        installer_path (str): Chrome安装包路径
        output_dir (str, optional): 输出目录, 用于存放生成的plus包
        force (bool): 是否强制处理, 即使目录已存在
        repack (bool): 是否重新打包
    
    Returns:
        bool: 成功返回True, 失败返回False
    """
    # 获取架构信息
    arch = get_arch_from_path(installer_path)
    if not arch:
        print(f"错误: 无法从路径 {installer_path} 确定架构信息")
        return False
    
    # 构建输出文件路径
    extract_name = os.path.splitext(os.path.basename(installer_path))[0]
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(installer_path))
    
    plus_7z_name = f"{extract_name}_plus.7z"
    plus_7z_path = os.path.join(output_dir, plus_7z_name)
    
    # 检查目标plus包是否已存在
    if os.path.exists(plus_7z_path):
        if force:
            print(f"强制模式: 删除已存在的目标压缩包 {plus_7z_path}")
            try:
                os.remove(plus_7z_path)
            except Exception as e:
                print(f"删除目标压缩包失败: {e}")
                return False
        else:
            print(f"Plus包 {plus_7z_path} 已存在, 跳过处理")
            return True
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 解压目录可以放在临时位置
    temp_extract_dir = os.path.join(output_dir, "temp_extract")
    
    # 解压Chrome
    chrome_dir = extract_chrome(installer_path, temp_extract_dir, force=True)  # 总是强制解压到临时目录
    if not chrome_dir:
        return False
    
    # 复制Plus文件到chrome.exe所在目录
    if not copy_plus_files(chrome_dir, arch):
        return False
    
    # 重新打包
    if repack:
        # 只打包chrome目录（第二次解压的结果, 包含chrome.exe的目录）
        if not create_archive(chrome_dir, plus_7z_path):
            return False
    
    # 如果成功, 清理临时目录
    if os.path.exists(temp_extract_dir):
        shutil.rmtree(temp_extract_dir)
    
    return True

def find_installer_files(download_dir=None):
    """
    在下载目录中查找所有Chrome安装包
    
    Args:
        download_dir (str, optional): 下载目录
        
    Returns:
        list: 找到的安装包路径列表
    """
    if download_dir is None:
        download_dir = config.DOWNLOAD_OUTPUT_DIR
    
    if not os.path.exists(download_dir):
        print(f"错误: 下载目录 {download_dir} 不存在")
        return []
    
    # 查找所有可能的Chrome安装包
    patterns = [
        os.path.join(download_dir, "x64_*.exe"),
        os.path.join(download_dir, "x86_*.exe"),
        os.path.join(download_dir, "arm64_*.exe")
    ]
    
    installer_files = []
    for pattern in patterns:
        installer_files.extend(glob.glob(pattern))
    
    return installer_files

def process_all_installers(download_dir=None, output_dir=None, force=False, repack=True):
    """
    处理下载目录中的所有Chrome安装包
    
    Args:
        download_dir (str, optional): 下载目录
        output_dir (str, optional): 输出目录
        force (bool): 是否强制处理
        repack (bool): 是否重新打包
        
    Returns:
        list: 处理成功的plus包路径列表
    """
    installer_files = find_installer_files(download_dir)
    if not installer_files:
        print("未找到任何Chrome安装包")
        return []
    
    processed_files = []
    for installer in installer_files:
        # 获取基本文件名（不含路径）
        basename = os.path.basename(installer)
        print(f"处理安装包: {basename}")
        
        # 处理单个安装包
        if process_chrome_plus(installer, output_dir, force, repack):
            # 计算生成的plus包路径
            extract_name = os.path.splitext(os.path.basename(installer))[0]
            plus_7z_name = f"{extract_name}_plus.7z"
            plus_7z_path = os.path.join(output_dir or os.path.dirname(installer), plus_7z_name)
            processed_files.append(plus_7z_path)
    
    return processed_files

def main():
    # 从配置获取默认参数
    default_output_dir = config.GEN_PLUS_OUTPUT_DIR
    default_force = config.GEN_PLUS_FORCE
    default_repack = config.GEN_PLUS_REPACK
    default_download_dir = config.DOWNLOAD_OUTPUT_DIR
    
    parser = argparse.ArgumentParser(
        description="生成Chrome Plus版本"
    )
    parser.add_argument(
        "installer_path",
        nargs="?",
        help="Chrome安装包路径 (如不指定, 将处理下载目录中的所有安装包)",
    )
    parser.add_argument(
        "--output-dir",
        default=default_output_dir,
        help=f"输出目录, 用于存放生成的plus包 (默认: {default_output_dir})",
    )
    parser.add_argument(
        "--download-dir",
        default=default_download_dir,
        help=f"下载目录, 当不指定installer_path时使用 (默认: {default_download_dir})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=default_force,
        help="强制处理, 即使plus包已存在",
    )
    parser.add_argument(
        "--no-repack",
        action="store_true",
        default=not default_repack,
        help="不重新打包",
    )
    args = parser.parse_args()
    
    # 如果指定了installer_path, 则处理单个安装包
    if args.installer_path:
        result = process_chrome_plus(args.installer_path, args.output_dir, args.force, not args.no_repack)
    else:
        # 否则处理下载目录中的所有安装包
        processed_files = process_all_installers(args.download_dir, args.output_dir, args.force, not args.no_repack)
        result = len(processed_files) > 0
        if result:
            print(f"成功处理 {len(processed_files)} 个安装包:")
            for f in processed_files:
                print(f"  - {f}")
    
    clean_temp_files()
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main()) 