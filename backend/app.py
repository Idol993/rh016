from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, init_db
from routes.auth import auth_bp
from routes.battery import battery_bp
from routes.bms import bms_bp
from routes.charging import charging_bp
from routes.recycling import recycling_bp
from routes.carbon import carbon_bp
from routes.dashboard import dashboard_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='/')
app.config['SECRET_KEY'] = 'battery-trace-secret-key-2024'
app.config['JWT_SECRET_KEY'] = 'battery-trace-jwt-secret-key-2024'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'battery.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app, supports_credentials=True)
JWTManager(app)
db.init_app(app)

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(battery_bp, url_prefix='/api/battery')
app.register_blueprint(bms_bp, url_prefix='/api/bms')
app.register_blueprint(charging_bp, url_prefix='/api/charging')
app.register_blueprint(recycling_bp, url_prefix='/api/recycling')
app.register_blueprint(carbon_bp, url_prefix='/api/carbon')
app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok', 'message': '动力电池溯源平台运行正常'})

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.errorhandler(404)
def not_found(e):
    path = request.path
    if path.startswith('/api/'):
        return jsonify({'message': 'API 接口不存在', 'code': 404}), 404
    return send_from_directory(FRONTEND_DIR, 'index.html')

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
