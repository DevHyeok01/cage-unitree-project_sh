import logging
import hashlib
import json
import random
import requests
import time
import sys
import os
import jwt
from dotenv import load_dotenv  # 추가
from Crypto.PublicKey import RSA
from .unitree_auth import make_remote_request
from .encryption import rsa_encrypt, rsa_load_public_key, aes_decrypt, generate_aes_key

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

def _generate_md5(string: str) -> str:
    md5_hash = hashlib.md5(string.encode())
    return md5_hash.hexdigest()

def generate_uuid():
    def replace_char(char):
        rand = random.randint(0, 15)
        if char == "x":
            return format(rand, 'x')
        elif char == "y":
            return format((rand & 0x3) | 0x8, 'x')

    uuid_template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return ''.join(replace_char(char) if char in 'xy' else char for char in uuid_template)

def get_nested_field(message, *fields):
    current_level = message
    for field in fields:
        if isinstance(current_level, dict) and field in current_level:
            current_level = current_level[field]
        else:
            return None
    return current_level

def fetch_token(email: str, password: str) -> str:
    path = "login/email"
    body = {
        'email': email,
        'password': _generate_md5(password)
    }
    response = make_remote_request(path, body, token="", method="POST")
    if response.get("code") == 100:
        data = response.get("data")
        access_token = data.get("accessToken")
        return access_token
    else:
        return None

def fetch_public_key() -> RSA.RsaKey:
    path = "system/pubKey"
    try:
        response = make_remote_request(path, {}, token="", method="GET")
        if response.get("code") == 100:
            public_key_pem = response.get("data")
            return rsa_load_public_key(public_key_pem)
        else:
            return None
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.RequestException:
        return None

def fetch_turn_server_info(serial: str, access_token: str, public_key: RSA.RsaKey) -> dict:
    aes_key = generate_aes_key()
    path = "webrtc/account"
    body = {
        "sn": serial,
        "sk": rsa_encrypt(aes_key, public_key)
    }
    response = make_remote_request(path, body, token=access_token, method="POST")
    if response.get("code") == 100:
        return json.loads(aes_decrypt(response['data'], aes_key))
    else:
        return None

def print_status(status_type, status_message):
    current_time = time.strftime("%H:%M:%S")
    print(f"🕒 {status_type:<25}: {status_message:<15} ({current_time})")

class TokenManager:
    def __init__(self, token_path='.unitree_token'):
        # 프로젝트 루트 디렉토리를 기준으로 token_path 설정
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.token_path = os.path.join(project_root, token_path)

    def save_token(self, token):
        """토큰을 파일에 저장합니다."""
        try:
            with open(self.token_path, 'w') as f:
                f.write(token)
            logging.info(f"토큰이 '{self.token_path}' 파일에 저장되었습니다.")
        except IOError as e:
            logging.error(f"토큰 파일 저장 중 오류 발생: {e}")

    def load_token(self):
        """파일에서 토큰을 불러옵니다. 파일이 없으면 None을 반환합니다."""
        if not os.path.exists(self.token_path):
            logging.info(f"저장된 토큰 파일('{self.token_path}')을 찾을 수 없습니다.")
            return None
        try:
            with open(self.token_path, 'r') as f:
                token = f.read().strip()
                if token:
                    logging.info(f"'{self.token_path}' 파일에서 토큰을 불러왔습니다.")
                    return token
                else:
                    logging.warning(f"토큰 파일('{self.token_path}')이 비어있습니다.")
                    self.delete_token() # 파일이 비어있으면 삭제
                    return None
        except IOError as e:
            logging.error(f"토큰 파일 로드 중 오류 발생: {e}")
            return None

    def delete_token(self):
        """토큰 파일을 삭제합니다."""
        if os.path.exists(self.token_path):
            try:
                os.remove(self.token_path)
                logging.info(f"기존 토큰 파일('{self.token_path}')을 삭제했습니다.")
            except OSError as e:
                logging.error(f"토큰 파일 삭제 중 오류 발생: {e}")


