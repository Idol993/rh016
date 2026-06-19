from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, Battery, BMSRecord, ScrapAssessment, STATUS_MAP, User, ROLES

battery_bp = Blueprint('battery', __name__)

@battery_bp.route('/list', methods=['GET'])
@jwt_required()
def list_batteries():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')
    automaker = request.args.get('automaker', '')
    factory = request.args.get('factory', '')
    
    query = Battery.query
    
    if current_user.role == 'battery_factory':
        query = query.filter(Battery.battery_factory == current_user.company_name)
    elif current_user.role == 'automaker':
        query = query.filter(Battery.automaker == current_user.company_name)
    
    if keyword:
        query = query.filter((Battery.serial_code.contains(keyword)) | 
                            (Battery.vehicle_plate.contains(keyword)) |
                            (Battery.production_batch.contains(keyword)))
    if status:
        query = query.filter(Battery.status == status)
    if automaker:
        query = query.filter(Battery.automaker == automaker)
    if factory:
        query = query.filter(Battery.battery_factory == factory)
    
    total = query.count()
    batteries = query.order_by(Battery.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'page': page,
            'page_size': page_size,
            'list': [b.to_dict() for b in batteries]
        }
    })

@battery_bp.route('/create', methods=['POST'])
@jwt_required()
def create_battery():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    if current_user.role != 'battery_factory':
        return jsonify({'message': '只有电池厂可以新增电池', 'code': 403}), 403
    
    data = request.get_json()
    required = ['serial_code', 'cell_model', 'capacity', 'production_batch', 'production_date']
    for f in required:
        if not data.get(f):
            return jsonify({'message': f'字段 {f} 不能为空', 'code': 400}), 400
    
    if Battery.query.filter_by(serial_code=data['serial_code']).first():
        return jsonify({'message': '该编码已存在', 'code': 400}), 400
    
    battery = Battery(
        serial_code=data['serial_code'],
        cell_model=data['cell_model'],
        capacity=float(data['capacity']),
        production_batch=data['production_batch'],
        production_date=datetime.strptime(data['production_date'], '%Y-%m-%d'),
        battery_factory=current_user.company_name,
        status='produced',
        status_name='已生产',
        current_soh=100.0,
        remaining_capacity=float(data['capacity'])
    )
    db.session.add(battery)
    db.session.commit()
    return jsonify({'message': '电池创建成功，唯一编码已写入', 'code': 200, 'data': battery.to_dict()})

@battery_bp.route('/<int:bid>', methods=['GET'])
@jwt_required()
def get_battery(bid):
    battery = Battery.query.get(bid)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    
    bms_records = BMSRecord.query.filter_by(battery_id=bid).order_by(BMSRecord.record_time.desc()).limit(50).all()
    scrap = ScrapAssessment.query.filter_by(battery_id=bid).first()
    
    result = battery.to_dict()
    result['bms_history'] = [r.to_dict() for r in bms_records]
    result['scrap_assessment'] = scrap.to_dict() if scrap else None
    
    return jsonify({'code': 200, 'data': result})

@battery_bp.route('/<int:bid>/install', methods=['POST'])
@jwt_required()
def install_battery(bid):
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    if current_user.role != 'automaker':
        return jsonify({'message': '只有车企可以装车', 'code': 403}), 403
    
    data = request.get_json()
    battery = Battery.query.get(bid)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status not in ['produced', 'shipped']:
        return jsonify({'message': f'当前状态 {battery.status_name} 无法装车', 'code': 400}), 400
    
    battery.automaker = current_user.company_name
    battery.vehicle_plate = data.get('vehicle_plate', '')
    battery.status = 'installed'
    battery.status_name = '已装车'
    db.session.commit()
    return jsonify({'message': '装车成功', 'code': 200, 'data': battery.to_dict()})

@battery_bp.route('/<int:bid>/start-use', methods=['POST'])
@jwt_required()
def start_use(bid):
    battery = Battery.query.get(bid)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status != 'installed':
        return jsonify({'message': f'当前状态 {battery.status_name} 无法启用', 'code': 400}), 400
    battery.status = 'in_use'
    battery.status_name = '使用中'
    db.session.commit()
    return jsonify({'message': '已启用', 'code': 200})

@battery_bp.route('/status-options', methods=['GET'])
def status_options():
    return jsonify({'code': 200, 'data': STATUS_MAP})

@battery_bp.route('/<int:bid>/assess', methods=['POST'])
@jwt_required()
def assess_battery(bid):
    battery = Battery.query.get(bid)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status != 'in_use':
        return jsonify({'message': f'当前状态 {battery.status_name} 无法评估残值', 'code': 400}), 400
    
    soh = battery.current_soh
    if soh >= 60:
        scenario = '储能电站 - 削峰填谷'
        detail = '电池SOH较高，适合用于电网级储能系统，预计可服役5-8年'
        value = round(soh * 80, 0)
    elif soh >= 40:
        scenario = '低速电动车 / 电动叉车'
        detail = '电池SOH中等，适合用于低速车辆及工程机械'
        value = round(soh * 50, 0)
    else:
        scenario = '拆解回收 - 提取贵金属'
        detail = '电池SOH较低，建议拆解回收锂、钴、镍等贵金属'
        value = round(soh * 25, 0)
    
    sa = ScrapAssessment.query.filter_by(battery_id=bid).first()
    if sa:
        sa.final_soh = soh
        sa.residual_value = value
        sa.recommended_scenario = scenario
        sa.scenario_detail = detail
    else:
        sa = ScrapAssessment(
            battery_id=bid,
            final_soh=soh,
            residual_value=value,
            recommended_scenario=scenario,
            scenario_detail=detail
        )
        db.session.add(sa)
    
    battery.status = 'scrapped'
    battery.status_name = '已报废'
    db.session.commit()
    
    return jsonify({
        'message': '残值评估完成',
        'code': 200,
        'data': {
            'assessment': sa.to_dict(),
            'battery': battery.to_dict()
        }
    })

@battery_bp.route('/<int:bid>/second-life', methods=['POST'])
@jwt_required()
def second_life(bid):
    battery = Battery.query.get(bid)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status != 'scrapped':
        return jsonify({'message': f'当前状态 {battery.status_name} 无法转梯次利用', 'code': 400}), 400
    battery.status = 'second_life'
    battery.status_name = '梯次利用'
    db.session.commit()
    return jsonify({'message': '梯次利用状态已更新', 'code': 200})

@battery_bp.route('/automakers', methods=['GET'])
@jwt_required()
def get_automakers():
    result = db.session.query(Battery.automaker).filter(Battery.automaker.isnot(None)).distinct().all()
    factories = db.session.query(Battery.battery_factory).filter(Battery.battery_factory.isnot(None)).distinct().all()
    return jsonify({
        'code': 200,
        'data': {
            'automakers': [r[0] for r in result if r[0]],
            'factories': [r[0] for r in factories if r[0]]
        }
    })
