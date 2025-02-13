import json
import os
import subprocess
import requests


def version_tuple(v):
    return tuple(map(int, (v.split("."))))


def get_last_version():
    result = subprocess.run(
        ["git", "tag", "--sort=-creatordate"], capture_output=True, text=True
    )
    version = result.stdout.split("\n")[0].strip()
    return version if version else "0.0.0.0"


def check_update():
    last_version = get_last_version()
    with open('data.json', 'r') as f:
        data = json.load(f)
        latest_version = data['win_stable_x64']['version']
    with open(os.getenv('GITHUB_ENV'), 'a') as env_file:
        env_file.write(f'latest_version={latest_version}\n')
    return version_tuple(last_version) < version_tuple(latest_version)


def get_download_url():
    with open('data.json', 'r') as f:
        data = json.load(f)
        download_url = data['win_stable_x64']['urls'][3]
    return download_url


def download():
    if check_update():
        print('New version detected, start downloading...')
        url = get_download_url()
        filename = url.split('/')[-1]
        if os.path.exists(filename):
            print('The file already exists, skip downloading')
            return
        r = requests.get(url, stream=True)
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print('Download complete')
        if os.path.exists('__pycache__'):
            os.system('rmdir /s /q __pycache__')
    else:
        print('No new version detected, skip downloading')
        return


download()
