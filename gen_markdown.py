import os
import json
import config

suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]

def humansize(nbytes):
    """将字节数转换为人类可读的大小字符串"""
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.0
        i += 1
    f = ("%.2f" % nbytes).rstrip("0").rstrip(".")
    return f"{f} {suffixes[i]}"

def generate_readme(results, file_path=None):
    """生成README.md文件
    
    Args:
        results (dict): 包含Chrome版本信息的字典
        file_path (str, optional): README.md的保存路径。如果为None，则使用配置中的设置
    """
    if file_path is None:
        file_path = config.GEN_MARKDOWN_OUTPUT_PATH
    
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    index_url = "https://github.com/Bush2021/chrome_installer?tab=readme-ov-file#"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Google Chrome 离线安装包（请使用 7-Zip 解压）\n")
        f.write(
            "稳定版存档: <https://github.com/Bush2021/chrome_installer/releases>\n\n"
        )
        f.write("## 目录\n")
        for name in results.keys():
            title = name.replace("_", " ")
            link = index_url + title.replace(" ", "-")
            f.write(f"* [{title}]({link})\n")
        f.write("\n")
        for name, version in results.items():
            f.write(f'## {name.replace("_", " ")}\n')
            f.write(f'**最新版本**: {version["version"]}  \n')
            f.write(f'**文件大小**: {humansize(version["size"])}  \n')
            f.write(f'**校验值（Sha256）**: {version["sha256"]}  \n')
            for url in version["urls"]:
                if url.startswith("https://dl."):
                    f.write(f"**下载链接**: [{url}]({url})  \n")
            f.write("\n")
    
    print(f"已生成README.md到 {file_path}")

if __name__ == "__main__":
    """
    单独运行此脚本可以从data.json生成README.md
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="生成Chrome版本信息的README.md")
    parser.add_argument(
        "--json-file", 
        default=config.FETCH_OUTPUT_JSON_PATH,
        help=f"JSON输入文件路径 (默认: {config.FETCH_OUTPUT_JSON_PATH})"
    )
    parser.add_argument(
        "--output", 
        default=config.GEN_MARKDOWN_OUTPUT_PATH,
        help=f"README.md输出路径 (默认: {config.GEN_MARKDOWN_OUTPUT_PATH})"
    )
    
    args = parser.parse_args()
    
    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        generate_readme(data, args.output)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {args.json_file}")
    except json.JSONDecodeError:
        print(f"错误: {args.json_file} 不是有效的JSON文件") 