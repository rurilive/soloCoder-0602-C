import json
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from flask import request, jsonify, g

from .config import Config, USERS_DIR


def ensure_users_dir():
    USERS_DIR.mkdir(parents=True, exist_ok=True)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def generate_token(user_id: str, username: str) -> str:
    payload = {
        'user_id': user_id,
        'username': username,
        'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm='HS256')


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise ValueError('Token has expired')
    except jwt.InvalidTokenError:
        raise ValueError('Invalid token')


def get_user_file_path(username: str) -> Path:
    return USERS_DIR / f"{username}.json"


def user_exists(username: str) -> bool:
    return get_user_file_path(username).exists()


def create_user(username: str, password: str) -> dict:
    if user_exists(username):
        raise ValueError('Username already exists')
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    user_data = {
        'id': user_id,
        'username': username,
        'password_hash': password_hash,
        'created_at': datetime.utcnow().isoformat()
    }
    user_file = get_user_file_path(username)
    with open(user_file, 'w') as f:
        json.dump(user_data, f)
    return {
        'id': user_id,
        'username': username
    }


def authenticate_user(username: str, password: str) -> dict:
    user_file = get_user_file_path(username)
    if not user_file.exists():
        raise ValueError('Invalid username or password')
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if not verify_password(password, user_data['password_hash']):
        raise ValueError('Invalid username or password')
    return {
        'id': user_data['id'],
        'username': user_data['username']
    }


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        if not token:
            token = request.args.get('token')
        if not token:
            return jsonify({'success': False, 'error': 'Token is missing'}), 401
        try:
            data = decode_token(token)
            g.user = {
                'id': data['user_id'],
                'username': data['username']
            }
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 401
        return f(*args, **kwargs)
    return decorated
