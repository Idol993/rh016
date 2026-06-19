from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, User, ROLES

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'message': '用户名和密码不能为空', 'code': 400}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'message': '用户名或密码错误', 'code': 401}), 401
    
    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        'message': '登录成功',
        'code': 200,
        'data': {
            'token': access_token,
            'user': user.to_dict()
        }
    })

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({'message': '用户不存在', 'code': 404}), 404
    return jsonify({'code': 200, 'data': user.to_dict()})

@auth_bp.route('/users', methods=['GET'])
@jwt_required()
def list_users():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    if not current_user or current_user.role != 'regulator':
        return jsonify({'message': '无权访问', 'code': 403}), 403
    users = User.query.all()
    return jsonify({'code': 200, 'data': {'list': [u.to_dict() for u in users], 'roles': ROLES}})

@auth_bp.route('/roles', methods=['GET'])
def get_roles():
    return jsonify({'code': 200, 'data': ROLES})
