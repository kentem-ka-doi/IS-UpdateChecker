# coding: UTF-8
import requests
import re
import json
import concurrent.futures

# ページを非同期で取得
def fetch_page(url, timeout=10):
    """指定されたURLのページを取得"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            # ページが存在しない場合は終了信号としてNoneを返す
            # print(f"Page not found: {url} (404)")
            return None
        else:
            print(f"Failed to fetch page {url}: {response.status_code}")
            return None
    except requests.Timeout:
        print(f"Request to {url} timed out.")
        return None

# 並列リクエストでタグを取得
def get_latest_tags_parallel(repo, max_pages=3, page_size=100, timeout=10):
    """DockerHubから並列リクエストでタグを取得"""
    if "/" in repo:
        base_url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size={page_size}"
    else:
        base_url = f"https://hub.docker.com/v2/repositories/library/{repo}/tags?page_size={page_size}"
    
    urls = [f"{base_url}&page={i+1}" for i in range(max_pages)]
    tags = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_url = {executor.submit(fetch_page, url, timeout): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            data = future.result()
            if data:
                tags.extend(tag['name'] for tag in data.get('results', []))

    return tags

# タグをフィルタリング
def filter_tags(tags, include_patterns, exclude_patterns):
    filtered_tags = []
    for tag in tags:
        if any(re.match(pattern, tag) for pattern in include_patterns):
            if not any(re.match(pattern, tag) for pattern in exclude_patterns):
                filtered_tags.append(tag)
    return filtered_tags

# 現在のタグと新しいタグを比較
def is_newer_version(current_tag, latest_tag):
    # タグをバージョン部分とオプション部分に分ける
    def split_tag(tag):
        if "-" in tag:
            version, option = tag.split("-", 1)
        else:
            version, option = tag, ""
        return version.split("."), option.split("-")

    current_version, current_options = split_tag(current_tag)
    latest_version, latest_options = split_tag(latest_tag)

    # バージョン部分を比較
    for cur, lat in zip(current_version, latest_version):
        if cur.isdigit() and lat.isdigit():
            cur, lat = int(cur), int(lat)
        if lat > cur:
            return True
        elif lat < cur:
            return False

    # オプション部分の比較
    return latest_options > current_options

# 最も新しいタグを取得
def get_latest_version_tag(tags, current_tag):
    latest_tag = None
    for tag in tags:
        if is_newer_version(current_tag, tag):
            if latest_tag is None or is_newer_version(latest_tag, tag):
                latest_tag = tag
    return latest_tag

# 設定ファイルを読み込む
def load_config(config_file):
    with open(config_file, "r") as f:
        return json.load(f)

# メイン処理
if __name__ == "__main__":
    config = load_config("config.json")
    repositories = config["repositories"]

    for repo, filter_sets in repositories.items():
        if not isinstance(filter_sets, list):
            print(f"Skipping {repo}: Expected a list of filter sets, got {type(filter_sets).__name__}\n")
            continue

        for filters in filter_sets:
            note = filters.get("note", "No note provided")
            current_tag = filters["current_tag"]
            include_patterns = filters["include"]
            exclude_patterns = filters["exclude"]

            # DockerHubからすべてのタグを取得（並列処理、max_pages=3）
            all_tags = get_latest_tags_parallel(repo, max_pages=3, page_size=100)

            # フィルタリング
            filtered_tags = filter_tags(all_tags, include_patterns, exclude_patterns)

            # 最も新しいタグを取得
            latest_tag = get_latest_version_tag(filtered_tags, current_tag)

            # 結果を出力
            if latest_tag:
                print(f"[{note}] Latest version available for {repo} (current: {current_tag}): {latest_tag}\n")
            # else:
                # print(f"[{note}] You are using the latest version for {repo} (current: {current_tag})")
