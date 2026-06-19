from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, RecyclingRecord, Battery, ScrapAssessment, User

recycling_bp = Blueprint('recycling', __name__)

@recycling_bp.route('/scan-inbound', methods=['POST'])
@jwt_required()
def scan_inbound():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    if current_user.role != 'recycler':
        return jsonify({'message': '只有回收商可以操作', 'code': 403}), 403
    
    data = request.get_json()
    serial_code = data.get('serial_code')
    if not serial_code:
        return jsonify({'message': '缺少电池编码', 'code': 400}), 400
    
    battery = Battery.query.filter_by(serial_code=serial_code).first()
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    if battery.status not in ['scrapped', 'second_life']:
        return jsonify({'message': f'当前状态 {battery.status_name} 无法回收', 'code': 400}), 400
    
    existing = RecyclingRecord.query.filter(
        RecyclingRecord.battery_id == battery.id,
        RecyclingRecord.disassembly_status == 'pending'
    ).first()
    if existing:
        return jsonify({'message': '该电池已入库，待拆解', 'code': 400, 'data': existing.to_dict()}), 400
    
    year = datetime.now().year
    count = RecyclingRecord.query.count() + 1
    record = RecyclingRecord(
        battery_id=battery.id,
        recycler_name=current_user.company_name,
        inbound_code=f'IN{year}{count:05d}',
        disassembly_order=f'DO{year}{count:05d}',
        disassembly_status='pending'
    )
    db.session.add(record)
    
    battery.status = 'recycled'
    battery.status_name = '已回收拆解'
    db.session.commit()
    
    return jsonify({
        'message': '扫码入库成功，已生成拆解工单',
        'code': 200,
        'data': record.to_dict()
    })

@recycling_bp.route('/complete/<int:rid>', methods=['POST'])
@jwt_required()
def complete_disassembly(rid):
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    if current_user.role != 'recycler':
        return jsonify({'message': '只有回收商可以操作', 'code': 403}), 403
    
    record = RecyclingRecord.query.get(rid)
    if not record:
        return jsonify({'message': '记录不存在', 'code': 404}), 404
    if record.disassembly_status != 'pending':
        return jsonify({'message': '该工单已完成', 'code': 400}), 400
    
    data = request.get_json()
    record.lithium_extracted = round(float(data.get('lithium_extracted', random.uniform(2.5, 6.5))), 3)
    record.cobalt_extracted = round(float(data.get('cobalt_extracted', random.uniform(0.5, 3.5))), 3)
    record.nickel_extracted = round(float(data.get('nickel_extracted', random.uniform(1.5, 8.5))), 3)
    record.manganese_extracted = round(float(data.get('manganese_extracted', random.uniform(0.3, 2.0))), 3)
    record.other_metals = round(float(data.get('other_metals', random.uniform(0.5, 5.0))), 3)
    record.disassembly_status = 'completed'
    record.completed_at = datetime.now()
    
    db.session.commit()
    return jsonify({
        'message': '拆解完成，已记录贵金属提取量',
        'code': 200,
        'data': record.to_dict()
    })

@recycling_bp.route('/list', methods=['GET'])
@jwt_required()
def list_recycling():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    status = request.args.get('status', '')
    
    query = RecyclingRecord.query
    if current_user.role == 'recycler':
        query = query.filter(RecyclingRecord.recycler_name == current_user.company_name)
    if status:
        query = query.filter(RecyclingRecord.disassembly_status == status)
    
    total = query.count()
    records = query.order_by(RecyclingRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'list': [r.to_dict() for r in records]
        }
    })

@recycling_bp.route('/assessments', methods=['GET'])
@jwt_required()
def list_assessments():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    total = ScrapAssessment.query.count()
    records = ScrapAssessment.query.order_by(ScrapAssessment.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'list': [r.to_dict() for r in records]
        }
    })

@recycling_bp.route('/stats', methods=['GET'])
@jwt_required()
def recycling_stats():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    query = RecyclingRecord.query
    if current_user.role == 'recycler':
        query = query.filter(RecyclingRecord.recycler_name == current_user.company_name)
    
    total = query.count()
    completed = query.filter_by(disassembly_status='completed').count()
    pending = total - completed
    
    li = db.session.query(db.func.sum(RecyclingRecord.lithium_extracted)).scalar() or 0
    co = db.session.query(db.func.sum(RecyclingRecord.cobalt_extracted)).scalar() or 0
    ni = db.session.query(db.func.sum(RecyclingRecord.nickel_extracted)).scalar() or 0
    mn = db.session.query(db.func.sum(RecyclingRecord.manganese_extracted)).scalar() or 0
    other = db.session.query(db.func.sum(RecyclingRecord.other_metals)).scalar() or 0
    
    scenario_counts = db.session.query(
        ScrapAssessment.recommended_scenario, db.func.count(ScrapAssessment.id)
    ).group_by(ScrapAssessment.recommended_scenario).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total_recycled': total,
            'completed': completed,
            'pending': pending,
            'metals': {
                'lithium': round(li, 3),
                'cobalt': round(co, 3),
                'nickel': round(ni, 3),
                'manganese': round(mn, 3),
                'other': round(other, 3),
                'total': round(li + co + ni + mn + other, 3)
            },
            'scenario_distribution': [{'scenario': s, 'count': c} for s, c in scenario_counts]
        }
    })
