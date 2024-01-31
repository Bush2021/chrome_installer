import json
import os

import requests


def version_tuple(v):
    return tuple(map(int, (v.split("."))))


def get_last_download():
    try:
        with open('last_download.txt', 'r') as file:
            last_version = file.read().strip()
            return last_version
    except FileNotFoundError:
        return ''


def check_update():
    last_version = get_last_download()
    with open('data.json', 'r') as f:
        data = json.load(f)
        current_version = data['win_stable_x64']['version']
    if version_tuple(last_version) < version_tuple(current_version):
        with open('last_download.txt', 'w') as file:
            file.write(current_version)
        return True
    else:
        return False


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
