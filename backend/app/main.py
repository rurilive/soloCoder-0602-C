import os
import re
from flask import Flask, request, jsonify, send_file, send_from_directory, Response, g
from flask_cors import CORS
from flask_socketio import SocketIO, join_room
from pathlib import Path

from .config import Config
from .utils import (
    ensure_dirs,
    list_directory,
    create_folder,
    delete_item,
    rename_item,
    move_item,
    copy_item,
    save_upload,
    get_abs_path,
    create_share,
    get_share,
    get_file_info,
    search_files,
    soft_delete_item,
    list_trash,
    restore_trash_item,
    permanently_delete_trash_item,
    empty_trash,
    get_user_storage_usage,
    check_storage_quota,
    clean_all_expired_trash,
    get_dir_size,
    init_chunk_upload,
    save_chunk,
    complete_chunk_upload,
    get_upload_meta,
)
from .auth import (
    create_user,
    authenticate_user,
    generate_token,
    token_required,
    decode_token,
)
from .audit import (
    start_audit_worker,
    log_audit,
    read_audit_logs,
    ensure_audit_dir,
)

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="eventlet",
    logger=False,
    engineio_logger=False,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, resources={r"/socket.io/*": {"origins": "*"}})
    socketio.init_app(app)
    ensure_dirs()
    ensure_audit_dir()
    start_audit_worker()
    try:
        clean_all_expired_trash()
    except Exception:
        pass

    def emit_file_event(username, event_type, data=None):
        if socketio:
            socketio.emit(
                "file_event",
                {"type": event_type, "data": data or {}},
                to=f"user:{username}",
            )

    @socketio.on("connect")
    def on_connect():
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        if not token:
            token = request.args.get("token")
        if not token:
            return False
        try:
            data = decode_token(token)
            username = data["username"]
            join_room(f"user:{username}")
        except ValueError:
            return False

    @app.route("/api/auth/register", methods=["POST"])
    def api_register():
        data = request.get_json()
        username = data.get("username", "")
        password = data.get("password", "")
        if not username or not password:
            return jsonify({"success": False, "error": "Username and password are required"}), 400
        if len(username) < 3 or len(username) > 32:
            return jsonify({"success": False, "error": "Username must be between 3 and 32 characters"}), 400
        if len(password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400
        try:
            user = create_user(username, password)
            token = generate_token(user["id"], user["username"])
            return jsonify({"success": True, "user": user, "token": token})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        data = request.get_json()
        username = data.get("username", "")
        password = data.get("password", "")
        if not username or not password:
            return jsonify({"success": False, "error": "Username and password are required"}), 400
        try:
            user = authenticate_user(username, password)
            token = generate_token(user["id"], user["username"])
            return jsonify({"success": True, "user": user, "token": token})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 401

    @app.route("/api/files", methods=["GET"])
    @token_required
    def api_list_files():
        username = g.user["username"]
        path = request.args.get("path", "")
        try:
            items = list_directory(path, username)
            return jsonify({"success": True, "items": items, "path": path})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/search", methods=["GET"])
    @token_required
    def api_search_files():
        username = g.user["username"]
        query = request.args.get("q", "")
        extension = request.args.get("ext", None)
        path = request.args.get("path", "")
        if not query:
            return jsonify({"success": False, "error": "Search query is required"}), 400
        try:
            items = search_files(query, extension, path, username)
            return jsonify({"success": True, "items": items, "query": query, "extension": extension})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/upload", methods=["POST"])
    @token_required
    def api_upload():
        username = g.user["username"]
        path = request.form.get("path", "")
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No filename"}), 400
        try:
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            try:
                check_storage_quota(username, file_size)
            except ValueError as e:
                usage = get_user_storage_usage(username)
                return jsonify({
                    "success": False,
                    "error": str(e),
                    "usage": usage
                }), 403
            info = save_upload(path, file, username)
            log_audit(username, "upload", info["path"])
            emit_file_event(username, "upload", {"item": info, "path": path})
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/upload/init", methods=["POST"])
    @token_required
    def api_upload_init():
        username = g.user["username"]
        data = request.get_json()
        filename = data.get("filename", "")
        total_size = data.get("totalSize", 0)
        total_chunks = data.get("totalChunks", 0)
        file_md5 = data.get("fileMD5", "")
        if not filename or total_size <= 0 or total_chunks <= 0 or not file_md5:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            check_storage_quota(username, total_size)
        except ValueError as e:
            usage = get_user_storage_usage(username)
            return jsonify({
                "success": False,
                "error": str(e),
                "usage": usage
            }), 403
        try:
            meta = init_chunk_upload(filename, total_size, total_chunks, file_md5, username)
            return jsonify({"success": True, "uploadId": meta["uploadId"]})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/upload/chunk", methods=["POST"])
    @token_required
    def api_upload_chunk():
        username = g.user["username"]
        upload_id = request.form.get("uploadId", "")
        chunk_index = request.form.get("chunkIndex", "")
        chunk_md5 = request.form.get("chunkMD5", "")
        if not upload_id or chunk_index == "" or not chunk_md5:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if "chunk" not in request.files:
            return jsonify({"success": False, "error": "No chunk file provided"}), 400
        try:
            chunk_index = int(chunk_index)
            meta = get_upload_meta(upload_id)
            if not meta:
                return jsonify({"success": False, "error": "Upload session not found"}), 404
            if meta["username"] != username:
                return jsonify({"success": False, "error": "Permission denied"}), 403
            result = save_chunk(upload_id, chunk_index, request.files["chunk"], chunk_md5)
            return jsonify({"success": True, **result})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/upload/complete", methods=["POST"])
    @token_required
    def api_upload_complete():
        username = g.user["username"]
        data = request.get_json()
        upload_id = data.get("uploadId", "")
        path = data.get("path", "")
        if not upload_id:
            return jsonify({"success": False, "error": "Missing uploadId"}), 400
        try:
            meta = get_upload_meta(upload_id)
            if not meta:
                return jsonify({"success": False, "error": "Upload session not found"}), 404
            if meta["username"] != username:
                return jsonify({"success": False, "error": "Permission denied"}), 403
            info = complete_chunk_upload(upload_id, path, username)
            log_audit(username, "upload", info["path"])
            emit_file_event(username, "upload", {"item": info, "path": path})
            return jsonify({"success": True, "item": info})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/folder", methods=["POST"])
    @token_required
    def api_create_folder():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        name = data.get("name", "")
        if not name:
            return jsonify({"success": False, "error": "Name required"}), 400
        try:
            info = create_folder(path, name, username)
            log_audit(username, "create_folder", info["path"])
            emit_file_event(username, "create_folder", {"item": info, "path": path})
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/delete", methods=["POST"])
    @token_required
    def api_delete():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        try:
            soft_delete_item(path, username)
            log_audit(username, "delete", path)
            emit_file_event(username, "delete", {"path": path})
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/rename", methods=["POST"])
    @token_required
    def api_rename():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        newName = data.get("newName", "")
        if not newName:
            return jsonify({"success": False, "error": "New name required"}), 400
        try:
            info = rename_item(path, newName, username)
            log_audit(username, "rename", path, {"newPath": info["path"], "newName": newName})
            emit_file_event(username, "rename", {"item": info, "oldPath": path})
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/move", methods=["POST"])
    @token_required
    def api_move():
        username = g.user["username"]
        data = request.get_json()
        src = data.get("src", "")
        dst = data.get("dst", "")
        try:
            info = move_item(src, dst, username)
            log_audit(username, "move", src, {"dst": dst, "newPath": info["path"]})
            emit_file_event(username, "move", {"item": info, "src": src, "dst": dst})
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/copy", methods=["POST"])
    @token_required
    def api_copy():
        username = g.user["username"]
        data = request.get_json()
        src = data.get("src", "")
        dst = data.get("dst", "")
        try:
            src_path = get_abs_path(src, username)
            if not src_path.exists():
                raise ValueError("Source not found")
            copy_size = get_dir_size(src_path)
            try:
                check_storage_quota(username, copy_size)
            except ValueError as e:
                usage = get_user_storage_usage(username)
                return jsonify({
                    "success": False,
                    "error": str(e),
                    "usage": usage
                }), 403
            info = copy_item(src, dst, username)
            log_audit(username, "copy", src, {"dst": dst, "newPath": info["path"]})
            emit_file_event(username, "copy", {"item": info, "src": src, "dst": dst})
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/preview", methods=["GET"])
    @token_required
    def api_preview():
        username = g.user["username"]
        path = request.args.get("path", "")
        try:
            abs_path = get_abs_path(path, username)
            if not abs_path.exists() or not abs_path.is_file():
                return jsonify({"success": False, "error": "File not found"}), 404
            ext = abs_path.suffix.lower()
            image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
            text_exts = {".txt", ".md", ".json", ".xml", ".html", ".css", ".js", ".py", ".csv", ".log"}
            if ext in image_exts:
                return send_file(str(abs_path), mimetype=f"image/{ext.lstrip('.')}")
            elif ext in text_exts or ext == "":
                content = abs_path.read_text(errors="replace")
                return jsonify({"success": True, "type": "text", "content": content, "name": abs_path.name})
            elif ext == ".pdf":
                return send_file(str(abs_path), mimetype="application/pdf")
            else:
                return jsonify({"success": False, "error": "Preview not supported for this file type"}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/download", methods=["GET"])
    @token_required
    def api_download():
        username = g.user["username"]
        path = request.args.get("path", "")
        try:
            abs_path = get_abs_path(path, username)
            if not abs_path.exists():
                return jsonify({"success": False, "error": "Not found"}), 404
            if abs_path.is_file():
                return stream_file(abs_path)
            else:
                return jsonify({"success": False, "error": "Cannot download directory"}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/share", methods=["POST"])
    @token_required
    def api_create_share():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        expire_hours = data.get("expireHours")
        password = data.get("password")
        try:
            result = create_share(path, username, expire_hours, password)
            log_audit(username, "share", path, {"shareId": result["id"], "expireHours": expire_hours, "hasPassword": password is not None})
            return jsonify({"success": True, "share": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/share/<share_id>", methods=["GET", "POST"])
    def api_get_share(share_id):
        password = None
        if request.method == "POST":
            data = request.get_json()
            password = data.get("password")
        else:
            password = request.args.get("password")
        try:
            share, error = get_share(share_id, password)
            if error:
                return jsonify({"success": False, "error": error}), 400
            username = share.get("username", "")
            if not username:
                return jsonify({"success": False, "error": "Invalid share data"}), 400
            abs_path = get_abs_path(share["path"], username)
            if not abs_path.exists():
                return jsonify({"success": False, "error": "File not found"}), 404
            if abs_path.is_file():
                info = get_file_info(abs_path, username)
                return jsonify({"success": True, "type": "file", "item": info})
            else:
                items = list_directory(share["path"], username)
                return jsonify({"success": True, "type": "dir", "items": items, "path": share["path"]})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/share/<share_id>/download", methods=["GET", "POST"])
    def api_share_download(share_id):
        password = request.args.get("password")
        subpath = request.args.get("subpath", "")
        if not password and request.method == "POST":
            data = request.get_json()
            password = data.get("password")
            subpath = data.get("subpath", "")
        try:
            share, error = get_share(share_id, password)
            if error:
                return jsonify({"success": False, "error": error}), 400
            username = share.get("username", "")
            if not username:
                return jsonify({"success": False, "error": "Invalid share data"}), 400
            base_path = get_abs_path(share["path"], username)
            if subpath:
                subpath = subpath.lstrip("/")
                abs_path = (base_path / subpath).resolve()
                if not str(abs_path).startswith(str(base_path.resolve())):
                    return jsonify({"success": False, "error": "Invalid subpath"}), 400
            else:
                abs_path = base_path
            if not abs_path.exists() or not abs_path.is_file():
                return jsonify({"success": False, "error": "Not found"}), 404
            return stream_file(abs_path)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/storage/usage", methods=["GET"])
    @token_required
    def api_storage_usage():
        username = g.user["username"]
        try:
            usage = get_user_storage_usage(username)
            return jsonify({"success": True, "usage": usage})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/trash", methods=["GET"])
    @token_required
    def api_list_trash():
        username = g.user["username"]
        try:
            items = list_trash(username)
            return jsonify({"success": True, "items": items})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/trash/restore", methods=["POST"])
    @token_required
    def api_restore_trash():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        try:
            item = restore_trash_item(path, username)
            log_audit(username, "restore_trash", path, {"newPath": item["path"]})
            emit_file_event(username, "restore_trash", {"item": item, "trashPath": path})
            return jsonify({"success": True, "item": item})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/trash/delete", methods=["POST"])
    @token_required
    def api_permanent_delete():
        username = g.user["username"]
        data = request.get_json()
        path = data.get("path", "")
        try:
            permanently_delete_trash_item(path, username)
            log_audit(username, "permanent_delete", path)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/trash/empty", methods=["POST"])
    @token_required
    def api_empty_trash():
        username = g.user["username"]
        try:
            empty_trash(username)
            log_audit(username, "empty_trash", "")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/audit", methods=["GET"])
    @token_required
    def api_get_audit_logs():
        username = g.user["username"]
        action_type = request.args.get("action")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("perPage", 20))
        try:
            result = read_audit_logs(username, action_type, page, per_page)
            return jsonify({"success": True, **result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    def stream_file(file_path: Path, chunk_size: int = 1024 * 1024):
        file_size = file_path.stat().st_size
        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1
        status_code = 200
        if range_header:
            range_match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if range_match:
                start_str, end_str = range_match.groups()
                if start_str:
                    start = int(start_str)
                if end_str:
                    end = int(end_str)
                start = max(0, min(start, file_size - 1))
                end = max(start, min(end, file_size - 1))
                status_code = 206
        def generate():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)
        headers = {
            "Content-Disposition": f"attachment; filename={file_path.name.encode('utf-8').decode('latin-1')}",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
        }
        if status_code == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return Response(
            generate(),
            status=status_code,
            headers=headers,
            direct_passthrough=True,
        )

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app


def main():
    app = create_app()
    socketio.run(app, host=Config.HOST, port=Config.PORT, debug=True)


if __name__ == "__main__":
    main()
