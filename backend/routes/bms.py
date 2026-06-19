from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, BMSRecord, Battery, User

bms_bp = Blueprint('bms', __name__)

@bms_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_bms():
    data = request.get_json()
    serial_code = data.get('serial_code')
    if not serial_code:
        return jsonify({'message': '缺少电池编码', 'code': 400}), 400
    
    battery = Battery.query.filter_by(serial_code=serial_code).first()
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    
    voltage = float(data.get('voltage', 380))
    current = float(data.get('current', 0))
    temperature = float(data.get('temperature', 28))
    soc = float(data.get('soc', 80))
    soh = float(data.get('soh', battery.current_soh))
    cell_temps = data.get('cell_temperatures', [])
    cell_volts = data.get('cell_voltages', [])
    
    abnormal = temperature > 45 or temperature < -10
    warning = None
    if temperature > 50:
        warning = '过温告警-紧急断电保护已启动'
    elif temperature > 45:
        warning = '过温预警-请立即检查冷却系统'
    elif temperature < -10:
        warning = '低温预警-电池性能下降'
    
    record = BMSRecord(
        battery_id=battery.id,
        voltage=voltage,
        current=current,
        temperature=temperature,
        soc=soc,
        soh=soh,
        cell_temperatures=','.join([str(x) for x in cell_temps]) if cell_temps else ','.join([str(round(random.uniform(22, 42), 1)) for _ in range(96)]),
        cell_voltages=','.join([str(x) for x in cell_volts]) if cell_volts else ','.join([str(round(random.uniform(3.2, 4.2), 3)) for _ in range(96)]),
        is_abnormal=abnormal,
        warning_type=warning,
        record_time=datetime.now()
    )
    db.session.add(record)
    
    battery.current_soh = min(battery.current_soh, soh)
    db.session.commit()
    
    return jsonify({
        'message': 'BMS数据上传成功',
        'code': 200,
        'data': {
            'alert': warning,
            'abnormal': abnormal,
            'record': record.to_dict()
        }
    })

@bms_bp.route('/realtime/<int:battery_id>', methods=['GET'])
@jwt_required()
def realtime_data(battery_id):
    battery = Battery.query.get(battery_id)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    
    latest = BMSRecord.query.filter_by(battery_id=battery_id).order_by(BMSRecord.record_time.desc()).first()
    
    hours = int(request.args.get('hours', 24))
    from datetime import timedelta
    start_time = datetime.now() - timedelta(hours=hours)
    history = BMSRecord.query.filter(
        BMSRecord.battery_id == battery_id,
        BMSRecord.record_time >= start_time
    ).order_by(BMSRecord.record_time.asc()).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'battery': battery.to_dict(),
            'latest': latest.to_dict() if latest else None,
            'history': [r.to_dict() for r in history]
        }
    })

@bms_bp.route('/warnings', methods=['GET'])
@jwt_required()
def warnings_list():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    query = BMSRecord.query.filter(BMSRecord.is_abnormal == True)
    
    if current_user.role == 'automaker':
        battery_ids = [b.id for b in Battery.query.filter_by(automaker=current_user.company_name).all()]
        query = query.filter(BMSRecord.battery_id.in_(battery_ids))
    elif current_user.role == 'battery_factory':
        battery_ids = [b.id for b in Battery.query.filter_by(battery_factory=current_user.company_name).all()]
        query = query.filter(BMSRecord.battery_id.in_(battery_ids))
    
    total = query.count()
    records = query.order_by(BMSRecord.record_time.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'list': [r.to_dict() for r in records]
        }
    })

@bms_bp.route('/simulate/<int:battery_id>', methods=['POST'])
@jwt_required()
def simulate_bms(battery_id):
    battery = Battery.query.get(battery_id)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    
    for _ in range(5):
        temp = round(random.uniform(22, 48), 1)
        abnormal = temp > 42
        warning = '过温告警-紧急断电保护已启动' if temp > 47 else ('过温预警-请立即检查' if abnormal else None)
        
        r = BMSRecord(
            battery_id=battery.id,
            voltage=round(random.uniform(320, 410), 2),
            current=round(random.uniform(-150, 200), 2),
            temperature=temp,
            soc=round(random.uniform(10, 100), 1),
            soh=round(random.uniform(max(50, battery.current_soh - 5), min(100, battery.current_soh + 2)), 2),
            cell_temperatures=','.join([str(round(random.uniform(22, 42), 1)) for _ in range(96)]),
            cell_voltages=','.join([str(round(random.uniform(3.2, 4.2), 3)) for _ in range(96)]),
            is_abnormal=abnormal,
            warning_type=warning
        )
        db.session.add(r)
    
    db.session.commit()
    return jsonify({'message': '模拟数据生成成功', 'code': 200})
