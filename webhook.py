import base64
import os
import re

import aio_pika
import aiofiles
from fastapi import APIRouter, Request, HTTPException, status
import httpx
import json
import hmac
import hashlib
import logging

from sqlalchemy import select
from starlette.responses import JSONResponse

from app.models.database import async_get_db
from app.models.models import GitConfig

router = APIRouter()
logging.basicConfig(level=logging.INFO)

# 配置各平台的 Secret


async def task_to_queue(user_id, git_type, issue_url, file_path, request, ACCESS_TOKEN, task_type: str = "webhook_tasks"):
    message = aio_pika.Message(
        body=json.dumps({
            "user_id": user_id,
            "git_type": git_type,
            "issue_url": issue_url,
            "file_path": file_path,
            "access_token": ACCESS_TOKEN
        }).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json"
    )
    channel = request.app.state.channel
    await channel.default_exchange.publish(
        message,
        routing_key=task_type,
    )

async def async_write_text_to_file(user_id:str, file_id: str, content: str, encoding: str = "utf-8"):
    """
    异步将文本内容写入文件

    :param file_path: 要保存的文件路径
    :param content: 文本内容
    :param encoding: 编码格式，默认 utf-8
    """
    file_path = os.path.join("file",user_id)
    file_path = os.path.join(file_path, file_id)
    directory = os.path.dirname(file_path)
    os.makedirs(directory, exist_ok=True)  # exist_ok=True 避免目录不存在时出错
    async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
        await f.write(content)



def get_file_diff(diff):
    pattern = r'^\+(.*)$'  # 注意：需要使用多行模式
    added_lines = re.findall(pattern, diff, re.MULTILINE)
    return '\n'.join(added_lines)

async def get_file_diffs(diff_url, headers):
    async with httpx.AsyncClient() as client:
        response = await client.get(diff_url, headers=headers)
    file_diffs = []
    current_diff = []
    for line in response.text.splitlines():
        if line.startswith('diff --git') and current_diff != []:
            file_diffs.append('\n'.join(current_diff))
            current_diff = []
        else:
            current_diff.append(line)
    file_diffs.append('\n'.join(current_diff))
    return file_diffs

async def file_process(request, user_id, file, git_type, ACCESS_TOKEN,  diff_url, issue_url, head):
    async with httpx.AsyncClient() as client:
        response = await client.get(diff_url, headers=head)
    content_b64 = response.json()["content"]
    diff_content = base64.b64decode(content_b64).decode("utf-8")
    await async_write_text_to_file(user_id, file, diff_content)
    await task_to_queue(user_id, git_type, issue_url, file, request, ACCESS_TOKEN)


async def process_gitlab(request, user_id, ACCESS_TOKEN, project_id, mode, commits, ref):
    headers = {
        "PRIVATE-TOKEN": ACCESS_TOKEN,
    }
    git_type = "gitlab"
    if mode == "1":
        for commit in commits:
            path_parts = commit["url"].split("/")
            gitlab_url = f"{path_parts[0]}//{path_parts[2]}"
            sha = commit["id"]
            if mode == "1":
                diff_url = f"{gitlab_url}/api/v4/projects/{project_id}/repository/commits/{sha}/diff"
                async with httpx.AsyncClient() as client:
                    response = await client.get(diff_url, headers=headers)
                    for file_diff in response.json():
                        diff = file_diff["diff"]
                        new_path = file_diff['new_path']
                        diff_content = get_file_diff(diff)
                        await async_write_text_to_file(user_id, new_path, diff_content)
                        comments_url = f"{gitlab_url}/api/v4/projects/{project_id}/repository/commits/{sha}/comments"
                        await task_to_queue(user_id, git_type, comments_url, new_path, request, ACCESS_TOKEN)
            elif mode == "0":
                modified_files = commit.get("modified") or []
                added_files = commit.get("added") or []
                all_files = modified_files + added_files
                if not all_files:
                    continue
                for file in all_files:
                    diff_url = f"{gitlab_url}/api/v4/projects/{project_id}/repository/files/{file}/raw?ref={ref}"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(diff_url, headers=headers)
                    diff_content = response.text
                    await async_write_text_to_file(user_id, file, diff_content)
                    commit_url = f"{gitlab_url}/api/v4/projects/{project_id}/repository/commits/{commit["id"]}/comments"
                    await task_to_queue(user_id, git_type, commit_url, file, request, ACCESS_TOKEN)

async def process_gitee(request, user_id, ACCESS_TOKEN, mode, commits, ref):
    git_type = "gitee"
    headers = {
                "Authorization": f"token {ACCESS_TOKEN}",
                "Accept": "application/vnd.gitee.v1.diff"
            }
    for commit in commits:
        url = commit["url"].replace("/commit/", "/commits/")
        path_parts = url.split("/", 3)
        gitlab_url = f"{path_parts[0]}//{path_parts[2]}"
        if mode == "1":
            diff_url = f"{gitlab_url}/api/v5/repos/" + path_parts[3]
            sha = commit["id"]
            file_diffs = await get_file_diffs(diff_url, headers)
            for file_diff in file_diffs:
                diff_content = get_file_diff(file_diff)
                await async_write_text_to_file(user_id, sha, diff_content)
                commit_url = f"{path_parts[0]}//{path_parts[2]}/api/v5/repos/{path_parts[3]}/comments"
                await task_to_queue(user_id, git_type, commit_url, sha, request, ACCESS_TOKEN)
        elif mode == "0":
            modified_files = commit.get("modified") or []
            added_files = commit.get("added") or []
            all_files = modified_files + added_files
            if not all_files:
                continue
            for file in all_files:
                path_parts = url.split("/")
                diff_url = f"{gitlab_url}/api/v5/repos/{path_parts[3]}/{path_parts[4]}/contents/{file}?ref={ref}"
                commit_url = f"{path_parts[0]}//{path_parts[2]}/api/v5/repos/{path_parts[3]}/{path_parts[4]}/commits/{commit["id"]}/comments"
                await file_process(request, user_id, file, git_type, ACCESS_TOKEN, diff_url, commit_url, headers)

async def process_gitea(request, url, user_id, ACCESS_TOKEN, mode, commits, ref):
    git_type = "gitea"
    head = {
        "Authorization": f"token {ACCESS_TOKEN}",
        "Accept": "application/vnd.gitee.v1.diff"
    }
    for commit in commits:
        sha = commit["id"]
        if mode == "1":
            diff_url = url + f"/git/commits/{sha}.diff"
            file_diffs = await get_file_diffs(diff_url, head)
            for file_diff in file_diffs:
                diff_content = get_file_diff(file_diff)
                await async_write_text_to_file(user_id, sha, diff_content)
                issue_url = f"{url}/issues"
                await task_to_queue(user_id, git_type, issue_url, sha, request, ACCESS_TOKEN)
        elif mode == "0":
            modified_files = commit.get("modified") or []
            added_files = commit.get("added") or []
            all_files = modified_files + added_files
            if not all_files:
                continue
            for file in all_files:
                diff_url = f"{url}/contents/{file}?ref={ref}"
                issue_url = f"{url}/issues"
                await file_process(request, user_id, file, git_type, ACCESS_TOKEN, diff_url, issue_url, head)

async def process_gitub(request, commits_url, contents_url, user_id, ACCESS_TOKEN, mode, commits, ref):
    git_type = "github"
    headers = {
            "Authorization": f"token {ACCESS_TOKEN}",
            "Accept": "application/vnd.github.diff"
        }
    for commit in commits:
        sha = commit["id"]
        result_url = commits_url.replace("{/sha}", f"/{sha}")
        if mode == "1":
            file_diffs = await get_file_diffs(result_url, headers)
            for file_diff in file_diffs:
                diff_content = get_file_diff(file_diff)
                await async_write_text_to_file(user_id, sha, diff_content)
                issue_url = f"{result_url}/comments"
                await task_to_queue(user_id, git_type, issue_url, sha, request, ACCESS_TOKEN)

        elif mode == "0":
            modified_files = commit.get("modified") or []
            added_files = commit.get("added") or []
            all_files = modified_files + added_files
            for file in all_files:
                contents_url = contents_url.replace("{+path}", f"/{file}") + f"?ref={ref}"
                async with httpx.AsyncClient() as client:
                    response = await client.get(contents_url, headers=headers)
                content_b64 = response.json()["content"]
                diff_content = base64.b64decode(content_b64).decode("utf-8")
                await async_write_text_to_file(user_id, file, diff_content)
                issue_url = f"{result_url}/comments"
                await task_to_queue(user_id, git_type, issue_url, file, request, ACCESS_TOKEN)


@router.post("/{id}")
async def webhook(request: Request, id: str):
    try:
        # 尝试解析 JSON 数据（如果请求体非 JSON 会抛出异常）
        headers = dict(request.headers)
        body = await request.json()
        body_bytes = await request.body()
    except Exception as e:
        logging.warning(f"webhook error: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid JSON in request body"}
        )
    async with async_get_db() as db:
        result = await db.execute(select(GitConfig).where(GitConfig.user_id == id))
        gitconfig = result.scalars().first()
        if not gitconfig:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "Git config not found"}
            )
        password = gitconfig.password_hash
        mode = "1" if gitconfig.mode else "0"
        ACCESS_TOKEN = gitconfig.access_token
        # 正常逻辑继续处理...
    try:
        if "x-gitlab-event" in headers:
            if headers.get("x-gitlab-token") != password:
                raise HTTPException(status_code=403, detail="Invalid GitLab token")
            event_type = headers["x-gitlab-event"]
            project_id = body["project_id"]
            commits = body.get("commits", [])
            ref = body.get("ref", "")
            if event_type == "Push Hook":
                await process_gitlab(request, id, ACCESS_TOKEN, project_id, mode, commits, ref)
            else:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "目前只支持push事件"}
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"detail": "GitLab push processed"}
            )

        elif "x-gitee-event" in headers:
            if headers.get("x-gitee-token") != password:
                raise HTTPException(status_code=403, detail="Invalid Gitee token")
            event_type = headers["x-gitee-event"]
            if event_type == "Push Hook":
                commits = body.get("commits", [])
                ref = body.get("ref", "")
                await process_gitee(request, id, ACCESS_TOKEN, mode, commits, ref)
            else:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "目前只支持push事件"}
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"detail": "Gitee push processed"}
            )

        #
        elif "x-gitea-event" in headers:
            signature = headers.get("x-gitea-signature", "")
            hmac_obj = hmac.new(password.encode(), msg=body_bytes, digestmod=hashlib.sha256).hexdigest()
            if hmac_obj != signature:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "error Gitea password"}
                )
            event_type = headers["x-gitea-event"]
            if event_type == "push":
                url = body["repository"]["url"]
                commits = body.get("commits", [])
                ref = body.get("ref", "")
                await process_gitea(request, url, id, ACCESS_TOKEN, mode, commits, ref)

            else:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "目前只支持push事件"}
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"detail": "GitLea push processed"}
            )
        elif "x-github-event" in headers:
            signature = headers.get("x-hub-signature-256", "")
            hmac_obj = hmac.new("123".encode(), msg=body_bytes, digestmod=hashlib.sha256).hexdigest()
            if signature[7:] != hmac_obj:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid GitLub token"}
                )
            event_type = headers["x-github-event"]
            if event_type == "push":
                commits_url = body["repository"]["commits_url"]
                contents_url = body["repository"]["contents_url"]
                commits = body.get("commits", [])
                ref = body.get("ref", "")
                await process_gitub(request, commits_url, contents_url, id, ACCESS_TOKEN, mode, commits, ref)

            else:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "目前只支持push事件"}
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"detail": "GitLub push processed"}
            )

        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Unknown git event type"}
            )
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )

