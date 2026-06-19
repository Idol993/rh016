from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, ChargingRecord, Battery, User

charging_bp = Blueprint('charging', __name__)

@charging_bp.route('/start', methods=['POST'])
@jwt_required()
def start_charging():
    data = request.get_json()
    serial_code = data.get('serial_code')
    if not serial_code:
        return jsonify({'message': '缺少电池编码', 'code': 400}), 400
    
    battery = Battery.query.filter_by(serial_code=serial_code).first()
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status not in ['in_use']:
        return jsonify({'message': f'当前状态 {battery.status_name} 无法充电', 'code': 400}), 400
    
    start_soc = float(data.get('start_soc', random.uniform(10, 40)))
    
    soh = battery.current_soh
    temp = float(data.get('temperature', random.uniform(20, 35)))
    if temp < 5:
        strategy = '低温预热策略 - 启动加热膜，低电流预热后再进入恒流阶段'
    elif temp > 40:
        strategy = '高温保护策略 - 降低充电功率至50%，启动液冷散热'
    elif start_soc < 20:
        strategy = '深度补能策略 - 先小电流唤醒，再进入快充阶段'
    elif soh < 80:
        strategy = 'SOH优化策略 - 限制峰值电流，减小充电深度以延长寿命'
    elif start_soc < 50:
        strategy = '快速补能策略 - 恒流快充至80%，然后转恒压涓流'
    else:
        strategy = '标准恒流充电 - 标准电流充电至95%，涓流至满'
    
    record = ChargingRecord(
        battery_id=battery.id,
        start_soc=round(start_soc, 1),
        charging_strategy=strategy,
        charging_power=round(random.uniform(30, 120) if temp < 40 else random.uniform(20, 60), 1),
        max_temperature=round(temp, 1),
        status='charging'
    )
    db.session.add(record)
    db.session.commit()
    
    return jsonify({
        'message': '充电开始，已根据电池状态动态调整策略',
        'code': 200,
        'data': record.to_dict()
    })

@charging_bp.route('/stop/<int:cid>', methods=['POST'])
@jwt_required()
def stop_charging(cid):
    record = ChargingRecord.query.get(cid)
    if not record:
        return jsonify({'message': '充电记录不存在', 'code': 404}), 404
    if record.status != 'charging':
        return jsonify({'message': '充电已结束', 'code': 400}), 400
    
    data = request.get_json()
    end_soc = float(data.get('end_soc', record.start_soc + random.uniform(20, 60)))
    end_soc = min(100, end_soc)
    max_temp = round(float(data.get('max_temperature', record.max_temperature + random.uniform(2, 10))), 1)
    
    is_alerted = max_temp > 45
    alert = None
    if max_temp > 50:
        is_alerted = True
        alert = '电池温度过高，系统已自动断电保护！请检查冷却系统'
    elif max_temp > 45:
        is_alerted = True
        alert = '电池温度过高，已自动降低充电功率，建议等待冷却'
    
    record.end_soc = round(end_soc, 1)
    record.max_temperature = max_temp
    record.is_alerted = is_alerted
    record.alert_message = alert
    record.end_time = datetime.now()
    record.status = 'completed'
    
    db.session.commit()
    
    return jsonify({
        'message': '充电结束' + ('，异常发热已触发预警' if is_alerted else ''),
        'code': 200,
        'data': record.to_dict()
    })

@charging_bp.route('/list', methods=['GET'])
@jwt_required()
def list_charging():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    serial_code = request.args.get('serial_code', '')
    
    query = ChargingRecord.query
    
    if serial_code:
        battery = Battery.query.filter_by(serial_code=serial_code).first()
        if battery:
            query = query.filter(ChargingRecord.battery_id == battery.id)
        else:
            query = query.filter(False)
    
    if current_user.role == 'automaker':
        battery_ids = [b.id for b in Battery.query.filter_by(automaker=current_user.company_name).all()]
        query = query.filter(ChargingRecord.battery_id.in_(battery_ids))
    
    total = query.count()
    records = query.order_by(ChargingRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'list': [r.to_dict() for r in records]
        }
    })

@charging_bp.route('/stats', methods=['GET'])
@jwt_required()
def charging_stats():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    query = ChargingRecord.query
    if current_user.role == 'automaker':
        battery_ids = [b.id for b in Battery.query.filter_by(automaker=current_user.company_name).all()]
        query = query.filter(ChargingRecord.battery_id.in_(battery_ids))
    
    total = query.count()
    alerted = query.filter_by(is_alerted=True).count()
    avg_power = db.session.query(db.func.avg(ChargingRecord.charging_power)).scalar() or 0
    strategy_counts = db.session.query(
        ChargingRecord.charging_strategy, db.func.count(ChargingRecord.id)
    ).group_by(ChargingRecord.charging_strategy).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total_charging': total,
            'alerted_count': alerted,
            'avg_power': round(avg_power, 1),
            'strategy_distribution': [{'strategy': s, 'count': c} for s, c in strategy_counts]
        }
    })
