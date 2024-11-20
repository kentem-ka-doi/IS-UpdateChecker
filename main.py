# coding: UTF-8
import requests
import re
import json
import concurrent.futures
import os
import shutil
import git

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

# Dockerfileの更新
def update_dockerfile(dockerfile_path, current_tag, new_tag):
    with open(dockerfile_path, "r") as file:
        content = file.read()
    updated_content = content.replace(current_tag, new_tag)
    with open(dockerfile_path, "w") as file:
        file.write(updated_content)

# Gitリポジトリのクローン、コミット、プッシュ（DeployKeyを使用）
def clone_and_update_repo(repo_url, dockerfile_path, current_tag, new_tag, deploy_key_name, branch="main"):
    # 一時ディレクトリにリポジトリをクローン
    temp_dir = "temp_repo"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    # DeployKeyの読み込み
    deploy_key_path = f"/root/.ssh/{os.getenv(deploy_key_name)}"
    if not deploy_key_path:
        print(f"Deploy key path for {deploy_key_name} not found in environment variables.")
        return

    git_ssh_cmd = f'ssh -i {deploy_key_path}'

    with git.Git().custom_environment(GIT_SSH_COMMAND=git_ssh_cmd):
        repo = git.Repo.clone_from(repo_url, temp_dir, branch=branch)

    # Dockerfileのパスを取得
    dockerfile_full_path = os.path.join(temp_dir, dockerfile_path)

    # Dockerfileを更新
    update_dockerfile(dockerfile_full_path, current_tag, new_tag)

    # Gitで変更をコミットしてプッシュ
    with repo.git.custom_environment(GIT_SSH_COMMAND=git_ssh_cmd):
        repo.git.add(update=True)
        repo.index.commit(f"Update Dockerfile from {current_tag} to {new_tag}")
        origin = repo.remote(name='origin')
        origin.push(branch)

    # 一時ディレクトリを削除
    shutil.rmtree(temp_dir)

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
            print(f"Skipping {repo}: Expected a list of filter sets, got {type(filter_sets).__name__}\n\n")
            continue

        for filters in filter_sets:
            note = filters.get("note", "No note provided")
            current_tag = filters["current_tag"]
            include_patterns = filters["include"]
            exclude_patterns = filters["exclude"]
            auto_update = filters.get("auto_update", False)
            deploy_key_name = filters.get("deploy_key_name")
            branch = filters.get("branch")

            # DockerHubからすべてのタグを取得（並列処理、max_pages=3）
            all_tags = get_latest_tags_parallel(repo, max_pages=3, page_size=100)

            # フィルタリング
            filtered_tags = filter_tags(all_tags, include_patterns, exclude_patterns)

            # 最も新しいタグを取得
            latest_tag = get_latest_version_tag(filtered_tags, current_tag)

            # 更新が必要な場合、リポジトリをクローンしてDockerfileを更新しプッシュ
            if latest_tag:
                print(f"[{note}] Latest version available for {repo} (current: {current_tag}): {latest_tag}\n\n")
                
                if auto_update:
                    # リポジトリ情報を設定
                    repo_url = filters.get("repo_url")  # リポジトリのURL (GitHub/GitBucket)
                    dockerfile_path = filters.get("dockerfile_path", "Dockerfile")  # Dockerfileのパス

                    if repo_url and deploy_key_name:
                        clone_and_update_repo(repo_url, dockerfile_path, current_tag, latest_tag, deploy_key_name, branch)
                    else:
                        print(f"No repository URL or deploy key name provided for {repo}. Skipping update.\n\n")