import os
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
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
)
from .auth import (
    create_user,
    authenticate_user,
    generate_token,
    token_required,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)
    ensure_dirs()

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
        path = request.args.get("path", "")
        try:
            items = list_directory(path)
            return jsonify({"success": True, "items": items, "path": path})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/search", methods=["GET"])
    @token_required
    def api_search_files():
        query = request.args.get("q", "")
        extension = request.args.get("ext", None)
        path = request.args.get("path", "")
        if not query:
            return jsonify({"success": False, "error": "Search query is required"}), 400
        try:
            items = search_files(query, extension, path)
            return jsonify({"success": True, "items": items, "query": query, "extension": extension})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/upload", methods=["POST"])
    @token_required
    def api_upload():
        path = request.form.get("path", "")
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No filename"}), 400
        try:
            info = save_upload(path, file)
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/folder", methods=["POST"])
    @token_required
    def api_create_folder():
        data = request.get_json()
        path = data.get("path", "")
        name = data.get("name", "")
        if not name:
            return jsonify({"success": False, "error": "Name required"}), 400
        try:
            info = create_folder(path, name)
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/delete", methods=["POST"])
    @token_required
    def api_delete():
        data = request.get_json()
        path = data.get("path", "")
        try:
            delete_item(path)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/rename", methods=["POST"])
    @token_required
    def api_rename():
        data = request.get_json()
        path = data.get("path", "")
        newName = data.get("newName", "")
        if not newName:
            return jsonify({"success": False, "error": "New name required"}), 400
        try:
            info = rename_item(path, newName)
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/move", methods=["POST"])
    @token_required
    def api_move():
        data = request.get_json()
        src = data.get("src", "")
        dst = data.get("dst", "")
        try:
            info = move_item(src, dst)
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/copy", methods=["POST"])
    @token_required
    def api_copy():
        data = request.get_json()
        src = data.get("src", "")
        dst = data.get("dst", "")
        try:
            info = copy_item(src, dst)
            return jsonify({"success": True, "item": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/files/preview", methods=["GET"])
    @token_required
    def api_preview():
        path = request.args.get("path", "")
        try:
            abs_path = get_abs_path(path)
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
        path = request.args.get("path", "")
        try:
            abs_path = get_abs_path(path)
            if not abs_path.exists():
                return jsonify({"success": False, "error": "Not found"}), 404
            if abs_path.is_file():
                return send_file(str(abs_path), as_attachment=True, download_name=abs_path.name)
            else:
                return jsonify({"success": False, "error": "Cannot download directory"}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/share", methods=["POST"])
    @token_required
    def api_create_share():
        data = request.get_json()
        path = data.get("path", "")
        expire_hours = data.get("expireHours")
        password = data.get("password")
        try:
            result = create_share(path, expire_hours, password)
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
            abs_path = get_abs_path(share["path"])
            if not abs_path.exists():
                return jsonify({"success": False, "error": "File not found"}), 404
            if abs_path.is_file():
                info = get_file_info(abs_path)
                return jsonify({"success": True, "type": "file", "item": info})
            else:
                items = list_directory(share["path"])
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
            base_path = get_abs_path(share["path"])
            if subpath:
                subpath = subpath.lstrip("/")
                abs_path = (base_path / subpath).resolve()
                if not str(abs_path).startswith(str(base_path.resolve())):
                    return jsonify({"success": False, "error": "Invalid subpath"}), 400
            else:
                abs_path = base_path
            if not abs_path.exists() or not abs_path.is_file():
                return jsonify({"success": False, "error": "Not found"}), 404
            return send_file(str(abs_path), as_attachment=True, download_name=abs_path.name)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app


def main():
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=True)


if __name__ == "__main__":
    main()
